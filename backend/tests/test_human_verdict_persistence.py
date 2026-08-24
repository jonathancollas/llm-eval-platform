"""
Human-review labels on EvalResult must persist.

The dashboard failed-items panel reads `human_verdict` on every item and
PATCH /results/{id}/human-review writes it. Before the column existed on
EvalResult, GET /results/campaign/{id}/failed-items raised AttributeError
as soon as any failed item was present, and PATCH appeared to succeed
while dropping the verdict on the next request.
"""
from __future__ import annotations

import importlib.util
import os
import secrets
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from core.models import (  # noqa: E402
    Benchmark,
    BenchmarkType,
    Campaign,
    EvalResult,
    EvalRun,
    JobStatus,
    LLMModel,
    ModelProvider,
)

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
RESULTS_PATH = os.path.join(BACKEND_DIR, "api", "routers", "results.py")


def _load_results_router():
    spec = importlib.util.spec_from_file_location("results_router_module", RESULTS_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _setup():
    db_path = Path("/tmp") / f"human-verdict-{uuid.uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        model = LLMModel(
            name="Test Model",
            provider=ModelProvider.CUSTOM,
            model_id=f"provider/{uuid.uuid4().hex[:8]}",
        )
        bench = Benchmark(
            name=f"bench-{uuid.uuid4().hex[:8]}",
            type=BenchmarkType.CUSTOM,
            is_builtin=False,
            config_json="{}",
        )
        session.add(model)
        session.add(bench)
        session.commit()
        session.refresh(model)
        session.refresh(bench)

        campaign = Campaign(
            name="Human review campaign",
            description="",
            model_ids=f"[{model.id}]",
            benchmark_ids=f"[{bench.id}]",
            status=JobStatus.COMPLETED,
        )
        session.add(campaign)
        session.commit()
        session.refresh(campaign)

        run = EvalRun(
            campaign_id=campaign.id,
            model_id=model.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
            score=0.0,
            num_items=2,
        )
        session.add(run)
        session.commit()
        session.refresh(run)

        failed = EvalResult(
            run_id=run.id,
            item_index=0,
            prompt="What is 2+2?",
            response="5",
            expected="4",
            score=0.0,
        )
        passed = EvalResult(
            run_id=run.id,
            item_index=1,
            prompt="What is 1+1?",
            response="2",
            expected="2",
            score=1.0,
        )
        session.add(failed)
        session.add(passed)
        session.commit()
        session.refresh(failed)
        ids = {
            "campaign_id": campaign.id,
            "run_id": run.id,
            "failed_id": failed.id,
        }

    results = _load_results_router()
    app = FastAPI()
    app.include_router(results.router)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[results.get_session] = _get_session_override
    return app, engine, ids


def test_failed_items_returns_null_human_verdict_without_crashing():
    app, _engine, ids = _setup()
    client = TestClient(app)

    resp = client.get(f"/results/campaign/{ids['campaign_id']}/failed-items")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_failed"] >= 1
    failed = next(item for item in body["items"] if item["id"] == ids["failed_id"])
    assert failed["human_verdict"] is None
    assert failed["score"] == 0.0


def test_human_review_persists_across_sessions():
    app, engine, ids = _setup()
    client = TestClient(app)
    result_id = ids["failed_id"]

    patch = client.patch(
        f"/results/{result_id}/human-review",
        json={"verdict": True},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["human_verdict"] is True

    # Fresh session — in-memory setattr must not mask a missing column.
    with Session(engine) as reader:
        stored = reader.exec(
            select(EvalResult).where(EvalResult.id == result_id)
        ).one()
        assert stored.human_verdict is True

    listed = client.get(f"/results/campaign/{ids['campaign_id']}/failed-items")
    assert listed.status_code == 200, listed.text
    failed = next(
        item for item in listed.json()["items"] if item["id"] == result_id
    )
    assert failed["human_verdict"] is True

    reset = client.patch(
        f"/results/{result_id}/human-review",
        json={"verdict": None},
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["human_verdict"] is None

    with Session(engine) as reader:
        stored = reader.exec(
            select(EvalResult).where(EvalResult.id == result_id)
        ).one()
        assert stored.human_verdict is None
