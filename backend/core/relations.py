import json

from sqlmodel import Session, select

from core.models import (
    Benchmark,
    BenchmarkTag,
    Campaign,
    CampaignBenchmark,
    CampaignModel,
    EvalRun,
    EvalRunMetric,
)
from core.utils import safe_json_load


def get_campaign_model_ids(session: Session, campaign: Campaign) -> list[int]:
    ids = session.exec(
        select(CampaignModel.model_id)
        .where(CampaignModel.campaign_id == campaign.id)
        .order_by(CampaignModel.model_id)
    ).all()
    if ids:
        return list(ids)
    return [int(v) for v in safe_json_load(campaign.model_ids, []) if isinstance(v, int)]


def get_campaign_benchmark_ids(session: Session, campaign: Campaign) -> list[int]:
    ids = session.exec(
        select(CampaignBenchmark.benchmark_id)
        .where(CampaignBenchmark.campaign_id == campaign.id)
        .order_by(CampaignBenchmark.benchmark_id)
    ).all()
    if ids:
        return list(ids)
    return [int(v) for v in safe_json_load(campaign.benchmark_ids, []) if isinstance(v, int)]


def replace_campaign_links(
    session: Session,
    campaign_id: int,
    model_ids: list[int],
    benchmark_ids: list[int],
) -> None:
    current_model_links = session.exec(
        select(CampaignModel).where(CampaignModel.campaign_id == campaign_id)
    ).all()
    for link in current_model_links:
        session.delete(link)
    for model_id in dict.fromkeys(model_ids):
        session.add(CampaignModel(campaign_id=campaign_id, model_id=model_id))

    current_benchmark_links = session.exec(
        select(CampaignBenchmark).where(CampaignBenchmark.campaign_id == campaign_id)
    ).all()
    for link in current_benchmark_links:
        session.delete(link)
    for benchmark_id in dict.fromkeys(benchmark_ids):
        session.add(CampaignBenchmark(campaign_id=campaign_id, benchmark_id=benchmark_id))


def get_benchmark_tags(session: Session, benchmark: Benchmark) -> list[str]:
    tags = session.exec(
        select(BenchmarkTag.tag)
        .where(BenchmarkTag.benchmark_id == benchmark.id)
        .order_by(BenchmarkTag.tag)
    ).all()
    if tags:
        return [str(tag) for tag in tags]
    raw_tags = safe_json_load(benchmark.tags, [])
    return [str(tag) for tag in raw_tags if isinstance(tag, str)]


def replace_benchmark_tags(session: Session, benchmark_id: int, tags: list[str]) -> None:
    current = session.exec(
        select(BenchmarkTag).where(BenchmarkTag.benchmark_id == benchmark_id)
    ).all()
    for row in current:
        session.delete(row)
    for tag in dict.fromkeys(tags):
        if not tag:
            continue
        session.add(BenchmarkTag(benchmark_id=benchmark_id, tag=tag))


def get_eval_run_metrics(session: Session, run: EvalRun) -> dict:
    rows = session.exec(
        select(EvalRunMetric).where(EvalRunMetric.run_id == run.id)
    ).all()
    if rows:
        out = {}
        for row in rows:
            out[row.metric_key] = safe_json_load(row.metric_value_json, None)
        return out
    return safe_json_load(run.metrics_json, {})


def replace_eval_run_metrics(session: Session, run_id: int, metrics: dict) -> None:
    current = session.exec(
        select(EvalRunMetric).where(EvalRunMetric.run_id == run_id)
    ).all()
    for row in current:
        session.delete(row)
    for key, value in (metrics or {}).items():
        session.add(
            EvalRunMetric(
                run_id=run_id,
                metric_key=str(key),
                metric_value_json=json.dumps(value),
            )
        )
