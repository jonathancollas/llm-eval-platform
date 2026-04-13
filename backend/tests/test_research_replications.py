import importlib.util
import os
import secrets
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
RESEARCH_PATH = os.path.join(BACKEND_DIR, "api", "routers", "research.py")
_spec = importlib.util.spec_from_file_location("research_router_module", RESEARCH_PATH)
research = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(research)


@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("research_replications_test") / "research_replications.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine):
    def _get_session_override():
        with Session(db_engine) as session:
            yield session

    test_app = FastAPI()
    test_app.include_router(research.router)
    test_app.dependency_overrides[research.get_session] = _get_session_override
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def workspace_id(client):
    response = client.post(
        "/research/workspaces",
        json={
            "name": "Replication Workspace",
            "description": "workflow test",
            "hypothesis": "replication should be tracked",
            "protocol": "same setup",
            "risk_domain": "capability",
            "visibility": "private",
            "tags": [],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_replication_request_rejects_workspace_id_mismatch(client, workspace_id):
    response = client.post(
        f"/research/workspaces/{workspace_id}/replications",
        json={"workspace_id": workspace_id + 1, "replicating_lab": "Lab Mismatch", "notes": ""},
    )
    assert response.status_code == 400
    assert "mismatch" in response.text.lower()


def test_replication_request_is_idempotent_for_pending_lab(client, workspace_id):
    payload = {"workspace_id": workspace_id, "replicating_lab": "Lab A", "notes": "first request"}
    first = client.post(f"/research/workspaces/{workspace_id}/replications", json=payload)
    second = client.post(f"/research/workspaces/{workspace_id}/replications", json=payload)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    listing = client.get(f"/research/workspaces/{workspace_id}/replications")
    assert listing.status_code == 200, listing.text
    labs = [r["lab"] for r in listing.json()["replications"] if r.get("status") == "pending"]
    assert labs.count("Lab A") == 1


def test_submit_replication_computes_concordance_and_confidence(client, workspace_id):
    request_b = client.post(
        f"/research/workspaces/{workspace_id}/replications",
        json={"workspace_id": workspace_id, "replicating_lab": "Lab B", "notes": "second request"},
    )
    assert request_b.status_code == 200, request_b.text

    submit_a = client.post(
        f"/research/workspaces/{workspace_id}/replications/submit",
        json={
            "workspace_id": workspace_id,
            "replicating_lab": "Lab A",
            "concordance_score": 0.92,
            "successful": True,
            "delta_capability": 0.01,
            "delta_propensity": 0.02,
            "notes": "close match",
        },
    )
    assert submit_a.status_code == 200, submit_a.text
    assert submit_a.json()["scientific_confidence"]["n_successful_replications"] == 1
    assert submit_a.json()["scientific_confidence"]["n_failed_replications"] == 0

    submit_b = client.post(
        f"/research/workspaces/{workspace_id}/replications/submit",
        json={
            "workspace_id": workspace_id,
            "replicating_lab": "Lab B",
            "successful": False,
            "delta_capability": 0.4,
            "delta_propensity": 0.2,
            "notes": "distribution shift",
        },
    )
    assert submit_b.status_code == 200, submit_b.text
    body = submit_b.json()
    assert body["n_replications"] == 2
    assert body["n_successful"] == 1
    assert body["n_failed"] == 1
    assert body["scientific_confidence_grade"] == "C"
    assert body["avg_concordance"] == pytest.approx(0.81, abs=1e-9)

    listing = client.get(f"/research/workspaces/{workspace_id}/replications")
    assert listing.status_code == 200, listing.text
    summary = listing.json()["summary"]
    assert summary["successful"] == 1
    assert summary["failed"] == 1
    assert summary["mean_concordance"] == pytest.approx(0.81, abs=1e-9)
    assert summary["confidence_grade"] == "C"
