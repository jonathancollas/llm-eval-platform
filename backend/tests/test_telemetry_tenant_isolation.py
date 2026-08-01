"""Telemetry tenant isolation for monitoring + research ingest/read paths.

TelemetryEvent already had a tenant_id column, but ingest never stamped it and
read/dashboard/report paths never filtered on it. Any caller with a valid (or
default) tenant key could read another tenant's production safety flags,
latency, scores, and drift aggregates — including via a fleet cache keyed only
by window_hours.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from datetime import datetime, UTC

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-telemetry-tenant-isolation-32b")

from core.auth import require_tenant  # noqa: E402
from core.models import TelemetryEvent, Tenant  # noqa: E402

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")


def _load_module(name: str, rel_path: str):
    path = os.path.join(BACKEND_DIR, rel_path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


monitoring = _load_module("monitoring_tenant_isolation_module", "api/routers/monitoring.py")
research = _load_module("research_tenant_isolation_module", "api/routers/research.py")


def _seed(engine):
    with Session(engine) as session:
        tenant_a = Tenant(
            name="Tenant A",
            slug=f"ta-{uuid.uuid4().hex[:8]}",
            api_key_hash="hash-a",
        )
        tenant_b = Tenant(
            name="Tenant B",
            slug=f"tb-{uuid.uuid4().hex[:8]}",
            api_key_hash="hash-b",
        )
        session.add(tenant_a)
        session.add(tenant_b)
        session.commit()
        session.refresh(tenant_a)
        session.refresh(tenant_b)

        secret = TelemetryEvent(
            tenant_id=tenant_a.id,
            model_id=None,
            event_type="inference",
            prompt_hash="aaaa1111bbbb2222",
            response_hash="cccc3333dddd4444",
            score=0.11,
            latency_ms=1234,
            safety_flag="injection_detected",
            deployment_context="production",
            model_version="tenant-a-secret-model",
            timestamp=datetime.now(UTC),
        )
        session.add(secret)
        session.commit()
        session.refresh(secret)

        return {
            "tenant_a_slug": tenant_a.slug,
            "tenant_b_slug": tenant_b.slug,
            "tenant_a_id": tenant_a.id,
            "tenant_b_id": tenant_b.id,
            "event_a_id": secret.id,
        }


def _setup():
    db_path = f"/tmp/telemetry-tenant-{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    ids = _seed(engine)

    app = FastAPI()
    app.include_router(monitoring.router, prefix="/api")
    app.include_router(research.router, prefix="/api")

    def _get_session_override():
        with Session(engine) as session:
            yield session

    def _require_tenant_override(
        tenant_key: str | None = Header(default=None, alias="X-Tenant-Key"),
    ):
        if not tenant_key:
            raise HTTPException(status_code=401, detail="X-Tenant-Key header required.")
        with Session(engine) as session:
            tenant = session.exec(select(Tenant).where(Tenant.slug == tenant_key)).first()
            if not tenant:
                raise HTTPException(status_code=401, detail="Invalid tenant.")
            return Tenant(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                api_key_hash=tenant.api_key_hash,
                is_active=tenant.is_active,
            )

    app.dependency_overrides[monitoring.get_session] = _get_session_override
    app.dependency_overrides[research.get_session] = _get_session_override
    app.dependency_overrides[monitoring.require_tenant] = _require_tenant_override
    app.dependency_overrides[research.require_tenant] = _require_tenant_override
    app.dependency_overrides[require_tenant] = _require_tenant_override

    with monitoring._fleet_cache_lock:
        monitoring._fleet_cache.clear()

    return TestClient(app), engine, ids


def test_monitoring_feed_hides_other_tenant_events():
    client, _engine, ids = _setup()
    r = client.get(
        "/api/monitoring/telemetry",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 200
    events = r.json()["events"]
    assert all(e["id"] != ids["event_a_id"] for e in events)
    assert all(e.get("safety_flag") != "injection_detected" for e in events)


def test_monitoring_stats_do_not_count_other_tenant():
    client, _engine, ids = _setup()
    r = client.get(
        "/api/monitoring/stats",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 200
    assert r.json()["n"] == 0


def test_monitoring_owner_can_see_own_events():
    client, _engine, ids = _setup()
    r = client.get(
        "/api/monitoring/telemetry",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert r.status_code == 200
    event_ids = {e["id"] for e in r.json()["events"]}
    assert ids["event_a_id"] in event_ids


def test_monitoring_ingest_stamps_tenant_id():
    client, engine, ids = _setup()
    r = client.post(
        "/api/monitoring/ingest",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={
            "event_type": "inference",
            "prompt": "hello from b",
            "response": "world",
            "score": 0.9,
            "latency_ms": 10,
            "safety_flag": "refusal",
        },
    )
    assert r.status_code == 201
    event_id = r.json()["event_id"]

    with Session(engine) as session:
        row = session.get(TelemetryEvent, event_id)
        assert row is not None
        assert row.tenant_id == ids["tenant_b_id"]

    feed_a = client.get(
        "/api/monitoring/telemetry",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert event_id not in {e["id"] for e in feed_a.json()["events"]}


def test_research_telemetry_dashboard_isolated():
    client, _engine, ids = _setup()
    r_b = client.get(
        "/api/research/telemetry/dashboard",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r_b.status_code == 200
    assert r_b.json()["total_events"] == 0

    r_a = client.get(
        "/api/research/telemetry/dashboard",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert r_a.status_code == 200
    assert r_a.json()["total_events"] == 1
    assert r_a.json()["safety_flag_rate"] == 1.0


def test_research_telemetry_ingest_stamps_tenant_id():
    client, engine, ids = _setup()
    r = client.post(
        "/api/research/telemetry/ingest",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={
            "events": [
                {
                    "event_type": "inference",
                    "prompt_hash": "bbbb",
                    "response_hash": "cccc",
                    "score": 0.5,
                    "latency_ms": 5,
                    "safety_flag": "hallucination",
                }
            ]
        },
    )
    assert r.status_code == 200
    assert r.json()["ingested"] == 1

    with Session(engine) as session:
        rows = session.exec(
            select(TelemetryEvent).where(TelemetryEvent.tenant_id == ids["tenant_b_id"])
        ).all()
        assert len(rows) == 1
        assert rows[0].safety_flag == "hallucination"

    dash_a = client.get(
        "/api/research/telemetry/dashboard",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert dash_a.json()["total_events"] == 1
    assert "hallucination" not in dash_a.json().get("safety_flags_by_type", {})
