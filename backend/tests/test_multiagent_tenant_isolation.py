"""Multi-agent simulation tenant isolation.

Auth re-enable (#361) scoped campaigns, but /api/multiagent simulation and
sandbagging report endpoints never gained require_tenant checks. Any caller
who listed simulations or fetched by ID could read another tenant's injection
step traces and objectives.
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
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-multiagent-tenant-isolation-32b")

import importlib.util  # noqa: E402

from core.auth import require_tenant  # noqa: E402
from core.models import (  # noqa: E402
    Benchmark,
    BenchmarkType,
    LLMModel,
    ModelProvider,
    MultiAgentSimulation,
    SandbaggingReport,
    Tenant,
)

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
MULTIAGENT_PATH = os.path.join(BACKEND_DIR, "api", "routers", "multiagent.py")
_spec = importlib.util.spec_from_file_location(
    "multiagent_tenant_isolation_module", MULTIAGENT_PATH
)
multiagent = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(multiagent)


def _setup():
    db_path = f"/tmp/multiagent-tenant-{uuid.uuid4().hex}.db"
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

        steps = [
            {
                "step_index": 0,
                "agent_name": "retriever",
                "agent_role": "retriever",
                "output": "TENANT-A-SECRET-INJECTION-TRACE",
                "goal_alignment": 0.1,
                "injected_payload_followed": True,
                "failure_modes": ["prompt_injection"],
                "latency_ms": 5,
                "tokens": 10,
            }
        ]
        sim = MultiAgentSimulation(
            tenant_id=tenant_a.id,
            simulation_id=f"sim-{uuid.uuid4().hex[:8]}",
            scenario_name="pipeline_injection",
            original_objective="TENANT-A-SECRET-OBJECTIVE",
            adversarial_goal="exfiltrate secrets",
            n_agents=3,
            n_steps=1,
            task_completed=False,
            final_answer="leaked",
            overall_goal_alignment=0.2,
            goal_drift_detected=True,
            prompt_injection_success_rate=1.0,
            trust_propagation_occurred=True,
            system_safety_score=0.1,
            pipeline_integrity_score=0.2,
            autonomy_level=3,
            steps_json=json.dumps(steps),
            failure_modes_json=json.dumps({"prompt_injection": 1}),
        )
        report = SandbaggingReport(
            tenant_id=tenant_a.id,
            model_id=model.id,
            benchmark_id=benchmark.id,
            n_probes=2,
            mean_sandbagging_score=0.8,
            risk_level="high",
            eval_awareness_rate=0.5,
            capability_gap=0.3,
            recommendation="TENANT-A-SECRET-SANDBAGGING",
            scientific_confidence="high",
            probes_json="[]",
        )
        session.add(sim)
        session.add(report)
        session.commit()
        session.refresh(sim)
        session.refresh(report)

        ids = {
            "tenant_a_slug": tenant_a.slug,
            "tenant_b_slug": tenant_b.slug,
            "tenant_a_id": tenant_a.id,
            "tenant_b_id": tenant_b.id,
            "model_id": model.id,
            "sim_a_id": sim.id,
            "report_a_id": report.id,
        }

    app = FastAPI()
    app.include_router(multiagent.router)

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

    app.dependency_overrides[multiagent.get_session] = _get_session_override
    app.dependency_overrides[multiagent.require_tenant] = _require_tenant_override
    app.dependency_overrides[require_tenant] = _require_tenant_override

    return TestClient(app), ids, engine


def test_list_simulations_hides_other_tenant():
    client, ids, _engine = _setup()
    r = client.get(
        "/multiagent/simulations",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 200
    assert r.json()["simulations"] == []


def test_owner_can_list_own_simulations():
    client, ids, _engine = _setup()
    r = client.get(
        "/multiagent/simulations",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert r.status_code == 200
    sims = r.json()["simulations"]
    assert len(sims) == 1
    assert sims[0]["id"] == ids["sim_a_id"]


def test_get_simulation_cross_tenant_returns_404():
    client, ids, _engine = _setup()
    r = client.get(
        f"/multiagent/simulations/{ids['sim_a_id']}",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 404
    assert "TENANT-A-SECRET" not in r.text


def test_owner_can_get_simulation_steps():
    client, ids, _engine = _setup()
    r = client.get(
        f"/multiagent/simulations/{ids['sim_a_id']}",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["original_objective"] == "TENANT-A-SECRET-OBJECTIVE"
    assert body["steps"][0]["output"] == "TENANT-A-SECRET-INJECTION-TRACE"


def test_list_sandbagging_reports_hides_other_tenant():
    client, ids, _engine = _setup()
    r = client.get(
        "/multiagent/sandbagging/reports",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 200
    assert r.json()["reports"] == []
    assert "TENANT-A-SECRET-SANDBAGGING" not in r.text


def test_owner_can_list_sandbagging_reports():
    client, ids, _engine = _setup()
    r = client.get(
        "/multiagent/sandbagging/reports",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert r.status_code == 200
    reports = r.json()["reports"]
    assert len(reports) == 1
    assert reports[0]["id"] == ids["report_a_id"]
