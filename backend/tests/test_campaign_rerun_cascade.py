"""Campaign re-run / delete must cascade to EvalRun children.

Re-run used to delete only EvalRun rows. Child tables FK to eval_runs.id
with no ON DELETE CASCADE. SQLite in this project never sets
PRAGMA foreign_keys, so prompts/scores/genomes were orphaned and
campaign-scoped genome/insights mixed stale rows with the new run.
Postgres enforces the FKs and the same delete raises IntegrityError.
"""
import importlib.util
import os
import secrets
import sys
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from core.models import (  # noqa: E402
    AgentTrajectory,
    Benchmark,
    BenchmarkType,
    Campaign,
    CampaignModel,
    EvalEventRecord,
    EvalResult,
    EvalRun,
    EvalRunMetric,
    ExperimentManifest,
    FailureProfile,
    JobStatus,
    JudgeEvaluation,
    LLMModel,
    ModelProvider,
    Report,
)

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
CAMPAIGNS_PATH = os.path.join(BACKEND_DIR, "api", "routers", "campaigns.py")
_spec = importlib.util.spec_from_file_location("campaigns_rerun_module", CAMPAIGNS_PATH)
campaigns = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(campaigns)


@pytest.fixture
def db_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'rerun.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def app(db_engine, monkeypatch):
    monkeypatch.setattr(campaigns.job_queue, "submit_campaign", lambda campaign_id: "fake-task")
    monkeypatch.setattr(campaigns.job_queue, "cancel_campaign", lambda campaign_id: True)

    def _get_session_override():
        with Session(db_engine) as session:
            yield session

    test_app = FastAPI()
    test_app.include_router(campaigns.router)
    test_app.dependency_overrides[campaigns.get_session] = _get_session_override
    return test_app


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _seed_completed_campaign(client, engine) -> dict:
    with Session(engine) as session:
        model = LLMModel(
            name="Cascade Model",
            provider=ModelProvider.CUSTOM,
            model_id=f"cascade-{uuid.uuid4().hex[:8]}",
        )
        bench = Benchmark(
            name=f"cascade-bench-{uuid.uuid4().hex[:8]}",
            type=BenchmarkType.CUSTOM,
            is_builtin=False,
            config_json="{}",
        )
        session.add(model)
        session.add(bench)
        session.commit()
        session.refresh(model)
        session.refresh(bench)
        model_id = model.id
        benchmark_id = bench.id

    create = client.post(
        "/campaigns/",
        json={
            "name": "Cascade Campaign",
            "description": "re-run cascade",
            "model_ids": [model_id],
            "benchmark_ids": [benchmark_id],
            "seed": 42,
            "temperature": 0.0,
        },
    )
    assert create.status_code == 201, create.text
    campaign_id = create.json()["id"]

    with Session(engine) as session:
        campaign = session.get(Campaign, campaign_id)
        assert campaign is not None
        campaign.status = JobStatus.COMPLETED
        session.add(campaign)

        run = EvalRun(
            campaign_id=campaign_id,
            model_id=model_id,
            benchmark_id=benchmark_id,
            status=JobStatus.COMPLETED,
            score=0.1,
            num_items=1,
        )
        session.add(run)
        session.commit()
        session.refresh(run)

        result = EvalResult(
            run_id=run.id,
            item_index=0,
            prompt="secret system prompt",
            response="leaked completion",
            score=0.0,
        )
        session.add(result)
        session.add(EvalRunMetric(run_id=run.id, metric_key="accuracy", metric_value_json="0.1"))
        session.add(
            FailureProfile(
                run_id=run.id,
                campaign_id=campaign_id,
                model_id=model_id,
                benchmark_id=benchmark_id,
                genome_json='{"sycophancy": 0.9}',
            )
        )
        session.commit()
        session.refresh(result)
        session.add(
            JudgeEvaluation(
                campaign_id=campaign_id,
                run_id=run.id,
                result_id=result.id,
                judge_model="judge-1",
                judge_score=0.2,
            )
        )
        session.commit()
        return {
            "campaign_id": campaign_id,
            "run_id": run.id,
            "result_id": result.id,
            "model_id": model_id,
            "benchmark_id": benchmark_id,
        }


def test_rerun_deletes_child_rows_under_fk_enforcement(client, db_engine):
    ids = _seed_completed_campaign(client, db_engine)

    response = client.post(f"/campaigns/{ids['campaign_id']}/run")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "running"

    with Session(db_engine) as session:
        assert session.exec(select(EvalRun)).all() == []
        assert session.exec(select(EvalResult)).all() == []
        assert session.exec(select(EvalRunMetric)).all() == []
        assert session.exec(select(FailureProfile)).all() == []
        assert session.exec(select(JudgeEvaluation)).all() == []
        campaign = session.get(Campaign, ids["campaign_id"])
        assert campaign is not None
        # Config links must survive re-run so the new execution still has targets.
        assert session.exec(
            select(CampaignModel).where(CampaignModel.campaign_id == ids["campaign_id"])
        ).first() is not None


def test_rerun_does_not_mix_stale_genome_into_new_campaign(client, db_engine):
    """GET genome/insights key FailureProfile by campaign_id, not run_id.

    If re-run leaves the old profile, a later compute aggregates stale + new
    genomes and reports the wrong failure DNA.
    """
    ids = _seed_completed_campaign(client, db_engine)
    response = client.post(f"/campaigns/{ids['campaign_id']}/run")
    assert response.status_code == 200, response.text

    with Session(db_engine) as session:
        stale = session.exec(
            select(FailureProfile).where(
                FailureProfile.campaign_id == ids["campaign_id"]
            )
        ).all()
        assert stale == []


def test_delete_campaign_cascades_under_fk_enforcement(client, db_engine):
    ids = _seed_completed_campaign(client, db_engine)
    with Session(db_engine) as session:
        session.add(
            Report(
                campaign_id=ids["campaign_id"],
                title="old report",
                content_markdown="# stale",
            )
        )
        session.add(
            ExperimentManifest(
                campaign_id=ids["campaign_id"],
                experiment_hash="abc",
            )
        )
        session.add(
            EvalEventRecord(
                event_id=str(uuid.uuid4()),
                event_type="campaign_completed",
                campaign_id=ids["campaign_id"],
                sequence=1,
            )
        )
        session.add(
            AgentTrajectory(
                campaign_id=ids["campaign_id"],
                model_id=ids["model_id"],
                task_description="keep me",
            )
        )
        session.commit()

    response = client.delete(f"/campaigns/{ids['campaign_id']}")
    assert response.status_code == 204, response.text

    with Session(db_engine) as session:
        assert session.get(Campaign, ids["campaign_id"]) is None
        assert session.exec(select(EvalRun)).all() == []
        assert session.exec(select(EvalResult)).all() == []
        assert session.exec(select(FailureProfile)).all() == []
        assert session.exec(select(JudgeEvaluation)).all() == []
        assert session.exec(select(Report)).all() == []
        assert session.exec(select(ExperimentManifest)).all() == []
        assert session.exec(select(EvalEventRecord)).all() == []
        assert session.exec(
            select(CampaignModel).where(CampaignModel.campaign_id == ids["campaign_id"])
        ).all() == []
        trajectories = session.exec(select(AgentTrajectory)).all()
        assert len(trajectories) == 1
        assert trajectories[0].campaign_id is None
        assert trajectories[0].task_description == "keep me"
