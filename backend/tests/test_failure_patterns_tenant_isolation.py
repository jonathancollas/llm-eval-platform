"""Failure-patterns tenant isolation.

Auth re-enable (#361) scoped campaigns, but /api/failure-patterns kept
process-global in-memory queues with no require_tenant. Cluster IDs are
derived from client-supplied campaign_id (``cluster_{campaign_id}_{idx}``),
so tenants collide on the same keys.

Trigger: Tenant A clusters failures containing secret prompts → queued.
Tenant B calls GET /failure-patterns/pending (or confirm/reject/retire)
and reads or mutates Tenant A's traces.

Impact: Cross-tenant disclosure of failure prompts/responses; cross-tenant
confirm/reject/retire of another tenant's validation gate state.
"""
from __future__ import annotations

import os
import sys
import uuid

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-failure-patterns-tenant-32b")

import importlib.util  # noqa: E402

from core.auth import require_tenant  # noqa: E402
from core.models import Tenant  # noqa: E402

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
FP_PATH = os.path.join(BACKEND_DIR, "api", "routers", "failure_patterns.py")
_spec = importlib.util.spec_from_file_location("failure_patterns_tenant_isolation_module", FP_PATH)
fp = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(fp)


def _setup():
    db_path = f"/tmp/failure-patterns-tenant-{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        tenant_a = Tenant(name="Tenant A", slug=f"ta-{uuid.uuid4().hex[:8]}", api_key_hash="a")
        tenant_b = Tenant(name="Tenant B", slug=f"tb-{uuid.uuid4().hex[:8]}", api_key_hash="b")
        session.add(tenant_a)
        session.add(tenant_b)
        session.commit()
        session.refresh(tenant_a)
        session.refresh(tenant_b)
        ids = {
            "tenant_a_slug": tenant_a.slug,
            "tenant_b_slug": tenant_b.slug,
            "tenant_a_id": tenant_a.id,
            "tenant_b_id": tenant_b.id,
        }

    fp._reset_stores()

    # Seed Tenant A's pending queue with a secret failure trace.
    # Use the same cluster_id shape the engine emits so Tenant B's collision
    # attempt would have hit the global store before this fix.
    secret_cluster_id = "cluster_42_000"
    fp._pending_for(ids["tenant_a_id"])[secret_cluster_id] = {
        "cluster_id": secret_cluster_id,
        "name": "Tenant A secret cluster",
        "failure_type": "novel",
        "representative_traces": [
            {
                "prompt": "TENANT-A-SECRET-FAILURE-PROMPT",
                "response": "TENANT-A-SECRET-FAILURE-RESPONSE",
            }
        ],
        "campaign_id": 42,
        "tenant_id": ids["tenant_a_id"],
        "status": "pending_review",
    }
    # Also seed a confirmed taxonomy entry for retire isolation.
    secret_pattern_id = str(uuid.uuid4())
    fp._taxonomy_for(ids["tenant_a_id"])[secret_pattern_id] = {
        "pattern_id": secret_pattern_id,
        "cluster_id": "cluster_42_001",
        "name": "Tenant A secret pattern",
        "tenant_id": ids["tenant_a_id"],
        "status": "confirmed",
        "representative_traces": [{"prompt": "TENANT-A-TAXONOMY-SECRET"}],
    }
    ids["secret_cluster_id"] = secret_cluster_id
    ids["secret_pattern_id"] = secret_pattern_id

    app = FastAPI()
    app.include_router(fp.router)

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
            )

    from core.database import get_session

    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[require_tenant] = _require_tenant_override
    # The router imported require_tenant into its own module namespace.
    app.dependency_overrides[fp.require_tenant] = _require_tenant_override

    client = TestClient(app)
    return client, ids, engine


def test_pending_hides_other_tenant_clusters():
    client, ids, _ = _setup()
    r = client.get(
        "/failure-patterns/pending",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    blob = str(body)
    assert "TENANT-A-SECRET-FAILURE-PROMPT" not in blob
    assert "TENANT-A-SECRET-FAILURE-RESPONSE" not in blob


def test_owner_can_see_own_pending():
    client, ids, _ = _setup()
    r = client.get(
        "/failure-patterns/pending",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert "TENANT-A-SECRET-FAILURE-PROMPT" in str(body)


def test_taxonomy_hides_other_tenant_patterns():
    client, ids, _ = _setup()
    r = client.get(
        "/failure-patterns/taxonomy",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert "TENANT-A-TAXONOMY-SECRET" not in str(body)


def test_confirm_other_tenant_cluster_is_404():
    client, ids, _ = _setup()
    r = client.post(
        f"/failure-patterns/{ids['secret_cluster_id']}/confirm",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={"reviewer": "attacker"},
    )
    assert r.status_code == 404
    # Owner's pending entry must still be present.
    assert ids["secret_cluster_id"] in fp._pending_for(ids["tenant_a_id"])


def test_reject_other_tenant_cluster_is_404():
    client, ids, _ = _setup()
    r = client.post(
        f"/failure-patterns/{ids['secret_cluster_id']}/reject",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={"reviewer": "attacker", "reason": "steal"},
    )
    assert r.status_code == 404
    assert ids["secret_cluster_id"] in fp._pending_for(ids["tenant_a_id"])
    assert ids["secret_cluster_id"] not in fp._rejected_for(ids["tenant_b_id"])


def test_retire_other_tenant_pattern_is_404():
    client, ids, _ = _setup()
    r = client.delete(
        f"/failure-patterns/taxonomy/{ids['secret_pattern_id']}",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 404
    assert ids["secret_pattern_id"] in fp._taxonomy_for(ids["tenant_a_id"])


def test_same_cluster_id_does_not_collide_across_tenants():
    """Tenant B can queue the same cluster_id without seeing/clobbering A."""
    client, ids, _ = _setup()
    cid = ids["secret_cluster_id"]
    fp._pending_for(ids["tenant_b_id"])[cid] = {
        "cluster_id": cid,
        "name": "Tenant B own cluster",
        "representative_traces": [{"prompt": "TENANT-B-OWN-PROMPT"}],
        "tenant_id": ids["tenant_b_id"],
        "status": "pending_review",
    }

    r_a = client.get(
        "/failure-patterns/pending",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    r_b = client.get(
        "/failure-patterns/pending",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r_a.status_code == 200 and r_b.status_code == 200
    assert "TENANT-A-SECRET-FAILURE-PROMPT" in str(r_a.json())
    assert "TENANT-B-OWN-PROMPT" in str(r_b.json())
    assert "TENANT-A-SECRET-FAILURE-PROMPT" not in str(r_b.json())
    assert "TENANT-B-OWN-PROMPT" not in str(r_a.json())


def test_cluster_queues_under_calling_tenant_only():
    client, ids, _ = _setup()
    failures = [
        {
            "prompt": f"tenant-b novel xyzzy failure {i}",
            "response": f"tenant-b novel xyzzy response {i}",
            "model_name": "m",
            "score": 0.1,
            "severity": "high",
            "category": "novel",
        }
        for i in range(5)
    ]
    r = client.post(
        "/failure-patterns/cluster",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={
            "failures": failures,
            "campaign_id": 42,  # same campaign_id → same cluster id shape as A's seed
            "similarity_threshold": 0.1,
            "min_cluster_size": 2,
        },
    )
    assert r.status_code == 200
    # Tenant A pending must still contain the secret and only A's entries.
    pending_a = client.get(
        "/failure-patterns/pending",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    ).json()
    assert "TENANT-A-SECRET-FAILURE-PROMPT" in str(pending_a)
    assert "tenant-b novel xyzzy" not in str(pending_a).lower()
