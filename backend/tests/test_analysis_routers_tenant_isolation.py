"""Tenant isolation for remaining campaign-scoped analysis routers.

Same IDOR class as results/reports/judge/genome: campaign-scoped endpoints that
never called require_tenant, so any caller who knows a campaign ID could read
another tenant's prompts, responses, event payloads, and analysis outputs.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.routers import events  # noqa: E402
from api.routers import policy  # noqa: E402
from api.routers import reward_hacking  # noqa: E402
from api.routers import scenarios  # noqa: E402
from api.routers import science  # noqa: E402
from core.auth import require_tenant  # noqa: E402
from core.database import get_session  # noqa: E402
from core.models import (  # noqa: E402
    Benchmark,
    BenchmarkType,
    Campaign,
    EvalEventRecord,
    EvalResult,
    EvalRun,
    JobStatus,
    JudgeEvaluation,
    LLMModel,
    ModelProvider,
    Tenant,
)


def _seed(engine):
    with Session(engine) as session:
        tenant_a = Tenant(name="Tenant A", slug="tenant-a", api_key_hash="a")
        tenant_b = Tenant(name="Tenant B", slug="tenant-b", api_key_hash="b")
        model = LLMModel(
            name="m1",
            provider=ModelProvider.CUSTOM,
            model_id=f"m-{uuid.uuid4().hex[:8]}",
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
        session.refresh(model)
        session.refresh(benchmark)

        campaign = Campaign(
            tenant_id=tenant_a.id,
            name="A campaign",
            description="",
            model_ids=f"[{model.id}]",
            benchmark_ids=f"[{benchmark.id}]",
            status=JobStatus.COMPLETED,
            progress=1.0,
        )
        session.add(campaign)
        session.commit()
        session.refresh(campaign)

        run = EvalRun(
            campaign_id=campaign.id,
            model_id=model.id,
            benchmark_id=benchmark.id,
            status=JobStatus.COMPLETED,
            score=0.2,
            num_items=1,
            total_latency_ms=120,
        )
        session.add(run)
        session.commit()
        session.refresh(run)

        result = EvalResult(
            run_id=run.id,
            item_index=0,
            prompt="secret prompt for tenant A",
            response="secret response for tenant A",
            expected="expected",
            score=0.2,
            latency_ms=120,
        )
        session.add(result)
        session.commit()
        session.refresh(result)

        je = JudgeEvaluation(
            campaign_id=campaign.id,
            run_id=run.id,
            result_id=result.id,
            judge_model="test-judge",
            judge_score=0.9,
            judge_reasoning="secret judge notes",
        )
        session.add(je)

        event = EvalEventRecord(
            event_id=str(uuid.uuid4()),
            campaign_id=campaign.id,
            event_type="campaign.started",
            sequence=1,
            timestamp=datetime.utcnow(),
            run_id=run.id,
            model_id=model.id,
            benchmark_id=benchmark.id,
            payload_json=json.dumps({"secret": "tenant-a-event-payload"}),
        )
        session.add(event)
        session.commit()

        return {
            "campaign_id": campaign.id,
            "run_id": run.id,
        }


def _build_app(*routers):
    db_path = Path("/tmp") / f"analysis-tenant-{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    ids = _seed(engine)

    app = FastAPI()
    for r in routers:
        app.include_router(r.router)

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
            return tenant

    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[require_tenant] = _require_tenant_override
    return app, ids


def test_events_require_tenant_access():
    app, ids = _build_app(events)
    client = TestClient(app)
    cid = ids["campaign_id"]

    owner = client.get(f"/events/campaign/{cid}", headers={"X-Tenant-Key": "tenant-a"})
    assert owner.status_code == 200, owner.text
    assert owner.json()["total_events"] == 1
    assert owner.json()["events"][0]["payload"]["secret"] == "tenant-a-event-payload"

    other = client.get(f"/events/campaign/{cid}", headers={"X-Tenant-Key": "tenant-b"})
    assert other.status_code == 404

    other_timeline = client.get(
        f"/events/campaign/{cid}/timeline",
        headers={"X-Tenant-Key": "tenant-b"},
    )
    assert other_timeline.status_code == 404


def test_science_contamination_requires_tenant_access():
    app, ids = _build_app(science)
    client = TestClient(app)
    cid = ids["campaign_id"]

    owner = client.get(
        f"/science/contamination/campaign/{cid}",
        headers={"X-Tenant-Key": "tenant-a"},
    )
    assert owner.status_code == 200, owner.text
    assert owner.json()["campaign_id"] == cid

    other = client.get(
        f"/science/contamination/campaign/{cid}",
        headers={"X-Tenant-Key": "tenant-b"},
    )
    assert other.status_code == 404


def test_scenarios_bias_report_requires_tenant_access():
    app, ids = _build_app(scenarios)
    client = TestClient(app)
    cid = ids["campaign_id"]

    owner = client.get(
        f"/scenarios/bias/report/{cid}",
        headers={"X-Tenant-Key": "tenant-a"},
    )
    assert owner.status_code == 200, owner.text
    assert owner.json()["campaign_id"] == cid

    other = client.get(
        f"/scenarios/bias/report/{cid}",
        headers={"X-Tenant-Key": "tenant-b"},
    )
    assert other.status_code == 404


def test_reward_hacking_campaign_requires_tenant_access():
    app, ids = _build_app(reward_hacking)
    client = TestClient(app)
    cid = ids["campaign_id"]

    owner = client.get(
        f"/reward-hacking/analyze/campaign/{cid}",
        headers={"X-Tenant-Key": "tenant-a"},
    )
    assert owner.status_code == 200, owner.text
    assert owner.json()["campaign_id"] == cid

    other = client.get(
        f"/reward-hacking/analyze/campaign/{cid}",
        headers={"X-Tenant-Key": "tenant-b"},
    )
    assert other.status_code == 404

    other_run = client.post(
        f"/reward-hacking/analyze/run/{ids['run_id']}",
        headers={"X-Tenant-Key": "tenant-b"},
    )
    assert other_run.status_code == 404


def test_policy_evaluate_requires_tenant_access():
    app, ids = _build_app(policy)
    client = TestClient(app)
    cid = ids["campaign_id"]

    owner = client.post(
        "/policy/evaluate",
        headers={"X-Tenant-Key": "tenant-a"},
        json={"campaign_id": cid, "policy_id": "eu_ai_act"},
    )
    assert owner.status_code == 200, owner.text
    assert owner.json()["campaign_id"] == cid

    other = client.post(
        "/policy/evaluate",
        headers={"X-Tenant-Key": "tenant-b"},
        json={"campaign_id": cid, "policy_id": "eu_ai_act"},
    )
    assert other.status_code == 404
