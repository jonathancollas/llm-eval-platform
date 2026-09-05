"""
HuggingFace import must persist a scorable local dataset.

The catalog wizard and /redbox-adjacent catalog modal POST
/benchmarks/import-huggingface with max_items=200. On main, create set
num_samples=min(len, 50), left integer `answer` untouched (cais/mmlu),
and ignored the wizard's `name_override` field.
"""
import json
import os
import secrets
import sys
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from core.models import Benchmark, BenchmarkType
from eval_engine.custom.runner import CustomRunner
from eval_engine.item_normalize import item_expected, normalize_imported_item

BACKEND_DIR = Path(__file__).resolve().parent.parent


# ── Pure normalization ─────────────────────────────────────────────────────────

class TestNormalizeImportedItem:
    def test_mmlu_integer_answer_becomes_letter(self):
        item = normalize_imported_item({
            "question": "Capital of France?",
            "choices": ["Paris", "London", "Berlin", "Rome"],
            "answer": 0,
        })
        assert item["answer"] == "A"
        assert item["expected"] == "A"
        assert item["prompt"] == "Capital of France?"

    def test_already_present_int_answer_is_stringified_without_choices(self):
        item = normalize_imported_item({"question": "How many?", "answer": 0})
        assert item["answer"] == "0"
        assert item["expected"] == "0"

    def test_label_field_copied_when_answer_missing(self):
        item = normalize_imported_item({
            "question": "q",
            "choices": ["a", "b", "c", "d"],
            "label": 2,
        })
        assert item["answer"] == "C"

    def test_open_ended_gets_prompt_and_expected(self):
        item = normalize_imported_item({"question": "2+2?", "answer": "4"})
        assert item["prompt"] == "2+2?"
        assert item["expected"] == "4"

    def test_item_expected_keeps_zero(self):
        assert item_expected({"answer": 0}) == "0"
        assert item_expected({"expected": "REFUSE"}) == "REFUSE"
        assert item_expected({}) is None


# ── HTTP import ────────────────────────────────────────────────────────────────

@pytest.fixture
def test_dirs(tmp_path_factory):
    root = tmp_path_factory.mktemp("hf_import")
    return {
        "bench_library": root / "bench_library",
        "db_path": root / "test.db",
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
def hf_module_and_app(db_engine, test_dirs, monkeypatch):
    import importlib.util

    test_dirs["bench_library"].mkdir(parents=True, exist_ok=True)
    path = BACKEND_DIR / "api" / "routers" / "benchmarks.py"
    spec = importlib.util.spec_from_file_location("hf_import_router", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)

    module.settings.bench_library_path = str(test_dirs["bench_library"])

    def _session():
        with Session(db_engine) as session:
            yield session

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[module.get_session] = _session
    return module, app, db_engine


@pytest.fixture
def client(hf_module_and_app):
    _module, app, _engine = hf_module_and_app
    with TestClient(app) as c:
        yield c


def _mmlu_rows(n: int = 80):
    rows = []
    for i in range(n):
        rows.append({
            "row": {
                "question": f"Question {i}?",
                "choices": ["Paris", "London", "Berlin", "Rome"],
                "answer": i % 4,
                "subject": "geography",
            }
        })
    return rows


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeAsyncClient:
    def __init__(self, rows):
        self.rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        offset = int((params or {}).get("offset") or 0)
        length = int((params or {}).get("length") or 100)
        page = self.rows[offset:offset + length]
        return _FakeResponse({"rows": page})


def test_import_persists_full_num_samples_and_letter_answers(
    client, hf_module_and_app, monkeypatch, test_dirs,
):
    module, _app, engine = hf_module_and_app
    rows = _mmlu_rows(80)

    class _Factory:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return _FakeAsyncClient(rows)

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr("httpx.AsyncClient", _Factory)

    resp = client.post(
        "/benchmarks/import-huggingface",
        json={
            "repo_id": "cais/mmlu",
            "split": "test",
            "max_items": 80,
            "name_override": "Imported MMLU",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items_imported"] == 80
    assert body["benchmark_name"] == "Imported MMLU"

    with Session(engine) as session:
        bench = session.exec(select(Benchmark).where(Benchmark.name == "Imported MMLU")).one()
        assert bench.num_samples == 80
        assert bench.has_dataset is True
        dataset_path = bench.dataset_path

    dataset = Path(test_dirs["bench_library"]) / dataset_path
    items = json.loads(dataset.read_text())
    assert len(items) == 80
    assert items[0]["answer"] == "A"
    assert items[1]["answer"] == "B"
    assert items[0]["expected"] == "A"

    runner = CustomRunner(
        Benchmark(id=1, name="Imported MMLU", type=BenchmarkType.CUSTOM, config_json="{}"),
        str(test_dirs["bench_library"]),
    )
    assert runner.score_item("A", items[0]) == 1.0
    assert runner.score_item("B", items[0]) == 0.0


def test_import_uses_benchmark_name_when_both_aliases_sent(
    client, hf_module_and_app, monkeypatch,
):
    _module, _app, engine = hf_module_and_app
    rows = _mmlu_rows(10)

    class _Factory:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return _FakeAsyncClient(rows)

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr("httpx.AsyncClient", _Factory)

    name = f"named-hf-{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/benchmarks/import-huggingface",
        json={
            "repo_id": "org/ds",
            "split": "test",
            "max_items": 10,
            "benchmark_name": name,
            "name_override": "should-not-win",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["benchmark_name"] == name
    with Session(engine) as session:
        assert session.exec(select(Benchmark).where(Benchmark.name == name)).first()
