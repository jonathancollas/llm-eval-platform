import json
import os
import secrets
import sys

from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from core.models import Benchmark, BenchmarkType, Campaign, EvalRun, JobStatus, LLMModel
from core.relations import (
    get_benchmark_tags,
    get_campaign_benchmark_ids,
    get_campaign_model_ids,
    get_eval_run_metrics,
    replace_benchmark_tags,
    replace_campaign_links,
    replace_eval_run_metrics,
)


def _make_session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_campaign_links_fallback_and_normalized_precedence():
    with _make_session() as session:
        m1 = LLMModel(name="m1", model_id="provider/m1")
        m2 = LLMModel(name="m2", model_id="provider/m2")
        b1 = Benchmark(name="b1", type=BenchmarkType.CUSTOM)
        b2 = Benchmark(name="b2", type=BenchmarkType.CUSTOM)
        session.add(m1)
        session.add(m2)
        session.add(b1)
        session.add(b2)
        session.commit()
        session.refresh(m1)
        session.refresh(m2)
        session.refresh(b1)
        session.refresh(b2)

        campaign = Campaign(
            name="c1",
            model_ids=json.dumps([m1.id, m2.id]),
            benchmark_ids=json.dumps([b1.id, b2.id]),
        )
        session.add(campaign)
        session.commit()
        session.refresh(campaign)

        assert get_campaign_model_ids(session, campaign) == [m1.id, m2.id]
        assert get_campaign_benchmark_ids(session, campaign) == [b1.id, b2.id]

        replace_campaign_links(session, campaign.id, [m2.id, m1.id], [b2.id, b1.id])
        campaign.model_ids = json.dumps([999])
        campaign.benchmark_ids = json.dumps([888])
        session.add(campaign)
        session.commit()

        assert get_campaign_model_ids(session, campaign) == sorted([m1.id, m2.id])
        assert get_campaign_benchmark_ids(session, campaign) == sorted([b1.id, b2.id])


def test_benchmark_tags_and_eval_run_metrics_fallback_and_normalized_precedence():
    with _make_session() as session:
        model = LLMModel(name="m1", model_id="provider/m1")
        bench = Benchmark(name="b1", type=BenchmarkType.SAFETY, tags=json.dumps(["legacy-tag"]))
        campaign = Campaign(name="c1")
        session.add(model)
        session.add(bench)
        session.add(campaign)
        session.commit()
        session.refresh(model)
        session.refresh(bench)
        session.refresh(campaign)

        run = EvalRun(
            campaign_id=campaign.id,
            model_id=model.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
            metrics_json=json.dumps({"legacy_metric": {"alerts": ["legacy"]}}),
        )
        session.add(run)
        session.commit()
        session.refresh(run)

        assert get_benchmark_tags(session, bench) == ["legacy-tag"]
        assert get_eval_run_metrics(session, run) == {"legacy_metric": {"alerts": ["legacy"]}}

        replace_benchmark_tags(session, bench.id, ["normalized-a", "normalized-b"])
        replace_eval_run_metrics(session, run.id, {"alerts": ["normalized"], "score_breakdown": {"x": 1}})
        session.commit()

        assert get_benchmark_tags(session, bench) == ["normalized-a", "normalized-b"]
        assert get_eval_run_metrics(session, run) == {
            "alerts": ["normalized"],
            "score_breakdown": {"x": 1},
        }
