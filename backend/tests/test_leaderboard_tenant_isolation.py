"""Leaderboard tenant isolation for eval-run aggregates and caches.

Auth re-enable (#361) scoped campaigns, but GET /leaderboard/{domain}
loaded every completed EvalRun with no Campaign.tenant_id filter and
cached the result under the domain name only.

Trigger:
  Tenant A completes an EvalRun (score 0.91, cost 12.34) on shared model M.
  Tenant B GET /leaderboard/global (or /academic) sees 0.91 and 12.34.
  Because the TTL cache was keyed only by domain, B can also receive A's
  already-computed snapshot for five minutes.

Impact: Cross-tenant disclosure of evaluation scores, spend, and latency.
"""
from __future__ import annotations

import os
import sys
import time
import uuid

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-leaderboard-tenant-isolation-32b")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from api.routers import leaderboard  # noqa: E402
from core.auth import require_tenant  # noqa: E402
from core.database import get_session  # noqa: E402
from core.models import (  # noqa: E402
    Benchmark,
    BenchmarkType,
    Campaign,
    EvalRun,
    JobStatus,
    LLMModel,
    ModelProvider,
    Tenant,
)

SECRET_SCORE = 0.91
SECRET_COST = 12.34
SECRET_LATENCY = 999
OWNER_SCORE = 0.42
OWNER_COST = 0.05
OWNER_LATENCY = 100


def _setup():
    db_path = f"/tmp/leaderboard-tenant-{uuid.uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

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
        model = LLMModel(
            name="Shared Catalog Model",
            provider=ModelProvider.CUSTOM,
            model_id=f"m-{uuid.uuid4().hex[:8]}",
        )
        bench = Benchmark(
            name="mmlu",
            type=BenchmarkType.ACADEMIC,
            description="",
            tags="[]",
            config_json="{}",
            metric="accuracy",
            is_builtin=True,
            has_dataset=False,
            source="public",
        )
        session.add(tenant_a)
        session.add(tenant_b)
        session.add(model)
        session.add(bench)
        session.commit()
        session.refresh(tenant_a)
        session.refresh(tenant_b)
        session.refresh(model)
        session.refresh(bench)

        camp_a = Campaign(name="A private campaign", tenant_id=tenant_a.id)
        camp_b = Campaign(name="B private campaign", tenant_id=tenant_b.id)
        session.add(camp_a)
        session.add(camp_b)
        session.commit()
        session.refresh(camp_a)
        session.refresh(camp_b)

        session.add(
            EvalRun(
                campaign_id=camp_a.id,
                model_id=model.id,
                benchmark_id=bench.id,
                status=JobStatus.COMPLETED,
                score=SECRET_SCORE,
                total_cost_usd=SECRET_COST,
                total_latency_ms=SECRET_LATENCY,
            )
        )
        session.add(
            EvalRun(
                campaign_id=camp_b.id,
                model_id=model.id,
                benchmark_id=bench.id,
                status=JobStatus.COMPLETED,
                score=OWNER_SCORE,
                total_cost_usd=OWNER_COST,
                total_latency_ms=OWNER_LATENCY,
            )
        )
        session.commit()

        tenant_a_id = tenant_a.id
        tenant_b_id = tenant_b.id
        slug_a = tenant_a.slug
        slug_b = tenant_b.slug

    app = FastAPI()
    app.include_router(leaderboard.router)

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
    app.dependency_overrides[leaderboard.get_session] = _get_session_override
    app.dependency_overrides[leaderboard.require_tenant] = _require_tenant_override

    return app, slug_a, slug_b, tenant_a_id, tenant_b_id


def _scores_and_costs(payload: dict) -> tuple[list[float], list[float]]:
    scores = []
    costs = []
    for row in payload.get("rows") or []:
        if row.get("avg_score") is not None:
            scores.append(row["avg_score"])
        costs.append(row.get("total_cost_usd"))
        for value in (row.get("scores") or {}).values():
            if value is not None:
                scores.append(value)
    return scores, costs


def test_leaderboard_hides_other_tenant_scores_and_cost():
    app, slug_a, slug_b, _, _ = _setup()
    client = TestClient(app)

    resp_b = client.get("/leaderboard/global", headers={"X-Tenant-Key": slug_b})
    assert resp_b.status_code == 200, resp_b.text
    body_b = resp_b.json()
    scores_b, costs_b = _scores_and_costs(body_b)
    assert SECRET_SCORE not in scores_b
    assert SECRET_COST not in costs_b
    assert OWNER_SCORE in scores_b
    assert OWNER_COST in costs_b
    assert body_b["total_runs"] == 1

    resp_a = client.get("/leaderboard/global", headers={"X-Tenant-Key": slug_a})
    assert resp_a.status_code == 200, resp_a.text
    body_a = resp_a.json()
    scores_a, costs_a = _scores_and_costs(body_a)
    assert OWNER_SCORE not in scores_a
    assert OWNER_COST not in costs_a
    assert SECRET_SCORE in scores_a
    assert SECRET_COST in costs_a
    assert body_a["total_runs"] == 1


def test_leaderboard_cache_does_not_bleed_across_tenants():
    """Tenant A warming the TTL cache must not serve A's snapshot to Tenant B."""
    leaderboard._leaderboard_cache.clear()
    app, slug_a, slug_b, _, _ = _setup()
    client = TestClient(app)

    first = client.get("/leaderboard/global", headers={"X-Tenant-Key": slug_a})
    assert first.status_code == 200, first.text
    assert first.json()["total_runs"] == 1
    assert SECRET_SCORE in _scores_and_costs(first.json())[0]

    second = client.get("/leaderboard/global", headers={"X-Tenant-Key": slug_b})
    assert second.status_code == 200, second.text
    scores_b, costs_b = _scores_and_costs(second.json())
    assert SECRET_SCORE not in scores_b
    assert SECRET_COST not in costs_b
    assert OWNER_SCORE in scores_b
    assert second.json()["total_runs"] == 1


def test_report_cache_does_not_bleed_across_tenants():
    leaderboard._report_cache.clear()
    app, slug_a, slug_b, tenant_a_id, _ = _setup()
    client = TestClient(app)

    leaked = leaderboard.DomainReport(
        domain="global",
        label="Global",
        content_markdown="Tenant A secret ranking: score 0.91 cost 12.34",
        generated_at="2026-08-22T00:00:00+00:00",
        model_used="test",
    )
    leaderboard._report_cache[leaderboard._cache_key(tenant_a_id, "global")] = leaked

    resp_b = client.get("/leaderboard/global/report", headers={"X-Tenant-Key": slug_b})
    assert resp_b.status_code == 200, resp_b.text
    assert resp_b.json() is None

    resp_a = client.get("/leaderboard/global/report", headers={"X-Tenant-Key": slug_a})
    assert resp_a.status_code == 200, resp_a.text
    assert "0.91" in resp_a.json()["content_markdown"]


def test_get_domain_runs_sql_excludes_foreign_tenant():
    db_path = f"/tmp/leaderboard-helper-{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        tenant_a = Tenant(name="HA", slug=f"ha-{uuid.uuid4().hex[:8]}", api_key_hash="ha")
        tenant_b = Tenant(name="HB", slug=f"hb-{uuid.uuid4().hex[:8]}", api_key_hash="hb")
        model = LLMModel(name="M", provider=ModelProvider.CUSTOM, model_id=f"hm-{uuid.uuid4().hex[:8]}")
        bench = Benchmark(name="gpqa", type=BenchmarkType.ACADEMIC)
        session.add_all([tenant_a, tenant_b, model, bench])
        session.commit()
        session.refresh(tenant_a)
        session.refresh(tenant_b)
        session.refresh(model)
        session.refresh(bench)
        camp_a = Campaign(name="ca", tenant_id=tenant_a.id)
        camp_b = Campaign(name="cb", tenant_id=tenant_b.id)
        session.add_all([camp_a, camp_b])
        session.commit()
        session.refresh(camp_a)
        session.refresh(camp_b)
        session.add(
            EvalRun(
                campaign_id=camp_a.id,
                model_id=model.id,
                benchmark_id=bench.id,
                status=JobStatus.COMPLETED,
                score=SECRET_SCORE,
                total_cost_usd=SECRET_COST,
                total_latency_ms=SECRET_LATENCY,
            )
        )
        session.add(
            EvalRun(
                campaign_id=camp_b.id,
                model_id=model.id,
                benchmark_id=bench.id,
                status=JobStatus.COMPLETED,
                score=OWNER_SCORE,
                total_cost_usd=OWNER_COST,
                total_latency_ms=OWNER_LATENCY,
            )
        )
        session.commit()

        runs_b, _, _ = leaderboard._get_domain_runs("global", session, tenant_b.id)
        assert len(runs_b) == 1
        assert runs_b[0].score == OWNER_SCORE
        assert runs_b[0].total_cost_usd == OWNER_COST

        runs_a, _, _ = leaderboard._get_domain_runs("global", session, tenant_a.id)
        assert len(runs_a) == 1
        assert runs_a[0].score == SECRET_SCORE


def test_cache_key_includes_tenant():
    assert leaderboard._cache_key(1, "global") != leaderboard._cache_key(2, "global")
    assert leaderboard._cache_key(1, "global") == "1:global"


def test_cache_ttl_still_hits_same_tenant():
    """Same-tenant second GET within TTL must not recompute (cache still works)."""
    leaderboard._leaderboard_cache.clear()
    app, slug_a, _, _, _ = _setup()
    client = TestClient(app)

    first = client.get("/leaderboard/global", headers={"X-Tenant-Key": slug_a})
    assert first.status_code == 200
    cached_ts = None
    with leaderboard._leaderboard_cache_lock:
        for key, (ts, data) in leaderboard._leaderboard_cache.items():
            if key.endswith(":global"):
                cached_ts = ts
                break
    assert cached_ts is not None

    time.sleep(0.01)
    second = client.get("/leaderboard/global", headers={"X-Tenant-Key": slug_a})
    assert second.status_code == 200
    with leaderboard._leaderboard_cache_lock:
        later_ts = None
        for key, (ts, _data) in leaderboard._leaderboard_cache.items():
            if key.endswith(":global"):
                later_ts = ts
                break
    assert later_ts == cached_ts
