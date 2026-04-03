"""
Campaign runner: orchestrates N models × M benchmarks runs.
Called as a background asyncio task by the job queue.
"""
import asyncio
import json
import logging
from datetime import datetime

from sqlmodel import Session, select

from core.database import engine
from core.models import (
    Campaign, EvalRun, EvalResult, LLMModel, Benchmark, JobStatus
)
from core.config import get_settings
from eval_engine.registry import get_runner
from eval_engine.base import RunSummary, ItemResult

logger = logging.getLogger(__name__)
settings = get_settings()


async def execute_campaign(campaign_id: int) -> None:
    """
    Main coroutine for a campaign. Runs all model × benchmark combinations
    sequentially (MVP: no parallelism to avoid CPU overload on desktop).
    """
    with Session(engine) as session:
        campaign = session.get(Campaign, campaign_id)
        if not campaign:
            logger.error(f"Campaign {campaign_id} not found.")
            return

        # Mark running
        campaign.status = JobStatus.RUNNING
        campaign.started_at = datetime.utcnow()
        session.add(campaign)
        session.commit()
        session.refresh(campaign)

        model_ids: list[int] = json.loads(campaign.model_ids)
        benchmark_ids: list[int] = json.loads(campaign.benchmark_ids)
        total_runs = len(model_ids) * len(benchmark_ids)
        completed_runs = 0

        try:
            for model_id in model_ids:
                model = session.get(LLMModel, model_id)
                if not model:
                    logger.warning(f"Model {model_id} not found, skipping.")
                    continue

                for benchmark_id in benchmark_ids:
                    benchmark = session.get(Benchmark, benchmark_id)
                    if not benchmark:
                        logger.warning(f"Benchmark {benchmark_id} not found, skipping.")
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

                    try:
                        summary = await _run_one(
                            model=model,
                            benchmark=benchmark,
                            campaign=campaign,
                            eval_run_id=eval_run.id,
                            session=session,
                        )

                        # Update eval_run with summary
                        eval_run.status = JobStatus.COMPLETED
                        eval_run.score = summary.score
                        eval_run.metrics_json = json.dumps(summary.metrics)
                        eval_run.total_cost_usd = summary.total_cost_usd
                        eval_run.total_latency_ms = summary.total_latency_ms
                        eval_run.num_items = summary.num_items
                        eval_run.completed_at = datetime.utcnow()

                    except asyncio.CancelledError:
                        eval_run.status = JobStatus.CANCELLED
                        eval_run.completed_at = datetime.utcnow()
                        session.add(eval_run)
                        session.commit()
                        raise

                    except Exception as e:
                        logger.error(
                            f"Run failed (model={model_id}, bench={benchmark_id}): {e}",
                            exc_info=True,
                        )
                        eval_run.status = JobStatus.FAILED
                        eval_run.error_message = str(e)
                        eval_run.completed_at = datetime.utcnow()

                    session.add(eval_run)
                    completed_runs += 1
                    campaign.progress = completed_runs / total_runs * 100
                    session.add(campaign)
                    session.commit()

            campaign.status = JobStatus.COMPLETED
            campaign.progress = 100.0

        except asyncio.CancelledError:
            campaign.status = JobStatus.CANCELLED
            logger.info(f"Campaign {campaign_id} was cancelled.")

        except Exception as e:
            campaign.status = JobStatus.FAILED
            campaign.error_message = str(e)
            logger.error(f"Campaign {campaign_id} failed: {e}", exc_info=True)

        finally:
            campaign.completed_at = datetime.utcnow()
            session.add(campaign)
            session.commit()


async def _run_one(
    model: LLMModel,
    benchmark: Benchmark,
    campaign: Campaign,
    eval_run_id: int,
    session: Session,
) -> RunSummary:
    """Execute one model × benchmark run and persist per-item results."""
    runner = get_runner(benchmark, settings.bench_library_path)

    max_samples = campaign.max_samples or benchmark.num_samples or settings.default_max_samples

    def _progress(done: int, total: int) -> None:
        logger.debug(f"  [{model.name} × {benchmark.name}] {done}/{total}")

    summary = await runner.run(
        model=model,
        max_samples=max_samples,
        seed=campaign.seed,
        temperature=campaign.temperature,
        progress_callback=_progress,
    )

    # Persist per-item results
    for item_result in summary.item_results:
        result = EvalResult(
            run_id=eval_run_id,
            item_index=item_result.item_index,
            prompt=item_result.prompt,
            response=item_result.response,
            expected=item_result.expected,
            score=item_result.score,
            latency_ms=item_result.latency_ms,
            input_tokens=item_result.input_tokens,
            output_tokens=item_result.output_tokens,
            cost_usd=item_result.cost_usd,
            metadata_json=json.dumps(item_result.metadata),
        )
        session.add(result)
    session.commit()

    return summary
