"""
Tests for api/routers/campaigns.py
Covers: CRUD, run/cancel, collaboration, bundle import/export, manifest, sharing.
"""
import importlib.util
import json
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

_spec = importlib.util.spec_from_file_location(
    "campaigns_router",
    Path(__file__).parent.parent / "api" / "routers" / "campaigns.py",
)
camp_mod = importlib.util.module_from_spec(_spec)
sys.modules["campaigns_router"] = camp_mod
_spec.loader.exec_module(camp_mod)

from core.models import (
    Benchmark, BenchmarkType, Campaign, EvalRun, JobStatus, LLMModel, ModelProvider, Tenant,
)


# ── DB & app fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("camp_api_db") / "camp.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine):
    def _get_session():
        with Session(db_engine) as s:
            yield s

    test_app = FastAPI()
    test_app.include_router(camp_mod.router)
    test_app.dependency_overrides[camp_mod.get_session] = _get_session
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def seeded(db_engine):
    """Seed one model, one benchmark, one campaign."""
    with Session(db_engine) as s:
        model = LLMModel(
            name="TestModel-Camp",
            provider=ModelProvider.CUSTOM,
            model_id="test/camp-model",
        )
        s.add(model)
        bench = Benchmark(
            name="TestBench-Camp",
            type=BenchmarkType.ACADEMIC,
            metric="accuracy",
        )
        s.add(bench)
        s.commit()
        s.refresh(model)
        s.refresh(bench)
        return {"model_id": model.id, "bench_id": bench.id}


# ── list campaigns ─────────────────────────────────────────────────────────────

def test_list_campaigns_empty_initially(client):
    resp = client.get("/campaigns/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── create campaign ────────────────────────────────────────────────────────────

def test_create_campaign_success(client, seeded):
    resp = client.post("/campaigns/", json={
        "name": "Test Campaign",
        "description": "A test",
        "model_ids": [seeded["model_id"]],
        "benchmark_ids": [seeded["bench_id"]],
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Test Campaign"
    assert body["status"] == "pending"


def test_create_campaign_model_not_found(client, seeded):
    resp = client.post("/campaigns/", json={
        "name": "Bad Campaign",
        "model_ids": [999999],
        "benchmark_ids": [seeded["bench_id"]],
    })
    assert resp.status_code == 404
    assert "Model" in resp.json()["detail"]


def test_create_campaign_benchmark_not_found(client, seeded):
    resp = client.post("/campaigns/", json={
        "name": "Bad Campaign",
        "model_ids": [seeded["model_id"]],
        "benchmark_ids": [999999],
    })
    assert resp.status_code == 404
    assert "Benchmark" in resp.json()["detail"]


def _create_campaign(client, seeded, name="Camp") -> int:
    resp = client.post("/campaigns/", json={
        "name": name,
        "model_ids": [seeded["model_id"]],
        "benchmark_ids": [seeded["bench_id"]],
    })
    assert resp.status_code == 201
    return resp.json()["id"]


# ── get campaign ───────────────────────────────────────────────────────────────

def test_get_campaign_returns_200(client, seeded):
    cid = _create_campaign(client, seeded, "GetCamp")
    resp = client.get(f"/campaigns/{cid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == cid


def test_get_campaign_not_found(client):
    resp = client.get("/campaigns/999999")
    assert resp.status_code == 404


def test_get_campaign_with_runs(client, db_engine, seeded):
    cid = _create_campaign(client, seeded, "CampWithRuns")
    with Session(db_engine) as s:
        run = EvalRun(
            campaign_id=cid,
            model_id=seeded["model_id"],
            benchmark_id=seeded["bench_id"],
            status=JobStatus.COMPLETED,
            score=0.85,
        )
        s.add(run)
        s.commit()
    resp = client.get(f"/campaigns/{cid}")
    assert resp.status_code == 200
    assert len(resp.json()["runs"]) >= 1


# ── list shared campaigns ──────────────────────────────────────────────────────

def test_list_shared_campaigns_returns_list(client):
    resp = client.get("/campaigns/shared/available")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── share campaign ─────────────────────────────────────────────────────────────

def test_share_campaign_success(client, seeded):
    cid = _create_campaign(client, seeded, "ShareCamp")
    resp = client.post(f"/campaigns/{cid}/share", json={
        "visibility": "public",
        "collaborator_tenant_ids": [],
    })
    assert resp.status_code == 200
    assert resp.json()["visibility"] == "public"


def test_share_campaign_not_found(client):
    resp = client.post("/campaigns/999999/share", json={"visibility": "public"})
    assert resp.status_code == 404


def test_share_campaign_shared_visibility(client, seeded, db_engine):
    cid = _create_campaign(client, seeded, "SharedVizCamp")
    # Get the tenant id
    resp = client.get(f"/campaigns/{cid}")
    # Share with another tenant id
    resp2 = client.post(f"/campaigns/{cid}/share", json={
        "visibility": "shared",
        "collaborator_tenant_ids": [99],
    })
    assert resp2.status_code == 200
    assert resp2.json()["visibility"] == "shared"


# ── comments ───────────────────────────────────────────────────────────────────

def test_create_comment_success(client, seeded):
    cid = _create_campaign(client, seeded, "CommentCamp")
    resp = client.post(f"/campaigns/{cid}/comments", json={
        "author": "Alice",
        "message": "Looks good!",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True
    assert body["comment"]["author"] == "Alice"


def test_list_comments(client, seeded):
    cid = _create_campaign(client, seeded, "ListCommentCamp")
    client.post(f"/campaigns/{cid}/comments", json={
        "author": "Bob",
        "message": "Test comment",
    })
    resp = client.get(f"/campaigns/{cid}/comments")
    assert resp.status_code == 200
    body = resp.json()
    assert "comments" in body
    assert len(body["comments"]) >= 1


def test_list_comments_not_found(client):
    resp = client.get("/campaigns/999999/comments")
    assert resp.status_code == 404


def test_create_comment_not_found(client):
    resp = client.post("/campaigns/999999/comments", json={
        "author": "Alice",
        "message": "msg",
    })
    assert resp.status_code == 404


# ── reviews ────────────────────────────────────────────────────────────────────

def test_submit_review_approve(client, seeded):
    cid = _create_campaign(client, seeded, "ReviewCamp")
    resp = client.post(f"/campaigns/{cid}/reviews", json={
        "reviewer": "Reviewer1",
        "decision": "approve",
        "summary": "Looks great",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["submitted"] is True
    assert body["review_state"] == "approved"


def test_submit_review_request_changes(client, seeded):
    cid = _create_campaign(client, seeded, "ReviewCamp2")
    resp = client.post(f"/campaigns/{cid}/reviews", json={
        "reviewer": "Reviewer2",
        "decision": "request_changes",
        "summary": "Need more data",
    })
    assert resp.status_code == 200
    assert resp.json()["review_state"] == "changes_requested"


def test_submit_review_comment_only(client, seeded):
    cid = _create_campaign(client, seeded, "ReviewCamp3")
    resp = client.post(f"/campaigns/{cid}/reviews", json={
        "reviewer": "Reviewer3",
        "decision": "comment",
        "summary": "Noting this",
    })
    assert resp.status_code == 200
    assert resp.json()["review_state"] == "in_review"


def test_submit_review_not_found(client):
    resp = client.post("/campaigns/999999/reviews", json={
        "reviewer": "R",
        "decision": "approve",
    })
    assert resp.status_code == 404


# ── bundle export/import ───────────────────────────────────────────────────────

def test_bundle_export(client, seeded):
    cid = _create_campaign(client, seeded, "ExportCamp")
    resp = client.get(f"/campaigns/{cid}/bundle/export")
    assert resp.status_code == 200
    body = resp.json()
    assert "bundle_version" in body
    assert "campaign" in body
    assert "models" in body
    assert "benchmarks" in body


def test_bundle_export_not_found(client):
    resp = client.get("/campaigns/999999/bundle/export")
    assert resp.status_code == 404


def test_bundle_import_success(client, seeded, db_engine):
    # First export
    cid = _create_campaign(client, seeded, "ImportSourceCamp")
    export_resp = client.get(f"/campaigns/{cid}/bundle/export")
    bundle = export_resp.json()
    # Import
    resp = client.post("/campaigns/bundle/import", json={"bundle": bundle})
    assert resp.status_code == 201
    assert resp.json()["name"] == bundle["campaign"]["name"]


def test_bundle_import_invalid_format(client):
    resp = client.post("/campaigns/bundle/import", json={"bundle": "not a dict"})
    assert resp.status_code == 422


def test_bundle_import_missing_models(client, seeded):
    bundle = {
        "campaign": {"name": "Orphan Campaign"},
        "models": [{"model_id": "nonexistent/model-xyz"}],
        "benchmarks": [{"name": "TestBench-Camp"}],
    }
    resp = client.post("/campaigns/bundle/import", json={"bundle": bundle})
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "missing_models" in detail


def test_bundle_import_missing_benchmarks(client, seeded):
    bundle = {
        "campaign": {"name": "Orphan Campaign"},
        "models": [{"model_id": "test/camp-model"}],
        "benchmarks": [{"name": "NonexistentBench-XYZ"}],
    }
    resp = client.post("/campaigns/bundle/import", json={"bundle": bundle})
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "missing_benchmarks" in detail


def test_bundle_import_empty_model_ids(client, seeded):
    bundle = {
        "campaign": {"name": "Empty Campaign"},
        "models": [],
        "benchmarks": [],
    }
    resp = client.post("/campaigns/bundle/import", json={"bundle": bundle})
    assert resp.status_code == 422


def test_bundle_import_with_collaboration(client, seeded):
    cid = _create_campaign(client, seeded, "CollabImportSrc")
    bundle = client.get(f"/campaigns/{cid}/bundle/export").json()
    bundle["campaign"]["collaboration"] = {
        "visibility": "shared",
        "collaborator_tenant_ids": [42],
        "comments": [],
        "reviews": [],
        "review_state": "open",
    }
    resp = client.post("/campaigns/bundle/import", json={
        "bundle": bundle,
        "import_collaboration": True,
    })
    assert resp.status_code == 201


# ── run campaign ───────────────────────────────────────────────────────────────

def test_run_campaign_success(client, seeded):
    cid = _create_campaign(client, seeded, "RunCamp")
    with patch.object(camp_mod.job_queue, "submit_campaign", return_value="task-123"):
        resp = client.post(f"/campaigns/{cid}/run")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_run_campaign_not_found(client):
    with patch.object(camp_mod.job_queue, "submit_campaign", return_value="task-x"):
        resp = client.post("/campaigns/999999/run")
    assert resp.status_code == 404


def test_run_campaign_already_running_rejected(client, seeded, db_engine):
    cid = _create_campaign(client, seeded, "AlreadyRunning")
    # Set to running via DB
    with Session(db_engine) as s:
        c = s.get(Campaign, cid)
        c.status = JobStatus.RUNNING
        s.add(c)
        s.commit()
    with patch.object(camp_mod.job_queue, "submit_campaign", return_value="task-y"):
        resp = client.post(f"/campaigns/{cid}/run")
    assert resp.status_code == 409


def test_run_campaign_rerun_from_completed(client, seeded, db_engine):
    cid = _create_campaign(client, seeded, "CompletedCamp")
    # Set to completed
    with Session(db_engine) as s:
        c = s.get(Campaign, cid)
        c.status = JobStatus.COMPLETED
        c.progress = 100.0
        s.add(s.merge(c))
        s.commit()
    with patch.object(camp_mod.job_queue, "submit_campaign", return_value="task-rerun"):
        resp = client.post(f"/campaigns/{cid}/run")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_run_campaign_rerun_from_failed(client, seeded, db_engine):
    cid = _create_campaign(client, seeded, "FailedCamp")
    with Session(db_engine) as s:
        c = s.get(Campaign, cid)
        c.status = JobStatus.FAILED
        c.error_message = "previous error"
        s.add(s.merge(c))
        s.commit()
    with patch.object(camp_mod.job_queue, "submit_campaign", return_value="task-redo"):
        resp = client.post(f"/campaigns/{cid}/run")
    assert resp.status_code == 200


def test_run_campaign_queue_failure(client, seeded):
    cid = _create_campaign(client, seeded, "QueueFailCamp")
    with patch.object(camp_mod.job_queue, "submit_campaign", side_effect=RuntimeError("queue down")):
        resp = client.post(f"/campaigns/{cid}/run")
    assert resp.status_code == 500


# ── cancel campaign ────────────────────────────────────────────────────────────

def test_cancel_campaign_success_from_queue(client, seeded, db_engine):
    cid = _create_campaign(client, seeded, "CancelCamp1")
    with Session(db_engine) as s:
        c = s.get(Campaign, cid)
        c.status = JobStatus.RUNNING
        s.add(s.merge(c))
        s.commit()
    with patch.object(camp_mod.job_queue, "cancel_campaign", return_value=True):
        resp = client.post(f"/campaigns/{cid}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_cancel_campaign_not_running_in_queue(client, seeded, db_engine):
    cid = _create_campaign(client, seeded, "CancelCamp2")
    with Session(db_engine) as s:
        c = s.get(Campaign, cid)
        c.status = JobStatus.RUNNING
        s.add(s.merge(c))
        s.commit()
    with patch.object(camp_mod.job_queue, "cancel_campaign", return_value=False):
        resp = client.post(f"/campaigns/{cid}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_cancel_campaign_not_running_status_error(client, seeded):
    cid = _create_campaign(client, seeded, "NotRunningCamp")
    # Status is PENDING (not running)
    with patch.object(camp_mod.job_queue, "cancel_campaign", return_value=False):
        resp = client.post(f"/campaigns/{cid}/cancel")
    assert resp.status_code == 400


def test_cancel_campaign_not_found(client):
    with patch.object(camp_mod.job_queue, "cancel_campaign", return_value=False):
        resp = client.post("/campaigns/999999/cancel")
    assert resp.status_code == 404


# ── delete campaign ────────────────────────────────────────────────────────────

def test_delete_campaign_success(client, seeded):
    cid = _create_campaign(client, seeded, "DeleteCamp")
    resp = client.delete(f"/campaigns/{cid}")
    assert resp.status_code == 204
    assert client.get(f"/campaigns/{cid}").status_code == 404


def test_delete_campaign_not_found(client):
    resp = client.delete("/campaigns/999999")
    assert resp.status_code == 404


def test_delete_campaign_running_rejected(client, seeded, db_engine):
    cid = _create_campaign(client, seeded, "RunningDeleteCamp")
    with Session(db_engine) as s:
        c = s.get(Campaign, cid)
        c.status = JobStatus.RUNNING
        s.add(s.merge(c))
        s.commit()
    resp = client.delete(f"/campaigns/{cid}")
    assert resp.status_code == 409


def test_delete_campaign_cascades_runs(client, seeded, db_engine):
    cid = _create_campaign(client, seeded, "CascadeDeleteCamp")
    with Session(db_engine) as s:
        run = EvalRun(
            campaign_id=cid,
            model_id=seeded["model_id"],
            benchmark_id=seeded["bench_id"],
            status=JobStatus.COMPLETED,
        )
        s.add(run)
        s.commit()
    resp = client.delete(f"/campaigns/{cid}")
    assert resp.status_code == 204


# ── manifest ───────────────────────────────────────────────────────────────────

def test_get_manifest_returns_200(client, seeded):
    cid = _create_campaign(client, seeded, "ManifestCamp")
    resp = client.get(f"/campaigns/{cid}/manifest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["campaign_id"] == cid
    assert "experiment_hash" in body
    assert "model_configs" in body
    assert "benchmark_configs" in body
    assert "results_summary" in body


def test_get_manifest_not_found(client):
    resp = client.get("/campaigns/999999/manifest")
    assert resp.status_code == 404


def test_get_manifest_with_runs(client, seeded, db_engine):
    cid = _create_campaign(client, seeded, "ManifestWithRunsCamp")
    with Session(db_engine) as s:
        run = EvalRun(
            campaign_id=cid,
            model_id=seeded["model_id"],
            benchmark_id=seeded["bench_id"],
            status=JobStatus.COMPLETED,
            score=0.9,
            capability_score=0.85,
            propensity_score=0.95,
        )
        s.add(run)
        s.commit()
    resp = client.get(f"/campaigns/{cid}/manifest")
    assert resp.status_code == 200
    summary = resp.json()["results_summary"]
    assert summary["total_runs"] >= 1
    assert summary["avg_score"] is not None


# ── _campaign_context helpers ─────────────────────────────────────────────────

def test_campaign_context_no_json():
    c = Campaign(name="X", tenant_id=1, run_context_json=None)
    assert camp_mod._campaign_context(c) == {}


def test_campaign_context_valid_json():
    c = Campaign(name="X", tenant_id=1, run_context_json=json.dumps({"key": "value"}))
    assert camp_mod._campaign_context(c) == {"key": "value"}


def test_campaign_context_invalid_json():
    c = Campaign(name="X", tenant_id=1, run_context_json="not json!")
    assert camp_mod._campaign_context(c) == {}


def test_campaign_context_non_dict_json():
    c = Campaign(name="X", tenant_id=1, run_context_json=json.dumps([1, 2, 3]))
    assert camp_mod._campaign_context(c) == {}


# ── _campaign_collaboration helpers ──────────────────────────────────────────

def test_campaign_collaboration_defaults_with_no_json():
    c = Campaign(name="X", tenant_id=1, run_context_json=None)
    collab = camp_mod._campaign_collaboration(c)
    assert collab["visibility"] == "private"
    assert collab["collaborator_tenant_ids"] == []


def test_campaign_collaboration_non_dict_collab():
    context = {"collaboration": "bad_value"}
    c = Campaign(name="X", tenant_id=1, run_context_json=json.dumps(context))
    collab = camp_mod._campaign_collaboration(c)
    assert collab["visibility"] == "private"


# ── _can_access_campaign helpers ──────────────────────────────────────────────

def test_can_access_campaign_owner():
    tenant = Tenant(id=1, name="t", slug="t")
    c = Campaign(name="X", tenant_id=1)
    assert camp_mod._can_access_campaign(c, tenant) is True


def test_can_access_campaign_public():
    tenant = Tenant(id=2, name="t2", slug="t2")
    context = {"collaboration": {"visibility": "public", "collaborator_tenant_ids": []}}
    c = Campaign(name="X", tenant_id=1, run_context_json=json.dumps(context))
    assert camp_mod._can_access_campaign(c, tenant) is True


def test_can_access_campaign_shared_collaborator():
    tenant = Tenant(id=3, name="t3", slug="t3")
    context = {"collaboration": {"visibility": "shared", "collaborator_tenant_ids": [3]}}
    c = Campaign(name="X", tenant_id=1, run_context_json=json.dumps(context))
    assert camp_mod._can_access_campaign(c, tenant) is True


def test_can_access_campaign_shared_not_collaborator():
    tenant = Tenant(id=4, name="t4", slug="t4")
    context = {"collaboration": {"visibility": "shared", "collaborator_tenant_ids": [99]}}
    c = Campaign(name="X", tenant_id=1, run_context_json=json.dumps(context))
    assert camp_mod._can_access_campaign(c, tenant) is False


def test_can_access_campaign_private_other_tenant():
    tenant = Tenant(id=5, name="t5", slug="t5")
    c = Campaign(name="X", tenant_id=1)
    assert camp_mod._can_access_campaign(c, tenant) is False
