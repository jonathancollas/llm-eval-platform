"""Capability router tenant isolation for eval-run aggregates.

Auth re-enable (#361) scoped campaigns, but /capability/profile|gaps|
cross-benchmark|heatmap|coverage|scores loaded every EvalRun for a model_id
with no campaign.tenant_id filter. Two tenants evaluating the same shared
model therefore mixed private scores (and coverage) into each other's
capability views.

Trigger:
  Tenant A completes an EvalRun (score 0.91) on shared model M.
  Tenant B GET /capability/profile/{M} (and heatmap/coverage/gaps/
  cross-benchmark/scores) sees 0.91 mixed into B's aggregates.

Impact: Cross-tenant disclosure of evaluation scores used for capability
profiles, coverage heatmaps, and gap analysis.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import uuid

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-capability-tenant-isolation-32b")

from core.auth import require_tenant  # noqa: E402
from core.models import (  # noqa: E402
    Benchmark,
    BenchmarkType,
    Campaign,
    CapabilityDomainRecord,
    CapabilityEvalScore,
    CapabilitySubCapabilityRecord,
    EvalRun,
    JobStatus,
    LLMModel,
    ModelProvider,
    Tenant,
)

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
SECRET_SCORE = 0.91
OWNER_OWN_SCORE = 0.42


def _load_module(name: str, rel_path: str):
    path = os.path.join(BACKEND_DIR, rel_path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


capability = _load_module(
    "capability_tenant_isolation_module",
    "api/routers/capability.py",
)


def _setup():
    db_path = f"/tmp/capability-tenant-{uuid.uuid4().hex}.db"
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
            name="shared-gpt",
            provider=ModelProvider.CUSTOM,
            model_id=f"m-{uuid.uuid4().hex[:8]}",
        )
        benchmark = Benchmark(
            name="Safety Refusals",
            type=BenchmarkType.SAFETY,
            metric="safety_score",
        )
        safety_domain = CapabilityDomainRecord(
            slug="safety",
            display_name="Safety",
            description="Safety capabilities",
            sort_order=0,
        )
        session.add(tenant_a)
        session.add(tenant_b)
        session.add(model)
        session.add(benchmark)
        session.add(safety_domain)
        session.commit()
        session.refresh(tenant_a)
        session.refresh(tenant_b)
        session.refresh(model)
        session.refresh(benchmark)
        session.refresh(safety_domain)

        refusal_sc = CapabilitySubCapabilityRecord(
            domain_id=safety_domain.id,
            slug="refusal",
            display_name="Refusal",
            description="Refuse harmful requests",
            difficulty="medium",
            risk_level="critical",
        )
        session.add(refusal_sc)
        session.commit()
        session.refresh(refusal_sc)

        campaign_a = Campaign(
            name="Secret campaign A",
            description="tenant-a-only",
            model_ids=f"[{model.id}]",
            benchmark_ids=f"[{benchmark.id}]",
            tenant_id=tenant_a.id,
            status=JobStatus.COMPLETED,
        )
        campaign_b = Campaign(
            name="Campaign B",
            description="tenant-b-own",
            model_ids=f"[{model.id}]",
            benchmark_ids=f"[{benchmark.id}]",
            tenant_id=tenant_b.id,
            status=JobStatus.COMPLETED,
        )
        session.add(campaign_a)
        session.add(campaign_b)
        session.commit()
        session.refresh(campaign_a)
        session.refresh(campaign_b)

        run_a = EvalRun(
            campaign_id=campaign_a.id,
            model_id=model.id,
            benchmark_id=benchmark.id,
            status=JobStatus.COMPLETED,
            score=SECRET_SCORE,
        )
        run_b = EvalRun(
            campaign_id=campaign_b.id,
            model_id=model.id,
            benchmark_id=benchmark.id,
            status=JobStatus.COMPLETED,
            score=OWNER_OWN_SCORE,
        )
        session.add(run_a)
        session.add(run_b)
        session.commit()
        session.refresh(run_a)
        session.refresh(run_b)

        ids = {
            "tenant_a_slug": tenant_a.slug,
            "tenant_b_slug": tenant_b.slug,
            "model_id": model.id,
            "run_a_id": run_a.id,
            "run_b_id": run_b.id,
            "sub_capability_id": refusal_sc.id,
        }

    app = FastAPI()
    app.include_router(capability.router)

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
    app.dependency_overrides[capability.require_tenant] = _require_tenant_override

    client = TestClient(app)
    return client, ids, engine


def _header(ids, which: str) -> dict[str, str]:
    return {"X-Tenant-Key": ids[f"tenant_{which}_slug"]}


def test_profile_hides_other_tenant_eval_scores():
    client, ids, _ = _setup()
    r = client.get(
        f"/capability/profile/{ids['model_id']}",
        headers=_header(ids, "b"),
    )
    assert r.status_code == 200, r.text
    body = str(r.json())
    assert str(SECRET_SCORE) not in body
    assert str(OWNER_OWN_SCORE) in body


def test_owner_profile_includes_own_eval_scores():
    client, ids, _ = _setup()
    r = client.get(
        f"/capability/profile/{ids['model_id']}",
        headers=_header(ids, "a"),
    )
    assert r.status_code == 200, r.text
    body = str(r.json())
    assert str(SECRET_SCORE) in body
    assert str(OWNER_OWN_SCORE) not in body


def test_gaps_do_not_treat_foreign_runs_as_coverage():
    """Tenant B's own 0.42 run covers safety; A's 0.91 must not change B's gaps."""
    client, ids, _ = _setup()
    r_b = client.get(
        f"/capability/gaps/{ids['model_id']}",
        headers=_header(ids, "b"),
    )
    r_a = client.get(
        f"/capability/gaps/{ids['model_id']}",
        headers=_header(ids, "a"),
    )
    assert r_b.status_code == 200, r_b.text
    assert r_a.status_code == 200, r_a.text
    # Both tenants have one Safety Refusals run, so gap sets should match
    # in structure — and neither response may mention the other's score.
    assert str(SECRET_SCORE) not in str(r_b.json())
    assert str(OWNER_OWN_SCORE) not in str(r_a.json())


def test_cross_benchmark_hides_foreign_scores():
    client, ids, _ = _setup()
    r = client.get(
        f"/capability/cross-benchmark/{ids['model_id']}",
        headers=_header(ids, "b"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    scores = body.get("scores") or []
    assert SECRET_SCORE not in scores
    assert OWNER_OWN_SCORE in scores or body.get("mean_score") == OWNER_OWN_SCORE


def test_heatmap_hides_foreign_eval_run_coverage():
    client, ids, _ = _setup()
    r_b = client.get("/capability/heatmap", headers=_header(ids, "b"))
    r_a = client.get("/capability/heatmap", headers=_header(ids, "a"))
    assert r_b.status_code == 200, r_b.text
    assert r_a.status_code == 200, r_a.text
    mid = str(ids["model_id"])
    scores_b = r_b.json()["scores"].get(mid, {})
    scores_a = r_a.json()["scores"].get(mid, {})
    assert SECRET_SCORE not in scores_b.values()
    assert OWNER_OWN_SCORE not in scores_a.values()
    # Each tenant should see their own inferred safety-refusal coverage.
    assert OWNER_OWN_SCORE in scores_b.values() or any(
        v == OWNER_OWN_SCORE for v in scores_b.values()
    )
    assert SECRET_SCORE in scores_a.values() or any(
        v == SECRET_SCORE for v in scores_a.values()
    )


def test_coverage_does_not_credit_foreign_runs():
    client, ids, _ = _setup()
    r_b = client.get("/capability/coverage", headers=_header(ids, "b"))
    r_a = client.get("/capability/coverage", headers=_header(ids, "a"))
    assert r_b.status_code == 200, r_b.text
    assert r_a.status_code == 200, r_a.text
    assert str(SECRET_SCORE) not in str(r_b.json())
    assert str(OWNER_OWN_SCORE) not in str(r_a.json())
    entry_b = next(m for m in r_b.json()["models"] if m["model_id"] == ids["model_id"])
    entry_a = next(m for m in r_a.json()["models"] if m["model_id"] == ids["model_id"])
    # Both have one inferred capability from their own Safety Refusals run.
    assert entry_b["evaluated_count"] == entry_a["evaluated_count"]
    assert entry_b["evaluated_count"] >= 1


def test_persisted_score_tied_to_foreign_run_is_hidden():
    client, ids, engine = _setup()
    with Session(engine) as session:
        session.add(
            CapabilityEvalScore(
                model_id=ids["model_id"],
                sub_capability_id=ids["sub_capability_id"],
                eval_run_id=ids["run_a_id"],
                score=SECRET_SCORE,
                n_items=10,
            )
        )
        session.commit()

    r = client.get(
        f"/capability/scores/{ids['model_id']}",
        headers=_header(ids, "b"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert all(row["score"] != SECRET_SCORE for row in body["scores"])


def test_owner_can_read_own_persisted_score():
    client, ids, engine = _setup()
    with Session(engine) as session:
        session.add(
            CapabilityEvalScore(
                model_id=ids["model_id"],
                sub_capability_id=ids["sub_capability_id"],
                eval_run_id=ids["run_a_id"],
                score=SECRET_SCORE,
                n_items=10,
            )
        )
        session.commit()

    r = client.get(
        f"/capability/scores/{ids['model_id']}",
        headers=_header(ids, "a"),
    )
    assert r.status_code == 200, r.text
    scores = [row["score"] for row in r.json()["scores"]]
    assert SECRET_SCORE in scores
    # recorded_at is serialized as scored_at without crashing
    assert all("scored_at" in row for row in r.json()["scores"])


def test_missing_tenant_key_is_rejected_when_overridden():
    client, ids, _ = _setup()
    r = client.get(f"/capability/profile/{ids['model_id']}")
    assert r.status_code == 401
