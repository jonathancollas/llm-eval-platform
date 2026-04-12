import os
import secrets
import sys
import importlib.util
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from core.models import LLMModel

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
MODELS_PATH = os.path.join(BACKEND_DIR, "api", "routers", "models.py")
_spec = importlib.util.spec_from_file_location("models_router_module", MODELS_PATH)
models = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(models)


@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("models_concurrency") / "models.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine):
    def _get_session_override():
        with Session(db_engine) as session:
            yield session

    test_app = FastAPI()
    test_app.include_router(models.router)
    test_app.dependency_overrides[models.get_session] = _get_session_override
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


def _payload():
    return {
        "name": "Concurrent Import Model",
        "provider": "custom",
        "model_id": "provider/concurrent-model",
        "context_length": 4096,
        "cost_input_per_1k": 0.0,
        "cost_output_per_1k": 0.0,
        "tags": [],
        "notes": "",
    }


def test_parallel_model_creation_is_deduplicated(client, db_engine):
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(client.post, "/models/", json=_payload()) for _ in range(8)]
        responses = [future.result() for future in futures]

    created = [r for r in responses if r.status_code == 201]
    conflicts = [r for r in responses if r.status_code == 409]
    assert len(created) == 1
    assert len(conflicts) == 7

    with Session(db_engine) as session:
        rows = session.exec(select(LLMModel).where(LLMModel.model_id == _payload()["model_id"])).all()
        assert len(rows) == 1
