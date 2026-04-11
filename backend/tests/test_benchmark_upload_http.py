import os
import sys
import importlib.util
import uuid
import secrets
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Settings required by app config
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

BACKEND_DIR = Path(__file__).resolve().parent.parent
BENCHMARKS_PATH = BACKEND_DIR / "api" / "routers" / "benchmarks.py"
_spec = importlib.util.spec_from_file_location("benchmarks_router_module", BENCHMARKS_PATH)
benchmarks = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(benchmarks)


@pytest.fixture(scope="module")
def test_dirs(tmp_path_factory):
    root = tmp_path_factory.mktemp("bench_upload_http")
    return {
        "bench_library": root / "bench_library",
        "db_path": root / "test_http.db",
    }


@pytest.fixture(scope="module")
def db_engine(test_dirs):
    engine = create_engine(
        f"sqlite:///{test_dirs['db_path']}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine, test_dirs):
    test_dirs["bench_library"].mkdir(parents=True, exist_ok=True)
    benchmarks.settings.bench_library_path = str(test_dirs["bench_library"])

    def _get_session_override():
        with Session(db_engine) as session:
            yield session

    test_app = FastAPI()
    test_app.include_router(benchmarks.router)
    test_app.dependency_overrides[benchmarks.get_session] = _get_session_override
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def benchmark_id(client):
    resp = client.post(
        "/benchmarks/",
        json={
            "name": f"upload-http-test-benchmark-{uuid.uuid4().hex[:8]}",
            "type": "custom",
            "description": "fixture benchmark",
            "tags": [],
            "metric": "accuracy",
            "config": {},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_upload_dataset_json_success(client, benchmark_id, test_dirs):
    custom_dir = test_dirs["bench_library"] / "custom"
    existing_files = set(custom_dir.glob("*_dataset.json")) if custom_dir.exists() else set()
    files = {"file": ("dataset.json", b'[{"prompt":"p","answer":"a"}]', "application/json")}
    resp = client.post(f"/benchmarks/{benchmark_id}/upload-dataset", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == benchmark_id
    assert body["has_dataset"] is True
    created_files = set(custom_dir.glob("*_dataset.json")) - existing_files
    assert len(created_files) == 1
    created_file = next(iter(created_files))
    assert created_file.read_bytes() == b'[{"prompt":"p","answer":"a"}]'


def test_upload_dataset_empty_json_rejected(client, benchmark_id):
    files = {"file": ("dataset.json", b"[]", "application/json")}
    resp = client.post(f"/benchmarks/{benchmark_id}/upload-dataset", files=files)
    assert resp.status_code == 422
    assert "non-empty list" in resp.json()["detail"]
    bench = client.get(f"/benchmarks/{benchmark_id}")
    assert bench.status_code == 200
    assert bench.json()["has_dataset"] is False


def test_upload_dataset_invalid_json_rejected(client, benchmark_id):
    files = {"file": ("dataset.json", b"{invalid", "application/json")}
    resp = client.post(f"/benchmarks/{benchmark_id}/upload-dataset", files=files)
    assert resp.status_code == 422
    assert "Invalid JSON" in resp.json()["detail"]
    bench = client.get(f"/benchmarks/{benchmark_id}")
    assert bench.status_code == 200
    assert bench.json()["has_dataset"] is False
