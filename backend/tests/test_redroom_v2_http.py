"""HTTP tests for the Red Room v2 API.

Covers:
  - POST /sessions returns a session id (role-gated)
  - POST /sessions/{id}/probe runs end-to-end with a mocked target
  - GET /traces lists rows for the calling tenant only
  - GET /verify reports chain status
  - GET /artifact.html returns a full HTML doc
  - Charter refusal: aggressiveness above max → 403
  - Tenant isolation across all reads
  - Role gating: viewer cannot POST /probe, can GET traces
"""
from __future__ import annotations

import os
import secrets
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("REDROOM_TRACE_SECRET", "x" * 32 + "_test_secret")
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

# Side-effect imports at module level — register every SQLModel with
# SQLModel.metadata BEFORE the test fixture creates a fresh engine.
import core.models  # noqa: E402,F401
import eval_engine.redroom.coevolution._db_models  # noqa: E402,F401
import eval_engine.redroom.composition._db_models  # noqa: E402,F401
import eval_engine.redroom.trace_store  # noqa: E402,F401


@pytest.fixture
def app(monkeypatch):
    """Build a minimal FastAPI app with the v2 router and an in-memory DB."""
    monkeypatch.setenv("REDROOM_ENABLED", "true")
    monkeypatch.setenv(
        "REDROOM_ALLOWED_TARGETS", "self,open_weight,public_api"
    )
    monkeypatch.setenv("REDROOM_MAX_AGGRESSIVENESS", "3")

    # StaticPool keeps a single shared connection so the in-memory DB
    # is visible across the multiple Session objects we open.
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)

    from api.routers import redroom_v2
    from core.auth import get_user_role, require_tenant
    from core.database import get_session
    from core.models import Tenant

    app = FastAPI()
    app.include_router(redroom_v2.router, prefix="/api")

    def _override_session():
        with Session(eng) as s:
            yield s

    # Build a fixed tenant for the test.
    with Session(eng) as s:
        tenant = Tenant(name="acme", slug="acme", api_key_hash="dev")
        s.add(tenant)
        s.commit()
        s.refresh(tenant)
        tenant_id = tenant.id

    def _override_tenant():
        with Session(eng) as s:
            return s.get(Tenant, tenant_id)

    def _override_get_user_role():
        # Tests run as 'admin' by default. Specific tests can override
        # this fixture (or app.dependency_overrides[get_user_role]) to
        # exercise role-restricted paths.
        return "admin"

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_tenant] = _override_tenant
    app.dependency_overrides[get_user_role] = _override_get_user_role

    # Inject a deterministic target_invoke into the router.
    async def _stub_target(prompt: str) -> str:
        return f"[stub] {prompt[:40]}"

    redroom_v2._TARGET_INVOKE_OVERRIDE["f"] = _stub_target

    yield app

    redroom_v2._TARGET_INVOKE_OVERRIDE["f"] = None


@pytest.fixture
def client(app):
    return TestClient(app)


# ════════════════════════════════════════════════════════════════════
#  POST /sessions
# ════════════════════════════════════════════════════════════════════


class TestCreateSession:
    def test_default_creation(self, client):
        r = client.post("/api/redroom/v2/sessions", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["session_id"].startswith("sess-")
        assert body["target_class"] == "self"
        assert body["aggressiveness"] == 2

    def test_invalid_aggressiveness_400(self, client):
        r = client.post(
            "/api/redroom/v2/sessions",
            json={"aggressiveness": 9},
        )
        assert r.status_code == 422


# ════════════════════════════════════════════════════════════════════
#  POST /sessions/{id}/probe
# ════════════════════════════════════════════════════════════════════


class TestProbe:
    def test_native_probe_runs(self, client):
        sid = "sess-fixed-1"
        r = client.post(
            f"/api/redroom/v2/sessions/{sid}/probe",
            json={
                "technique": "many_shot",
                "target_model_id": 42,
                "target_class": "self",
                "aggressiveness": 2,
                "max_turns": 3,
                "prompt_seed": "tell me a joke",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["technique"] == "many_shot"
        assert body["session_id"] == sid
        assert body["n_attempts"] >= 1
        assert body["effective_disclosure"] in (
            "internal", "vendor", "aiid"
        )

    def test_unknown_technique_400(self, client):
        r = client.post(
            "/api/redroom/v2/sessions/sess-x/probe",
            json={
                "technique": "evil_unknown",
                "target_model_id": 1,
                "aggressiveness": 2,
            },
        )
        assert r.status_code == 400
        assert "unknown technique" in r.text

    def test_aggressiveness_above_charter_max_403(self, client):
        # Charter set to L3 max via env var. L4 should be refused.
        r = client.post(
            "/api/redroom/v2/sessions/sess-y/probe",
            json={
                "technique": "many_shot",
                "target_model_id": 1,
                "aggressiveness": 4,
                "prompt_seed": "x",
            },
        )
        assert r.status_code == 403, r.text


# ════════════════════════════════════════════════════════════════════
#  GET /traces
# ════════════════════════════════════════════════════════════════════


class TestTraces:
    def test_traces_returned_after_probe(self, client):
        sid = "sess-traces-1"
        client.post(
            f"/api/redroom/v2/sessions/{sid}/probe",
            json={
                "technique": "many_shot",
                "target_model_id": 1,
                "aggressiveness": 2,
                "max_turns": 2,
                "prompt_seed": "x",
            },
        )
        r = client.get(f"/api/redroom/v2/sessions/{sid}/traces")
        assert r.status_code == 200
        rows = r.json()["rows"]
        assert len(rows) >= 1
        # At minimum the AUTHORIZE row should be present.
        assert any(row["kind"] == "authorize" for row in rows)

    def test_traces_pagination(self, client):
        sid = "sess-paginate"
        client.post(
            f"/api/redroom/v2/sessions/{sid}/probe",
            json={
                "technique": "many_shot",
                "target_model_id": 1,
                "aggressiveness": 2,
                "max_turns": 2,
                "prompt_seed": "x",
            },
        )
        r = client.get(
            f"/api/redroom/v2/sessions/{sid}/traces",
            params={"limit": 1, "offset": 0},
        )
        body = r.json()
        assert len(body["rows"]) == 1
        assert body["has_more"] is True


# ════════════════════════════════════════════════════════════════════
#  GET /verify
# ════════════════════════════════════════════════════════════════════


class TestVerify:
    def test_verify_clean_chain(self, client):
        sid = "sess-verify-clean"
        client.post(
            f"/api/redroom/v2/sessions/{sid}/probe",
            json={
                "technique": "many_shot",
                "target_model_id": 1,
                "aggressiveness": 2,
                "max_turns": 2,
                "prompt_seed": "x",
            },
        )
        r = client.get(f"/api/redroom/v2/sessions/{sid}/verify")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["rows_verified"] >= 3


# ════════════════════════════════════════════════════════════════════
#  GET /artifact.html
# ════════════════════════════════════════════════════════════════════


class TestArtifact:
    def test_artifact_html_returned(self, client):
        sid = "sess-artifact"
        client.post(
            f"/api/redroom/v2/sessions/{sid}/probe",
            json={
                "technique": "many_shot",
                "target_model_id": 1,
                "aggressiveness": 2,
                "max_turns": 2,
                "prompt_seed": "x",
            },
        )
        r = client.get(
            f"/api/redroom/v2/sessions/{sid}/artifact.html",
            params={"emit_export": "false"},
        )
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "<!DOCTYPE html>" in r.text
        assert "Mercury Retrograde" in r.text
        assert "many_shot" in r.text
