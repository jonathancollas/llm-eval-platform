"""
Campaign runner — orchestrates N models × M benchmarks.
Runs benchmarks in parallel (asyncio.gather) for maximum throughput.
"""
import asyncio
import json
import logging
from datetime import datetime

from sqlmodel import Session, select

from core.database import engine
from core.models import Campaign, EvalRun, EvalResult, LLMModel, Benchmark, JobStatus
from core.config import get_settings
from eval_engine.registry import get_runner

logger = logging.getLogger(__name__)
settings = get_settings()


async def execute_campaign(campaign_id: int) -> None:
    """
    Top-level campaign executor.
    Any unhandled exception is caught here and persisted to DB — 
    no campaign can silently disappear from the queue.
    """
    try:
        await _execute_campaign_inner(campaign_id)
    except asyncio.CancelledError:
        logger.info(f"Campaign {campaign_id} was cancelled.")
        _mark_campaign(campaign_id, JobStatus.CANCELLED, "Cancelled by user.")
    except Exception as e:
        logger.exception(f"Campaign {campaign_id} crashed unexpectedly: {e}")
        _mark_campaign(campaign_id, JobStatus.FAILED, f"Unexpected error: {str(e)[:400]}")


def _mark_campaign(campaign_id: int, status: JobStatus, error: str | None = None) -> None:
    """Force-write campaign status to DB (called from exception handlers)."""
    try:
        with Session(engine) as session:
            campaign = session.get(Campaign, campaign_id)
            if campaign:
                campaign.status = status
                campaign.error_message = error
                campaign.completed_at = datetime.utcnow()
                session.add(campaign)
                session.commit()
    except Exception as db_err:
        logger.error(f"Failed to persist campaign {campaign_id} status: {db_err}")


async def _execute_campaign_inner(campaign_id: int) -> None:
    with Session(engine) as session:
        campaign = session.get(Campaign, campaign_id)
        if not campaign:
            logger.error(f"Campaign {campaign_id} not found in DB.")
            return

        # Mark as RUNNING
        campaign.status = JobStatus.RUNNING
        campaign.started_at = datetime.utcnow()
        campaign.error_message = None
        session.add(campaign)
        session.commit()
        logger.info(f"Campaign {campaign_id} started: '{campaign.name}'")

        model_ids: list[int] = json.loads(campaign.model_ids or "[]")
        benchmark_ids: list[int] = json.loads(campaign.benchmark_ids or "[]")
        total_runs = len(model_ids) * len(benchmark_ids)

        if total_runs == 0:
            campaign.status = JobStatus.COMPLETED
            campaign.progress = 100.0
            campaign.completed_at = datetime.utcnow()
            session.add(campaign)
            session.commit()
            logger.info(f"Campaign {campaign_id} completed (no runs).")
            return

        completed_runs = 0

        for model_id in model_ids:
            model = session.get(LLMModel, model_id)
            if not model:
                logger.warning(f"Model {model_id} not found, skipping.")
                completed_runs += len(benchmark_ids)
                continue

            logger.info(f"Campaign {campaign_id}: running model '{model.name}' against {len(benchmark_ids)} benchmarks")

            # Create EvalRun records and gather coroutines
            run_coroutines = []
            eval_run_ids = []

            for benchmark_id in benchmark_ids:
                benchmark = session.get(Benchmark, benchmark_id)
                if not benchmark:
                    logger.warning(f"Benchmark {benchmark_id} not found, skipping.")
                    completed_runs += 1
                    continue

                eval_run = EvalRun(
                    campaign_id=campaign_id,
                    model_id=model_id,
                    benchmark_id=benchmark_id,
                    status=JobStatus.RUNNING,
                    started_at=datetime.utcnow(),
                )
                session.add(eval_run)
                session.commit()
                session.refresh(eval_run)
                eval_run_ids.append(eval_run.id)

                run_coroutines.append(_run_one(
                    model=model,
                    benchmark=benchmark,
                    campaign=campaign,
                    eval_run_id=eval_run.id,
                ))

            if not run_coroutines:
                continue

            # Execute in parallel with concurrency limit
            semaphore = asyncio.Semaphore(settings.max_concurrent_runs)

            async def bounded(coro):
                async with semaphore:
                    return await coro

            results = await asyncio.gather(
                *[bounded(c) for c in run_coroutines],
                return_exceptions=True,
            )

            # Persist results
            for eval_run_id, result in zip(eval_run_ids, results):
                eval_run = session.get(EvalRun, eval_run_id)
                if not eval_run:
                    continue

                if isinstance(result, BaseException):
                    logger.error(f"EvalRun {eval_run_id} failed: {result}")
                    eval_run.status = JobStatus.FAILED
                    eval_run.error_message = str(result)[:400]
                else:
                    summary, item_results = result
                    eval_run.status = JobStatus.COMPLETED
                    eval_run.score = summary.score
                    eval_run.metrics_json = json.dumps(summary.metrics)
                    eval_run.total_cost_usd = summary.total_cost_usd
                    eval_run.total_latency_ms = summary.total_latency_ms
                    eval_run.num_items = summary.num_items

                    for item in item_results:
                        session.add(EvalResult(
                            run_id=eval_run_id,
                            item_index=item.item_index,
                            prompt=item.prompt[:2000],
                            response=item.response[:2000],
                            expected=item.expected,
                            score=item.score,
                            latency_ms=item.latency_ms,
                            input_tokens=item.input_tokens,
                            output_tokens=item.output_tokens,
                            cost_usd=item.cost_usd,
                            metadata_json=json.dumps(item.metadata),
                        ))

                    logger.info(
                        f"EvalRun {eval_run_id}: score={summary.score:.3f} "
                        f"items={summary.num_items} latency={summary.total_latency_ms}ms"
                    )

                eval_run.completed_at = datetime.utcnow()
                session.add(eval_run)
                completed_runs += 1

            # Update campaign progress
            campaign.progress = round((completed_runs / total_runs) * 100, 1)
            session.add(campaign)
            session.commit()
            logger.info(f"Campaign {campaign_id}: progress {campaign.progress}%")

        campaign.status = JobStatus.COMPLETED
        campaign.progress = 100.0
        campaign.completed_at = datetime.utcnow()
        session.add(campaign)
        session.commit()
        logger.info(f"Campaign {campaign_id} completed successfully.")


async def _run_one(model: LLMModel, benchmark: Benchmark, campaign: Campaign, eval_run_id: int):
    """Run one model × benchmark. Returns (RunSummary, item_results) or raises."""
    try:
        runner = get_runner(benchmark, settings.bench_library_path)
    except Exception as e:
        raise RuntimeError(f"Failed to get runner for '{benchmark.name}': {e}") from e

    max_samples = campaign.max_samples or benchmark.num_samples or settings.default_max_samples

    try:
        summary = await runner.run(
            model=model,
            max_samples=max_samples,
            seed=campaign.seed,
            temperature=campaign.temperature,
            progress_callback=None,
        )
    except Exception as e:
        raise RuntimeError(
            f"Runner failed for benchmark='{benchmark.name}' model='{model.name}': {e}"
        ) from e

    return summary, summary.item_results
