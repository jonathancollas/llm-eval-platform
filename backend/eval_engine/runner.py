"""
Campaign runner — orchestrates N models × M benchmarks in parallel.
Tracks rate limits and estimates ETA.
"""
import asyncio
import json
import logging
import time
from datetime import datetime

from sqlmodel import Session, select

from core.database import engine
from core.models import Campaign, EvalRun, EvalResult, LLMModel, Benchmark, JobStatus
from core.config import get_settings
from eval_engine.registry import get_runner

logger = logging.getLogger(__name__)
settings = get_settings()


async def execute_campaign(campaign_id: int) -> None:
    """Top-level executor. Any exception → DB marked FAILED."""
    try:
        await _execute_campaign_inner(campaign_id)
    except asyncio.CancelledError:
        logger.info(f"Campaign {campaign_id} cancelled.")
        _mark_campaign(campaign_id, JobStatus.CANCELLED, "Cancelled by user.")
    except Exception as e:
        logger.exception(f"Campaign {campaign_id} crashed: {e}")
        _mark_campaign(campaign_id, JobStatus.FAILED, f"Unexpected error: {str(e)[:400]}")


def _mark_campaign(campaign_id: int, status: JobStatus, error: str | None = None) -> None:
    try:
        with Session(engine) as session:
            c = session.get(Campaign, campaign_id)
            if c:
                c.status = status
                c.error_message = error
                c.completed_at = datetime.utcnow()
                session.add(c)
                session.commit()
    except Exception as e:
        logger.error(f"Could not persist status for campaign {campaign_id}: {e}")


async def _execute_campaign_inner(campaign_id: int) -> None:
    with Session(engine) as session:
        campaign = session.get(Campaign, campaign_id)
        if not campaign:
            logger.error(f"Campaign {campaign_id} not found.")
            return

        # Status already set to RUNNING by the /run endpoint
        model_ids: list[int] = json.loads(campaign.model_ids or "[]")
        benchmark_ids: list[int] = json.loads(campaign.benchmark_ids or "[]")
        logger.info(f"Campaign {campaign_id} executing: '{campaign.name}' "
                    f"({len(model_ids)} models × {len(benchmark_ids)} benchmarks = {len(model_ids)*len(benchmark_ids)} runs)")
        total_runs = len(model_ids) * len(benchmark_ids)

        if total_runs == 0:
            campaign.status = JobStatus.COMPLETED
            campaign.progress = 100.0
            campaign.completed_at = datetime.utcnow()
            session.add(campaign)
            session.commit()
            return

        completed_runs = 0
        campaign_start = time.monotonic()

        for model_id in model_ids:
            model = session.get(LLMModel, model_id)
            if not model:
                logger.warning(f"Model {model_id} not found, skipping.")
                completed_runs += len(benchmark_ids)
                continue

            logger.info(f"Campaign {campaign_id}: model '{model.name}' × {len(benchmark_ids)} benchmarks")

            run_coroutines = []
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
                run_coroutines.append(_run_one(model, benchmark, campaign, eval_run.id))

            if not run_coroutines:
                continue

            semaphore = asyncio.Semaphore(settings.max_concurrent_runs)

            async def bounded(coro):
                async with semaphore:
                    return await coro

            results = await asyncio.gather(
                *[bounded(c) for c in run_coroutines],
                return_exceptions=True,
            )

            for eval_run_id, result in zip(eval_run_ids, results):
                eval_run = session.get(EvalRun, eval_run_id)
                if not eval_run:
                    continue

                if isinstance(result, BaseException):
                    err_str = str(result)
                    # Classify error type for better UX
                    if "insufficient credits" in err_str.lower():
                        friendly = "Model requires credits on OpenRouter. Use a :free model or add credits to your account."
                    elif "rate limit" in err_str.lower() or "ratelimit" in err_str.lower():
                        friendly = f"Rate limited after retries: {err_str[:200]}"
                    else:
                        friendly = err_str[:300]
                    logger.error(f"EvalRun {eval_run_id} failed: {friendly}")
                    eval_run.status = JobStatus.FAILED
                    eval_run.error_message = friendly
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

            # Update progress + ETA
            elapsed = time.monotonic() - campaign_start
            campaign.progress = round((completed_runs / total_runs) * 100, 1)

            if completed_runs > 0 and completed_runs < total_runs:
                avg_per_run = elapsed / completed_runs
                remaining = total_runs - completed_runs
                eta_seconds = int(avg_per_run * remaining)
                eta_str = _format_eta(eta_seconds)
                campaign.error_message = f"ETA: {eta_str} ({completed_runs}/{total_runs} runs terminés)"
                logger.info(f"Campaign {campaign_id}: {campaign.progress}% — ETA {eta_str}")
            else:
                campaign.error_message = None

            session.add(campaign)
            session.commit()

        campaign.status = JobStatus.COMPLETED
        campaign.progress = 100.0
        campaign.error_message = None
        campaign.completed_at = datetime.utcnow()
        session.add(campaign)
        session.commit()
        logger.info(f"Campaign {campaign_id} completed in {_format_eta(int(time.monotonic() - campaign_start))}.")

        # Auto-compute Failure Genome
        try:
            from eval_engine.failure_genome.classifiers import classify_run, aggregate_genome
            _compute_genome_for_campaign(campaign_id, session)
            logger.info(f"Campaign {campaign_id}: Failure Genome computed.")
        except Exception as e:
            logger.warning(f"Genome computation failed (non-blocking): {e}")


def _format_eta(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"


async def _run_one(model: LLMModel, benchmark: Benchmark, campaign: Campaign, eval_run_id: int):
    """Run one model × benchmark. Returns (RunSummary, item_results) or raises."""
    from pathlib import Path
    if benchmark.dataset_path:
        dataset_file = Path(settings.bench_library_path) / benchmark.dataset_path
        logger.info(f"Benchmark '{benchmark.name}': {dataset_file} (exists={dataset_file.exists()})")

    try:
        runner = get_runner(benchmark, settings.bench_library_path)
    except Exception as e:
        raise RuntimeError(f"Failed to get runner for '{benchmark.name}': {e}") from e

    max_samples = campaign.max_samples or benchmark.num_samples or settings.default_max_samples

    try:
        summary = await asyncio.wait_for(
            runner.run(
                model=model,
                max_samples=max_samples,
                seed=campaign.seed,
                temperature=campaign.temperature,
                progress_callback=None,
            ),
            timeout=600,  # 10 min max per benchmark run
        )
    except asyncio.TimeoutError:
        raise RuntimeError(
            f"Timeout (10min) — benchmark='{benchmark.name}' model='{model.name}'"
        )
    except Exception as e:
        raise RuntimeError(
            f"Runner failed — benchmark='{benchmark.name}' model='{model.name}': {type(e).__name__}: {str(e)[:200]}"
        ) from e

    return summary, summary.item_results

def _compute_genome_for_campaign(campaign_id: int, session: Session) -> None:
    from sqlmodel import select as _sel_inner
    """Compute and store Failure Genome profiles after campaign completes."""
    from core.models import FailureProfile, ModelFingerprint
    from eval_engine.failure_genome.classifiers import classify_run, aggregate_genome
    from eval_engine.failure_genome.ontology import FAILURE_GENOME_VERSION
    from core.utils import safe_json_load
    import json as _json
    from datetime import datetime as _dt

    runs = session.exec(_sel_inner(EvalRun).where(EvalRun.campaign_id == campaign_id)).all()
    for run in runs:
        if run.status != JobStatus.COMPLETED:
            continue
        bench = session.get(Benchmark, run.benchmark_id)
        bench_type = str(bench.type) if bench else "custom"
        results = session.exec(_sel_inner(EvalResult).where(EvalResult.run_id == run.id)).all()

        if results:
            item_genomes = [classify_run(
                prompt=r.prompt or "", response=r.response or "", expected=r.expected,
                score=r.score, benchmark_type=bench_type,
                latency_ms=r.latency_ms, num_items=len(results),
            ) for r in results]
            genome = aggregate_genome(item_genomes)
        else:
            genome = classify_run(
                prompt="", response="", expected=None,
                score=run.score or 0.0, benchmark_type=bench_type,
                latency_ms=run.total_latency_ms, num_items=run.num_items,
            )

        existing = session.exec(_sel_inner(FailureProfile).where(FailureProfile.run_id == run.id)).first()
        if existing:
            existing.genome_json = _json.dumps(genome)
            session.add(existing)
        else:
            session.add(FailureProfile(
                run_id=run.id, campaign_id=campaign_id,
                model_id=run.model_id, benchmark_id=run.benchmark_id,
                genome_json=_json.dumps(genome), genome_version=FAILURE_GENOME_VERSION,
            ))
    session.commit()
