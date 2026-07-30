"""Agent trajectory tenant isolation.

Auth re-enable (#361) scoped campaigns, but /api/agents/* never gained
require_tenant checks. Any caller who knew a trajectory or campaign ID
could list/read/evaluate another tenant's agent thoughts, tool args,
observations, and expected answers.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-agents-tenant-isolation-32b")

import importlib.util  # noqa: E402

from core.auth import require_tenant  # noqa: E402
from core.models import (  # noqa: E402
    AgentTrajectory,
    Benchmark,
    BenchmarkType,
    Campaign,
    JobStatus,
    LLMModel,
    ModelProvider,
    Tenant,
)

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
AGENTS_PATH = os.path.join(BACKEND_DIR, "api", "routers", "agents.py")
_spec = importlib.util.spec_from_file_location("agents_tenant_isolation_module", AGENTS_PATH)
agents = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(agents)


def _setup():
    db_path = f"/tmp/agents-tenant-{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        tenant_a = Tenant(name="Tenant A", slug=f"ta-{uuid.uuid4().hex[:8]}", api_key_hash="a")
        tenant_b = Tenant(name="Tenant B", slug=f"tb-{uuid.uuid4().hex[:8]}", api_key_hash="b")
        model = LLMModel(
            name="m1",
            provider=ModelProvider.CUSTOM,
            model_id=f"m-{uuid.uuid4().hex[:8]}",
            cost_input_per_1k=0.001,
            cost_output_per_1k=0.002,
        )
        benchmark = Benchmark(
            name=f"b-{uuid.uuid4().hex[:8]}",
            type=BenchmarkType.CUSTOM,
            is_builtin=False,
        )
        session.add(tenant_a)
        session.add(tenant_b)
        session.add(model)
        session.add(benchmark)
        session.commit()
        session.refresh(tenant_a)
        session.refresh(tenant_b)
        session.refresh(model)
        session.refresh(benchmark)

        campaign_a = Campaign(
            name="Secret campaign A",
            description="tenant A only",
            model_ids=f"[{model.id}]",
            benchmark_ids=f"[{benchmark.id}]",
            tenant_id=tenant_a.id,
            status=JobStatus.COMPLETED,
        )
        session.add(campaign_a)
        session.commit()
        session.refresh(campaign_a)

        steps = [
            {
                "step_index": 0,
                "thought": "tenant A secret plan",
                "action": "tool_call",
                "tool": "search",
                "tool_args": {"q": "secret"},
                "observation": "tenant A secret observation",
                "tokens": 10,
                "latency_ms": 5,
            }
        ]
        traj = AgentTrajectory(
            tenant_id=tenant_a.id,
            campaign_id=campaign_a.id,
            model_id=model.id,
            task_description="Steal credentials from tenant A vault",
            task_type="tool_use",
            expected_answer="SECRET-ANSWER-A",
            final_answer="leaked final answer",
            num_steps=1,
            total_tokens=10,
            task_completed=True,
            steps_json=json.dumps(steps),
            score_overall=0.9,
            score_task_completion=1.0,
            score_tool_precision=0.9,
            score_planning_coherence=0.8,
            score_error_recovery=1.0,
            score_safety_compliance=0.7,
            score_cost_efficiency=0.9,
        )
        session.add(traj)
        session.commit()
        session.refresh(traj)

        ids = {
            "tenant_a_slug": tenant_a.slug,
            "tenant_b_slug": tenant_b.slug,
            "model_id": model.id,
            "campaign_a_id": campaign_a.id,
            "traj_a_id": traj.id,
        }

    app = FastAPI()
    app.include_router(agents.router)

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

    app.dependency_overrides[agents.get_session] = _get_session_override
    app.dependency_overrides[agents.require_tenant] = _require_tenant_override
    app.dependency_overrides[require_tenant] = _require_tenant_override

    return TestClient(app), ids, engine


def test_list_trajectories_hides_other_tenant():
    client, ids, _engine = _setup()
    r = client.get(
        "/agents/trajectories",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["trajectories"] == []


def test_list_by_foreign_campaign_returns_404():
    client, ids, _engine = _setup()
    r = client.get(
        f"/agents/trajectories?campaign_id={ids['campaign_a_id']}",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 404


def test_get_trajectory_cross_tenant_returns_404():
    client, ids, _engine = _setup()
    r = client.get(
        f"/agents/trajectories/{ids['traj_a_id']}",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 404


def test_owner_can_get_trajectory():
    client, ids, _engine = _setup()
    r = client.get(
        f"/agents/trajectories/{ids['traj_a_id']}",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["expected_answer"] == "SECRET-ANSWER-A"
    assert body["steps"][0]["thought"] == "tenant A secret plan"


def test_evaluate_cross_tenant_returns_404():
    client, ids, _engine = _setup()
    r = client.post(
        "/agents/evaluate",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={"trajectory_id": ids["traj_a_id"], "use_llm_judge": False},
    )
    assert r.status_code == 404


def test_create_rejects_foreign_campaign():
    client, ids, _engine = _setup()
    r = client.post(
        "/agents/trajectories",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={
            "model_id": ids["model_id"],
            "campaign_id": ids["campaign_a_id"],
            "task_description": "should fail",
            "steps": [
                {
                    "step_index": 0,
                    "thought": "x",
                    "action": "reply",
                    "observation": "y",
                    "tokens": 1,
                    "latency_ms": 1,
                }
            ],
            "final_answer": "nope",
        },
    )
    assert r.status_code == 404


def test_create_sets_tenant_and_lists_only_own():
    client, ids, engine = _setup()
    r = client.post(
        "/agents/trajectories",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={
            "model_id": ids["model_id"],
            "task_description": "tenant B private task",
            "steps": [
                {
                    "step_index": 0,
                    "thought": "b plan",
                    "action": "reply",
                    "observation": "b obs",
                    "tokens": 3,
                    "latency_ms": 2,
                }
            ],
            "final_answer": "b answer",
        },
    )
    assert r.status_code == 200
    traj_b_id = r.json()["id"]

    with Session(engine) as session:
        row = session.get(AgentTrajectory, traj_b_id)
        assert row is not None
        assert row.tenant_id is not None
        tenant_b = session.exec(
            select(Tenant).where(Tenant.slug == ids["tenant_b_slug"])
        ).first()
        assert row.tenant_id == tenant_b.id

    listed = client.get(
        "/agents/trajectories",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert listed.status_code == 200
    ids_listed = {t["id"] for t in listed.json()["trajectories"]}
    assert traj_b_id in ids_listed
    assert ids["traj_a_id"] not in ids_listed


def test_dashboard_excludes_other_tenant():
    client, ids, _engine = _setup()
    r = client.get(
        "/agents/dashboard",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 200
    assert r.json()["computed"] is False


def test_ingest_steps_cross_tenant_returns_404():
    client, ids, _engine = _setup()
    r = client.post(
        f"/agents/trajectories/{ids['traj_a_id']}/ingest-steps",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json=[{"type": "action", "output": "evil"}],
    )
    assert r.status_code == 404
