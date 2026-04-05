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
    with Session(engine) as session:
        campaign = session.get(Campaign, campaign_id)
        if not campaign:
            logger.error(f"Campaign {campaign_id} not found.")
            return

        campaign.status = JobStatus.RUNNING
        campaign.started_at = datetime.utcnow()
        session.add(campaign)
        session.commit()

        model_ids: list[int] = json.loads(campaign.model_ids)
        benchmark_ids: list[int] = json.loads(campaign.benchmark_ids)
        total_runs = len(model_ids) * len(benchmark_ids)

        if total_runs == 0:
            campaign.status = JobStatus.COMPLETED
            campaign.progress = 100.0
            campaign.completed_at = datetime.utcnow()
            session.add(campaign)
            session.commit()
            return

        completed_runs = 0

        try:
            for model_id in model_ids:
                model = session.get(LLMModel, model_id)
                if not model:
                    logger.warning(f"Model {model_id} not found, skipping.")
                    completed_runs += len(benchmark_ids)
                    continue

                # Run all benchmarks for this model in parallel
                tasks = []
                eval_run_ids = []
                for benchmark_id in benchmark_ids:
                    benchmark = session.get(Benchmark, benchmark_id)
                    if not benchmark:
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

                    tasks.append(_run_one(
                        model=model,
                        benchmark=benchmark,
                        campaign=campaign,
                        eval_run_id=eval_run.id,
                    ))

                # Execute with bounded parallelism
                semaphore = asyncio.Semaphore(settings.max_concurrent_runs)

                async def bounded(coro):
                    async with semaphore:
                        return await coro

                results = await asyncio.gather(
                    *[bounded(t) for t in tasks],
                    return_exceptions=True,
                )

                # Persist results
                for eval_run_id, result in zip(eval_run_ids, results):
                    eval_run = session.get(EvalRun, eval_run_id)
                    if not eval_run:
                        continue

                    if isinstance(result, Exception):
                        logger.error(f"Run {eval_run_id} failed: {result}")
                        eval_run.status = JobStatus.FAILED
                        eval_run.error_message = str(result)[:500]
                    elif isinstance(result, asyncio.CancelledError):
                        eval_run.status = JobStatus.CANCELLED
                    else:
                        summary, item_results = result
                        eval_run.status = JobStatus.COMPLETED
                        eval_run.score = summary.score
                        eval_run.metrics_json = json.dumps(summary.metrics)
                        eval_run.total_cost_usd = summary.total_cost_usd
                        eval_run.total_latency_ms = summary.total_latency_ms
                        eval_run.num_items = summary.num_items

                        # Persist item results in bulk
                        for item in item_results:
                            session.add(EvalResult(
                                run_id=eval_run_id,
                                item_index=item.item_index,
                                prompt=item.prompt[:2000],      # cap size
                                response=item.response[:2000],
                                expected=item.expected,
                                score=item.score,
                                latency_ms=item.latency_ms,
                                input_tokens=item.input_tokens,
                                output_tokens=item.output_tokens,
                                cost_usd=item.cost_usd,
                                metadata_json=json.dumps(item.metadata),
                            ))

                    eval_run.completed_at = datetime.utcnow()
                    session.add(eval_run)
                    completed_runs += 1

                campaign.progress = (completed_runs / total_runs) * 100
                session.add(campaign)
                session.commit()

            campaign.status = JobStatus.COMPLETED
            campaign.progress = 100.0

        except asyncio.CancelledError:
            campaign.status = JobStatus.CANCELLED
            logger.info(f"Campaign {campaign_id} cancelled.")

        except Exception as e:
            campaign.status = JobStatus.FAILED
            campaign.error_message = str(e)[:500]
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
):
    """Execute one model × benchmark run. Returns (RunSummary, item_results)."""
    runner = get_runner(benchmark, settings.bench_library_path)
    max_samples = campaign.max_samples or benchmark.num_samples or settings.default_max_samples

    summary = await runner.run(
        model=model,
        max_samples=max_samples,
        seed=campaign.seed,
        temperature=campaign.temperature,
        progress_callback=None,
    )

    return summary, summary.item_results
