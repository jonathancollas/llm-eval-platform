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
from core.relations import get_campaign_benchmark_ids, get_campaign_model_ids, replace_eval_run_metrics
from eval_engine.registry import get_runner
from core.utils import safe_extract_text
from eval_engine.event_pipeline import get_bus, EventType

logger = logging.getLogger(__name__)
settings = get_settings()
_bus = get_bus()


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
        model_ids = get_campaign_model_ids(session, campaign)
        benchmark_ids = get_campaign_benchmark_ids(session, campaign)
        logger.info(f"Campaign {campaign_id} executing: '{campaign.name}' "
                    f"({len(model_ids)} models × {len(benchmark_ids)} benchmarks = {len(model_ids)*len(benchmark_ids)} runs)")
        total_runs = len(model_ids) * len(benchmark_ids)

        # Emit campaign started event (non-blocking, fire-and-forget)
        asyncio.create_task(_bus.emit(
            EventType.CAMPAIGN_STARTED,
            campaign_id=campaign_id,
            payload={
                "name": campaign.name,
                "total_runs": total_runs,
                "model_ids": model_ids,
                "benchmark_ids": benchmark_ids,
            },
        ))

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

                # Emit RUN_STARTED
                asyncio.create_task(_bus.emit(
                    EventType.RUN_STARTED,
                    campaign_id=campaign_id,
                    run_id=eval_run.id,
                    model_id=model_id,
                    benchmark_id=benchmark_id,
                    payload={
                        "model_name": model.name,
                        "benchmark_name": benchmark.name,
                    },
                ))

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
                    # Emit RUN_FAILED
                    asyncio.create_task(_bus.emit(
                        EventType.RUN_FAILED,
                        campaign_id=campaign_id,
                        run_id=eval_run_id,
                        payload={"error": friendly[:300]},
                    ))
                else:
                    summary, item_results = result
                    eval_run.status = JobStatus.COMPLETED
                    eval_run.score = summary.score

                    # Set capability OR propensity score based on benchmark dimension
                    bench = session.get(Benchmark, eval_run.benchmark_id)
                    dim = getattr(bench, "eval_dimension", "capability") if bench else "capability"
                    if dim == "propensity":
                        eval_run.propensity_score = summary.score
                    else:
                        eval_run.capability_score = summary.score

                    eval_run.metrics_json = json.dumps(summary.metrics)
                    replace_eval_run_metrics(session, eval_run.id, summary.metrics)
                    eval_run.total_cost_usd = summary.total_cost_usd
                    eval_run.total_latency_ms = summary.total_latency_ms
                    eval_run.num_items = summary.num_items

                    # Check how many items were already streamed via callback
                    already_written = session.exec(
                        select(EvalResult).where(EvalResult.run_id == eval_run_id)
                    ).all()
                    already_ids = {r.item_index for r in already_written}

                    # Batch-insert any items NOT yet streamed (e.g. HarnessRunner)
                    missing = [item for item in item_results if item.item_index not in already_ids]
                    if missing:
                        session.add_all([
                            EvalResult(
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
                            )
                            for item in missing
                        ])

                    logger.info(
                        f"EvalRun {eval_run_id}: score={summary.score:.3f} "
                        f"items={summary.num_items} (streamed={len(already_ids)}, batch={len(missing)}) "
                        f"latency={summary.total_latency_ms}ms"
                    )
                    # Emit RUN_COMPLETED
                    asyncio.create_task(_bus.emit(
                        EventType.RUN_COMPLETED,
                        campaign_id=campaign_id,
                        run_id=eval_run_id,
                        model_id=eval_run.model_id,
                        benchmark_id=eval_run.benchmark_id,
                        payload={
                            "score": summary.score,
                            "num_items": summary.num_items,
                            "total_cost_usd": summary.total_cost_usd,
                            "total_latency_ms": summary.total_latency_ms,
                        },
                    ))

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

            # Emit CAMPAIGN_PROGRESS
            asyncio.create_task(_bus.emit(
                EventType.CAMPAIGN_PROGRESS,
                campaign_id=campaign_id,
                payload={"progress": campaign.progress, "completed_runs": completed_runs, "total_runs": total_runs},
            ))

            session.add(campaign)
            session.commit()

        campaign.status = JobStatus.COMPLETED
        campaign.progress = 100.0
        campaign.error_message = None
        campaign.current_item_index = None
        campaign.current_item_total = None
        campaign.current_item_label = None
        campaign.completed_at = datetime.utcnow()
        session.add(campaign)
        session.commit()
        logger.info(f"Campaign {campaign_id} completed in {_format_eta(int(time.monotonic() - campaign_start))}.")

        # Emit CAMPAIGN_COMPLETED
        asyncio.create_task(_bus.emit(
            EventType.CAMPAIGN_COMPLETED,
            campaign_id=campaign_id,
            payload={"duration_s": int(time.monotonic() - campaign_start)},
        ))

        # Auto-compute Failure Genome
        try:
            from eval_engine.failure_genome.classifiers import classify_run, aggregate_genome
            _compute_genome_for_campaign(campaign_id, session)
            logger.info(f"Campaign {campaign_id}: Failure Genome computed.")
            asyncio.create_task(_bus.emit(
                EventType.GENOME_COMPUTED,
                campaign_id=campaign_id,
                payload={"status": "computed"},
            ))
        except Exception as e:
            logger.warning(f"Genome computation failed (non-blocking): {e}")

        # Auto-trigger LLM Judge (if Anthropic key available)
        try:
            if settings.anthropic_api_key:
                await _auto_judge_campaign(campaign_id, session)
                logger.info(f"Campaign {campaign_id}: Auto-judge evaluation completed.")
                asyncio.create_task(_bus.emit(
                    EventType.JUDGE_COMPLETED,
                    campaign_id=campaign_id,
                    payload={"judge_model": "claude-sonnet-4-20250514"},
                ))
        except Exception as e:
            logger.warning(f"Auto-judge failed (non-blocking): {e}")

        # Auto-generate reproducibility manifest
        try:
            _generate_manifest(campaign_id, session)
            logger.info(f"Campaign {campaign_id}: Experiment manifest generated.")
        except Exception as e:
            logger.warning(f"Manifest generation failed (non-blocking): {e}")


async def _auto_judge_campaign(campaign_id: int, session: Session) -> None:
    """Auto-run a single judge on campaign results after completion."""
    import anthropic
    from core.models import EvalResult, JudgeEvaluation

    runs = session.exec(
        select(EvalRun).where(EvalRun.campaign_id == campaign_id, EvalRun.status == JobStatus.COMPLETED)
    ).all()
    run_ids = [r.id for r in runs]
    if not run_ids:
        return

    # Sample up to 30 items for auto-judge (don't judge everything — too expensive)
    results = session.exec(
        select(EvalResult).where(EvalResult.run_id.in_(run_ids)).limit(30)
    ).all()
    if not results:
        return

    # Check if already judged
    existing = session.exec(
        select(JudgeEvaluation).where(JudgeEvaluation.campaign_id == campaign_id).limit(1)
    ).first()
    if existing:
        return  # Already judged

    judge_model = "claude-sonnet-4-20250514"
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    judge_evals = []
    for result in results:
        try:
            prompt = f"""Score this model response on correctness (0.0-1.0).

## Prompt
{result.prompt[:800]}

## Response
{result.response[:1000]}

{f"## Expected: {result.expected[:300]}" if result.expected else ""}

JSON only: {{"score": <float>, "reasoning": "<brief>"}}"""

            msg = await asyncio.wait_for(
                client.messages.create(
                    model=judge_model, max_tokens=200,
                    messages=[{"role": "user", "content": prompt}],
                ), timeout=15,
            )
            text = safe_extract_text(msg)
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            data = json.loads(text)
            score = float(data.get("score", 0.5))
            reasoning = str(data.get("reasoning", ""))[:300]
        except Exception as e:
            logger.debug(f"[auto-judge] parse error for result {result.id}: {e}")
            # Don't persist fake 0.5 scores — skip this item entirely (#64)
            continue

        judge_evals.append(JudgeEvaluation(
            campaign_id=campaign_id,
            run_id=result.run_id,
            result_id=result.id,
            judge_model=judge_model,
            judge_score=score,
            judge_reasoning=reasoning,
        ))

    if judge_evals:
        session.add_all(judge_evals)
        session.commit()


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
    """Run one model × benchmark. Streams items to DB as they complete."""
    from pathlib import Path
    from eval_engine.base import ItemResult as _ItemResult

    if benchmark.dataset_path:
        dataset_file = Path(settings.bench_library_path) / benchmark.dataset_path
        logger.info(f"Benchmark '{benchmark.name}': {dataset_file} (exists={dataset_file.exists()})")

    try:
        runner = get_runner(benchmark, settings.bench_library_path)
    except Exception as e:
        raise RuntimeError(f"Failed to get runner for '{benchmark.name}': {e}") from e

    max_samples = campaign.max_samples or benchmark.num_samples or settings.default_max_samples

    # Live item tracking + streaming callback
    # Items are accumulated and flushed to DB every runner_batch_size items to
    # reduce write amplification.  Campaign progress (current_item_index) is
    # updated every runner_progress_heartbeat items so the LiveFeed stays fresh
    # without committing on every single item.
    _item_batch: list[EvalResult] = []
    _items_since_heartbeat: int = 0

    def _progress(current: int, total: int, item_result: _ItemResult = None):
        nonlocal _items_since_heartbeat
        try:
            new_result: EvalResult | None = None
            if item_result is not None:
                new_result = EvalResult(
                    run_id=eval_run_id,
                    item_index=item_result.item_index,
                    prompt=item_result.prompt[:2000],
                    response=item_result.response[:2000],
                    expected=item_result.expected,
                    score=item_result.score,
                    latency_ms=item_result.latency_ms,
                    input_tokens=item_result.input_tokens,
                    output_tokens=item_result.output_tokens,
                    cost_usd=item_result.cost_usd,
                    metadata_json=json.dumps(item_result.metadata),
                )
                _item_batch.append(new_result)
                _items_since_heartbeat += 1

            # Decide whether to flush items and/or update heartbeat
            batch_full = len(_item_batch) >= settings.runner_batch_size
            heartbeat_due = _items_since_heartbeat >= settings.runner_progress_heartbeat
            last_item = (item_result is None)  # explicit flush when item_result is None

            if batch_full or heartbeat_due or last_item:
                with Session(engine) as s:
                    # Flush accumulated EvalResult rows
                    if _item_batch:
                        s.add_all(_item_batch)
                        _item_batch.clear()

                    # Update campaign live tracking
                    if heartbeat_due or last_item:
                        c = s.get(Campaign, campaign.id)
                        if c:
                            c.current_item_index = current
                            c.current_item_total = total
                            c.current_item_label = f"{model.name} → {benchmark.name}"
                            s.add(c)
                        _items_since_heartbeat = 0

                    s.commit()

            # Emit ITEM_COMPLETED event (non-blocking, best-effort)
            if item_result is not None:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(_bus.emit(
                            EventType.ITEM_COMPLETED,
                            campaign_id=campaign.id,
                            run_id=eval_run_id,
                            payload={
                                "item_index": item_result.item_index,
                                "score": item_result.score,
                                "latency_ms": item_result.latency_ms,
                            },
                        ))
                except Exception as e:
                    logger.debug(f"Telemetry emit failed (non-blocking): {e}")  # Never block the eval for telemetry

        except Exception as ex:
            logger.debug(f"Progress callback error (non-blocking): {ex}")

    try:
        summary = await asyncio.wait_for(
            runner.run(
                model=model,
                max_samples=max_samples,
                seed=campaign.seed,
                temperature=campaign.temperature,
                progress_callback=_progress,
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

    # Flush any remaining buffered items that weren't yet committed (partial batch)
    if _item_batch:
        try:
            with Session(engine) as s:
                s.add_all(_item_batch)
                s.commit()
            _item_batch.clear()
        except Exception as ex:
            logger.debug(f"Final batch flush failed (non-blocking): {ex}")

    return summary, summary.item_results

def _compute_genome_for_campaign(campaign_id: int, session: Session) -> None:
    """Compute and store Failure Genome profiles after campaign completes."""
    from sqlmodel import select as _sel_inner
    from core.models import FailureProfile
    from eval_engine.failure_genome.classifiers import classify_run, aggregate_genome
    from eval_engine.failure_genome.ontology import FAILURE_GENOME_VERSION
    import json as _json

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


def _generate_manifest(campaign_id: int, session: Session) -> None:
    """Auto-generate reproducibility manifest after campaign completion."""
    import hashlib
    import platform as _platform
    from core.models import ExperimentManifest, Benchmark

    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        return

    runs = session.exec(select(EvalRun).where(EvalRun.campaign_id == campaign_id)).all()
    completed = [r for r in runs if r.status == JobStatus.COMPLETED]

    model_ids = list(set(r.model_id for r in runs))
    benchmark_ids = list(set(r.benchmark_id for r in runs))

    models = session.exec(select(LLMModel).where(LLMModel.id.in_(model_ids))).all()
    benchmarks = session.exec(select(Benchmark).where(Benchmark.id.in_(benchmark_ids))).all()

    model_configs = [
        {"model_id": m.id, "name": m.name, "provider": m.provider, "model_id_str": m.model_id}
        for m in models
    ]
    bench_configs = [
        {"bench_id": b.id, "name": b.name, "metric": b.metric,
         "eval_dimension": getattr(b, "eval_dimension", "capability")}
        for b in benchmarks
    ]

    scores = [r.score for r in completed if r.score is not None]
    cap = [r.capability_score for r in completed if getattr(r, "capability_score", None) is not None]
    prop = [r.propensity_score for r in completed if getattr(r, "propensity_score", None) is not None]

    config_str = json.dumps({
        "models": sorted([m["model_id_str"] for m in model_configs]),
        "benchmarks": sorted([b["name"] for b in bench_configs]),
        "seed": campaign.seed, "temperature": campaign.temperature,
    }, sort_keys=True)

    manifest = ExperimentManifest(
        campaign_id=campaign_id,
        experiment_hash=hashlib.sha256(config_str.encode()).hexdigest(),
        model_configs_json=json.dumps(model_configs),
        benchmark_configs_json=json.dumps(bench_configs),
        seed=campaign.seed,
        temperature=campaign.temperature,
        platform_version=settings.app_version,
        python_version=_platform.python_version(),
        total_runs=len(runs),
        total_items=sum(r.num_items for r in completed),
        avg_score=round(sum(scores) / len(scores), 4) if scores else None,
        avg_capability_score=round(sum(cap) / len(cap), 4) if cap else None,
        avg_propensity_score=round(sum(prop) / len(prop), 4) if prop else None,
    )
    session.add(manifest)
    session.commit()
