import asyncio
import importlib.util
import os
import secrets
import sys
import types
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from core.models import Benchmark, BenchmarkType, LLMModel, ModelProvider

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
CAMPAIGNS_PATH = os.path.join(BACKEND_DIR, "api", "routers", "campaigns.py")
_spec = importlib.util.spec_from_file_location("campaigns_router_module", CAMPAIGNS_PATH)
campaigns = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(campaigns)


@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("campaigns_test") / "campaigns.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine):
    def _get_session_override():
        with Session(db_engine) as session:
            yield session

    test_app = FastAPI()
    test_app.include_router(campaigns.router)
    test_app.dependency_overrides[campaigns.get_session] = _get_session_override
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def seeded_ids(db_engine):
    with Session(db_engine) as session:
        model = LLMModel(name="Test Model", provider=ModelProvider.CUSTOM, model_id="provider/test-model")
        benchmark = Benchmark(name="Test Benchmark", type=BenchmarkType.CUSTOM, is_builtin=False, config_json="{}")
        session.add(model)
        session.add(benchmark)
        session.commit()
        session.refresh(model)
        session.refresh(benchmark)
        return {"model_id": model.id, "benchmark_id": benchmark.id}


@pytest.fixture(autouse=True)
def patch_runner(monkeypatch):
    async def fake_execute_campaign(_: int):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            return

    fake_module = types.ModuleType("eval_engine.runner")
    fake_module.execute_campaign = fake_execute_campaign
    monkeypatch.setitem(sys.modules, "eval_engine.runner", fake_module)


def _create_campaign(client: TestClient, model_id: int, benchmark_id: int) -> int:
    response = client.post(
        "/campaigns/",
        json={
            "name": "Campaign Test",
            "description": "campaign lifecycle",
            "model_ids": [model_id],
            "benchmark_ids": [benchmark_id],
            "seed": 42,
            "temperature": 0.0,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_create_and_launch_campaign(client, seeded_ids):
    campaign_id = _create_campaign(client, seeded_ids["model_id"], seeded_ids["benchmark_id"])
    response = client.post(f"/campaigns/{campaign_id}/run")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "running"


def test_cancel_running_campaign(client, seeded_ids):
    campaign_id = _create_campaign(client, seeded_ids["model_id"], seeded_ids["benchmark_id"])
    run_response = client.post(f"/campaigns/{campaign_id}/run")
    assert run_response.status_code == 200, run_response.text

    cancel_response = client.post(f"/campaigns/{campaign_id}/cancel")
    assert cancel_response.status_code == 200, cancel_response.text
    assert cancel_response.json()["status"] == "cancelled"


def test_concurrent_launch_only_allows_one_runner(client, seeded_ids):
    campaign_id = _create_campaign(client, seeded_ids["model_id"], seeded_ids["benchmark_id"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(client.post, f"/campaigns/{campaign_id}/run") for _ in range(2)]
        responses = [f.result() for f in futures]

    status_codes = sorted([r.status_code for r in responses])
    assert status_codes == [200, 409]

    client.post(f"/campaigns/{campaign_id}/cancel")
