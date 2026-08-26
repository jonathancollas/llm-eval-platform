"""Tenant isolation + aggregation for model behavioral fingerprints."""
from __future__ import annotations

import importlib.util
import json
import os
import secrets
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from core.models import (  # noqa: E402
    Benchmark,
    BenchmarkType,
    Campaign,
    EvalRun,
    FailureProfile,
    JobStatus,
    LLMModel,
    ModelFingerprint,
    ModelProvider,
    Tenant,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
GENOME_PATH = BACKEND_DIR / "api" / "routers" / "genome.py"
_spec = importlib.util.spec_from_file_location("genome_router_module", GENOME_PATH)
genome = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(genome)


def _setup():
    db_path = Path("/tmp") / f"genome-fp-{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        tenant_a = Tenant(name="Tenant A", slug="tenant-a", api_key_hash="a")
        tenant_b = Tenant(name="Tenant B", slug="tenant-b", api_key_hash="b")
        model = LLMModel(
            name="shared-llama",
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
        session.refresh(tenant_b)
        session.refresh(model)
        session.refresh(benchmark)

    app = FastAPI()
    app.include_router(genome.router)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    def _require_tenant_override(tenant_key: str | None = Header(default=None, alias="X-Tenant-Key")):
        if not tenant_key:
            raise HTTPException(status_code=401, detail="X-Tenant-Key header required.")
        with Session(engine) as session:
            tenant = session.exec(select(Tenant).where(Tenant.slug == tenant_key)).first()
            if not tenant:
                raise HTTPException(status_code=401, detail="Invalid tenant.")
            return tenant

    app.dependency_overrides[genome.get_session] = _get_session_override
    app.dependency_overrides[genome.require_tenant] = _require_tenant_override
    return app, engine, tenant_a.id, tenant_b.id, model.id, benchmark.id


def _seed_campaign(
    session: Session,
    *,
    tenant_id: int,
    model_id: int,
    benchmark_id: int,
    name: str,
    genome: dict,
    score: float,
    cost: float,
) -> Campaign:
    campaign = Campaign(
        name=name,
        tenant_id=tenant_id,
        status=JobStatus.COMPLETED,
        progress=1.0,
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    run = EvalRun(
        campaign_id=campaign.id,
        model_id=model_id,
        benchmark_id=benchmark_id,
        status=JobStatus.COMPLETED,
        score=score,
        total_cost_usd=cost,
        total_latency_ms=100,
        num_items=1,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    session.add(
        FailureProfile(
            run_id=run.id,
            campaign_id=campaign.id,
            model_id=model_id,
            benchmark_id=benchmark_id,
            genome_json=json.dumps(genome),
        )
    )
    session.commit()
    return campaign


def test_fingerprint_list_and_get_are_tenant_scoped():
    app, engine, tenant_a_id, tenant_b_id, model_id, _bench_id = _setup()
    with Session(engine) as session:
        session.add(ModelFingerprint(
            tenant_id=tenant_a_id,
            model_id=model_id,
            genome_json=json.dumps({"hallucination": 0.9, "safety_bypass": 0.8}),
            stats_json=json.dumps({"num_runs": 5, "avg_score": 0.11, "total_cost_usd": 12.5}),
        ))
        session.add(ModelFingerprint(
            tenant_id=tenant_b_id,
            model_id=model_id,
            genome_json=json.dumps({"hallucination": 0.1}),
            stats_json=json.dumps({"num_runs": 1, "avg_score": 0.99, "total_cost_usd": 0.01}),
        ))
        session.commit()

    client = TestClient(app)

    list_b = client.get("/genome/models", headers={"X-Tenant-Key": "tenant-b"})
    assert list_b.status_code == 200, list_b.text
    fps_b = list_b.json()["fingerprints"]
    assert len(fps_b) == 1
    assert fps_b[0]["model_id"] == model_id
    assert fps_b[0]["genome"]["hallucination"] == 0.1
    assert fps_b[0]["stats"]["avg_score"] == 0.99
    assert fps_b[0]["stats"]["num_runs"] == 1

    get_b = client.get(f"/genome/models/{model_id}", headers={"X-Tenant-Key": "tenant-b"})
    assert get_b.status_code == 200
    assert get_b.json()["has_data"] is True
    assert get_b.json()["genome"]["hallucination"] == 0.1
    assert "safety_bypass" not in get_b.json()["genome"]

    list_a = client.get("/genome/models", headers={"X-Tenant-Key": "tenant-a"})
    assert list_a.status_code == 200
    fps_a = list_a.json()["fingerprints"]
    assert len(fps_a) == 1
    assert fps_a[0]["genome"]["hallucination"] == 0.9
    assert fps_a[0]["stats"]["total_cost_usd"] == 12.5


def test_compute_does_not_overwrite_other_tenant_or_mix_stats():
    app, engine, tenant_a_id, tenant_b_id, model_id, bench_id = _setup()
    with Session(engine) as session:
        camp_a = _seed_campaign(
            session,
            tenant_id=tenant_a_id,
            model_id=model_id,
            benchmark_id=bench_id,
            name="A eval",
            genome={"hallucination": 1.0},
            score=0.2,
            cost=9.0,
        )
        camp_b = _seed_campaign(
            session,
            tenant_id=tenant_b_id,
            model_id=model_id,
            benchmark_id=bench_id,
            name="B eval",
            genome={"hallucination": 0.0, "safety_bypass": 0.4},
            score=0.95,
            cost=0.5,
        )
        genome._update_model_fingerprints(camp_a.id, session, tenant_id=tenant_a_id)
        genome._update_model_fingerprints(camp_b.id, session, tenant_id=tenant_b_id)

        fp_a = session.exec(
            select(ModelFingerprint).where(
                ModelFingerprint.tenant_id == tenant_a_id,
                ModelFingerprint.model_id == model_id,
            )
        ).one()
        fp_b = session.exec(
            select(ModelFingerprint).where(
                ModelFingerprint.tenant_id == tenant_b_id,
                ModelFingerprint.model_id == model_id,
            )
        ).one()
        assert json.loads(fp_a.genome_json)["hallucination"] == 1.0
        assert json.loads(fp_b.genome_json)["hallucination"] == 0.0
        stats_a = json.loads(fp_a.stats_json)
        stats_b = json.loads(fp_b.stats_json)
        assert stats_a["num_runs"] == 1
        assert stats_a["avg_score"] == 0.2
        assert stats_a["total_cost_usd"] == 9.0
        assert stats_b["num_runs"] == 1
        assert stats_b["avg_score"] == 0.95
        assert stats_b["total_cost_usd"] == 0.5
        camp_a_id = camp_a.id

    client = TestClient(app)
    forbidden = client.post(
        f"/genome/campaigns/{camp_a_id}/compute",
        headers={"X-Tenant-Key": "tenant-b"},
    )
    assert forbidden.status_code == 404


def test_second_campaign_aggregates_instead_of_last_write_wins():
    _app, engine, tenant_a_id, _tenant_b_id, model_id, bench_id = _setup()
    with Session(engine) as session:
        camp_1 = _seed_campaign(
            session,
            tenant_id=tenant_a_id,
            model_id=model_id,
            benchmark_id=bench_id,
            name="A1",
            genome={"hallucination": 1.0},
            score=0.0,
            cost=1.0,
        )
        camp_2 = _seed_campaign(
            session,
            tenant_id=tenant_a_id,
            model_id=model_id,
            benchmark_id=bench_id,
            name="A2",
            genome={"hallucination": 0.0},
            score=1.0,
            cost=3.0,
        )
        genome._update_model_fingerprints(camp_1.id, session, tenant_id=tenant_a_id)
        genome._update_model_fingerprints(camp_2.id, session, tenant_id=tenant_a_id)

        fps = session.exec(
            select(ModelFingerprint).where(ModelFingerprint.tenant_id == tenant_a_id)
        ).all()
        assert len(fps) == 1
        genome_json = json.loads(fps[0].genome_json)
        stats = json.loads(fps[0].stats_json)
        assert genome_json["hallucination"] == 0.5
        assert stats["num_runs"] == 2
        assert stats["avg_score"] == 0.5
        assert stats["total_cost_usd"] == 4.0
