import importlib.util
import os
import secrets
import sys
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

BACKEND_DIR = Path(__file__).resolve().parent.parent
BENCHMARKS_PATH = BACKEND_DIR / "api" / "routers" / "benchmarks.py"
_spec = importlib.util.spec_from_file_location("benchmarks_router_module", BENCHMARKS_PATH)
benchmarks = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(benchmarks)


@pytest.fixture(scope="module")
def test_dirs(tmp_path_factory):
    root = tmp_path_factory.mktemp("uploads_http")
    return {"bench_library": root / "bench_library", "db_path": root / "uploads.db"}


@pytest.fixture(scope="module")
def db_engine(test_dirs):
    engine = create_engine(f"sqlite:///{test_dirs['db_path']}", connect_args={"check_same_thread": False})
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
    response = client.post(
        "/benchmarks/",
        json={
            "name": f"upload-security-{uuid.uuid4().hex[:8]}",
            "type": "custom",
            "description": "upload security test",
            "tags": [],
            "metric": "accuracy",
            "config": {},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_oversized_upload_returns_413(client, benchmark_id):
    content = b"x" * (50 * 1024 * 1024 + 1)
    files = {"file": ("dataset.json", content, "application/json")}
    response = client.post(f"/benchmarks/{benchmark_id}/upload-dataset", files=files)
    assert response.status_code == 413


def test_path_traversal_filename_returns_400(client, benchmark_id):
    files = {"file": ("../../escape.json", b'[{"prompt":"p","answer":"a"}]', "application/json")}
    response = client.post(f"/benchmarks/{benchmark_id}/upload-dataset", files=files)
    assert response.status_code == 400
    assert "Invalid file path" in response.json()["detail"]


def test_wrong_mime_type_returns_415(client, benchmark_id):
    files = {"file": ("dataset.json", b'[{"prompt":"p","answer":"a"}]', "application/pdf")}
    response = client.post(f"/benchmarks/{benchmark_id}/upload-dataset", files=files)
    assert response.status_code == 415
