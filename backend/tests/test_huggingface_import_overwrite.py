"""HuggingFace import must not re-point existing / built-in benchmarks."""
import json
import os
import secrets
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

import importlib.util

BACKEND_DIR = Path(__file__).resolve().parent.parent
BENCHMARKS_PATH = BACKEND_DIR / "api" / "routers" / "benchmarks.py"
_spec = importlib.util.spec_from_file_location("benchmarks_hf_import_module", BENCHMARKS_PATH)
benchmarks = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(benchmarks)

from core.models import Benchmark, BenchmarkType


class _FakeHFResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "rows": [
                {"row": {"question": "attacker prompt", "answer": "attacker answer"}},
            ]
        }


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, *args, **kwargs):
        return _FakeHFResponse()


@pytest.fixture
def test_dirs(tmp_path):
    return {
        "bench_library": tmp_path / "bench_library",
        "db_path": tmp_path / "hf_import.db",
    }


@pytest.fixture
def db_engine(test_dirs):
    engine = create_engine(
        f"sqlite:///{test_dirs['db_path']}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def client(db_engine, test_dirs, monkeypatch):
    test_dirs["bench_library"].mkdir(parents=True, exist_ok=True)
    benchmarks.settings.bench_library_path = str(test_dirs["bench_library"])
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    def _get_session_override():
        with Session(db_engine) as session:
            yield session

    test_app = FastAPI()
    test_app.include_router(benchmarks.router)
    test_app.dependency_overrides[benchmarks.get_session] = _get_session_override
    with TestClient(test_app) as c:
        yield c


def _create_builtin(engine, *, name: str, dataset_path: str) -> int:
    with Session(engine) as session:
        bench = Benchmark(
            name=name,
            type=BenchmarkType.ACADEMIC,
            description="seeded builtin",
            dataset_path=dataset_path,
            metric="accuracy",
            num_samples=50,
            is_builtin=True,
            has_dataset=True,
            config_json="{}",
        )
        session.add(bench)
        session.commit()
        session.refresh(bench)
        return bench.id


def test_hf_import_refuses_to_override_builtin_dataset(client, db_engine, test_dirs):
    original_path = "academic/mmlu_subset.json"
    bench_id = _create_builtin(db_engine, name="MMLU (subset)", dataset_path=original_path)

    resp = client.post(
        "/benchmarks/import-huggingface",
        json={
            "repo_id": "attacker/poisoned-eval",
            "split": "test",
            "max_items": 10,
            "benchmark_name": "MMLU (subset)",
        },
    )
    assert resp.status_code == 400, resp.text
    assert "built-in" in resp.json()["detail"].lower()

    with Session(db_engine) as session:
        bench = session.get(Benchmark, bench_id)
        assert bench is not None
        assert bench.dataset_path == original_path
        assert bench.is_builtin is True
        assert bench.num_samples == 50

    custom_dir = test_dirs["bench_library"] / "custom"
    assert not custom_dir.exists() or not any(custom_dir.iterdir())


def test_hf_import_refuses_to_clobber_unrelated_custom_benchmark(client, db_engine):
    with Session(db_engine) as session:
        custom = Benchmark(
            name="My custom eval",
            type=BenchmarkType.CUSTOM,
            description="tenant dataset",
            dataset_path="custom/mine.json",
            metric="accuracy",
            num_samples=12,
            is_builtin=False,
            has_dataset=True,
            config_json="{}",
        )
        session.add(custom)
        session.commit()
        session.refresh(custom)
        custom_id = custom.id

    resp = client.post(
        "/benchmarks/import-huggingface",
        json={
            "repo_id": "attacker/other",
            "split": "test",
            "max_items": 10,
            "benchmark_name": "My custom eval",
        },
    )
    assert resp.status_code == 409, resp.text

    with Session(db_engine) as session:
        bench = session.get(Benchmark, custom_id)
        assert bench is not None
        assert bench.dataset_path == "custom/mine.json"
        assert bench.num_samples == 12


def test_hf_import_allows_reimport_of_same_repo(client, db_engine):
    resp = client.post(
        "/benchmarks/import-huggingface",
        json={
            "repo_id": "org/demo-bench",
            "split": "test",
            "max_items": 10,
        },
    )
    assert resp.status_code == 200, resp.text
    first = resp.json()
    assert first["benchmark_name"] == "org_demo-bench"

    resp2 = client.post(
        "/benchmarks/import-huggingface",
        json={
            "repo_id": "org/demo-bench",
            "split": "test",
            "max_items": 10,
        },
    )
    assert resp2.status_code == 200, resp2.text
    second = resp2.json()
    assert second["benchmark_id"] == first["benchmark_id"]
    assert second["items_imported"] == 1

    with Session(db_engine) as session:
        bench = session.get(Benchmark, first["benchmark_id"])
        assert bench is not None
        cfg = json.loads(bench.config_json)
        assert cfg["source"] == "huggingface"
        assert cfg["repo_id"] == "org/demo-bench"
        assert bench.is_builtin is False
