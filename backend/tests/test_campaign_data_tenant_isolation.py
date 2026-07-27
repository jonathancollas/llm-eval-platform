"""Tenant isolation for reports / judge / genome campaign data endpoints.

Same IDOR class as results.py: campaign-scoped reads/writes that never called
require_tenant, so any caller who knows a campaign (or report/run) ID could
exfiltrate another tenant's prompts, scores, and report markdown.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.routers import genome, judge, reports  # noqa: E402
from core.auth import require_tenant  # noqa: E402
from core.database import get_session  # noqa: E402
from core.models import (  # noqa: E402
    Benchmark,
    BenchmarkType,
    Campaign,
    EvalResult,
    EvalRun,
    JobStatus,
    JudgeEvaluation,
    LLMModel,
    ModelProvider,
    Report,
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
            score=0.8,
            num_items=1,
            total_latency_ms=120,
        )
        session.add(run)
        session.commit()
        session.refresh(run)

        result = EvalResult(
            run_id=run.id,
            item_index=0,
            prompt="secret prompt",
            response="secret response",
            expected="expected",
            score=0.8,
            latency_ms=120,
        )
        session.add(result)
        session.commit()
        session.refresh(result)

        report = Report(
            campaign_id=campaign.id,
            title="Secret report",
            content_markdown="## Leaked findings\nsecret analysis",
            model_used="test-model",
        )
        session.add(report)

        je = JudgeEvaluation(
            campaign_id=campaign.id,
            run_id=run.id,
            result_id=result.id,
            judge_model="test-judge",
            judge_score=0.9,
            judge_reasoning="secret judge notes",
        )
        session.add(je)
        session.commit()
        session.refresh(report)

        return {
            "campaign_id": campaign.id,
            "run_id": run.id,
            "report_id": report.id,
        }


def _build_app(*routers):
    db_path = Path("/tmp") / f"campaign-data-tenant-{uuid.uuid4().hex}.db"
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


def test_reports_list_and_export_require_tenant_access():
    app, ids = _build_app(reports)
    client = TestClient(app)

    owner = client.get(
        f"/reports/campaign/{ids['campaign_id']}",
        headers={"X-Tenant-Key": "tenant-a"},
    )
    assert owner.status_code == 200, owner.text
    assert owner.json()[0]["content_markdown"].startswith("## Leaked findings")

    other = client.get(
        f"/reports/campaign/{ids['campaign_id']}",
        headers={"X-Tenant-Key": "tenant-b"},
    )
    assert other.status_code == 404

    other_export = client.get(
        f"/reports/{ids['report_id']}/export.md",
        headers={"X-Tenant-Key": "tenant-b"},
    )
    assert other_export.status_code == 404

    owner_export = client.get(
        f"/reports/{ids['report_id']}/export.md",
        headers={"X-Tenant-Key": "tenant-a"},
    )
    assert owner_export.status_code == 200
    assert "secret analysis" in owner_export.text


def test_judge_summary_requires_tenant_access():
    app, ids = _build_app(judge)
    client = TestClient(app)

    owner = client.get(
        f"/judge/summary/{ids['campaign_id']}",
        headers={"X-Tenant-Key": "tenant-a"},
    )
    assert owner.status_code == 200, owner.text
    assert owner.json()["computed"] is True
    assert "test-judge" in owner.json()["judges"]

    other = client.get(
        f"/judge/summary/{ids['campaign_id']}",
        headers={"X-Tenant-Key": "tenant-b"},
    )
    assert other.status_code == 404

    other_bias = client.get(
        f"/judge/bias/{ids['campaign_id']}",
        headers={"X-Tenant-Key": "tenant-b"},
    )
    assert other_bias.status_code == 404


def test_genome_campaign_and_signals_require_tenant_access():
    app, ids = _build_app(genome)
    client = TestClient(app)

    owner = client.get(
        f"/genome/campaigns/{ids['campaign_id']}",
        headers={"X-Tenant-Key": "tenant-a"},
    )
    assert owner.status_code == 200, owner.text

    other = client.get(
        f"/genome/campaigns/{ids['campaign_id']}",
        headers={"X-Tenant-Key": "tenant-b"},
    )
    assert other.status_code == 404

    other_signals = client.get(
        f"/genome/signals/{ids['run_id']}",
        headers={"X-Tenant-Key": "tenant-b"},
    )
    assert other_signals.status_code == 404

    other_compute = client.post(
        f"/genome/campaigns/{ids['campaign_id']}/compute",
        headers={"X-Tenant-Key": "tenant-b"},
    )
    assert other_compute.status_code == 404
