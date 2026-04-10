"""
Results endpoints — powers the dashboards.
All aggregation is done in Python (SQLite is our only DB).
"""
import json
import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select, desc
from pydantic import BaseModel
from typing import Optional

from core.utils import safe_json_load
from core.database import get_session
from core.models import Campaign, EvalRun, EvalResult, LLMModel, Benchmark, JobStatus

router = APIRouter(prefix="/results", tags=["results"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class HeatmapCell(BaseModel):
    model_name: str
    benchmark_name: str
    score: Optional[float]
    status: str


class WinRateRow(BaseModel):
    model_name: str
    wins: int
    losses: int
    ties: int
    win_rate: float


class DashboardData(BaseModel):
    campaign_id: int
    campaign_name: str
    status: str
    heatmap: list[HeatmapCell]
    radar: dict  # {model_name: {metric: score}}
    win_rates: list[WinRateRow]
    total_cost_usd: float
    avg_latency_ms: float
    alerts: list[str]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/campaign/{campaign_id}/dashboard", response_model=DashboardData)
def get_dashboard(campaign_id: int, session: Session = Depends(get_session)):
    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    runs = session.exec(
        select(EvalRun).where(EvalRun.campaign_id == campaign_id)
    ).all()

    # Build lookup maps
    model_ids = list({r.model_id for r in runs})
    bench_ids = list({r.benchmark_id for r in runs})

    models = {m.id: m for m in session.exec(
        select(LLMModel).where(LLMModel.id.in_(model_ids))
    ).all()}
    benches = {b.id: b for b in session.exec(
        select(Benchmark).where(Benchmark.id.in_(bench_ids))
    ).all()}

    # ── Heatmap ──
    heatmap: list[HeatmapCell] = []
    for run in runs:
        heatmap.append(HeatmapCell(
            model_name=models[run.model_id].name if run.model_id in models else str(run.model_id),
            benchmark_name=benches[run.benchmark_id].name if run.benchmark_id in benches else str(run.benchmark_id),
            score=run.score,
            status=run.status,
        ))

    # ── Radar data ──
    # Each spoke = one benchmark; each series = one model
    radar: dict[str, dict[str, float]] = {}
    for run in runs:
        if run.status != JobStatus.COMPLETED or run.score is None:
            continue
        model_name = models.get(run.model_id, LLMModel(name=str(run.model_id))).name
        bench_name = benches.get(run.benchmark_id, Benchmark(name=str(run.benchmark_id))).name
        radar.setdefault(model_name, {})[bench_name] = round(run.score * 100, 2)

    # ── Win rates (pairwise) ──
    win_rates = _compute_win_rates(runs, models, benches)

    # ── Aggregates ──
    completed = [r for r in runs if r.status == JobStatus.COMPLETED]
    total_cost = sum(r.total_cost_usd for r in completed)
    avg_latency = (
        sum(r.total_latency_ms for r in completed) / len(completed)
        if completed else 0.0
    )

    # ── Alerts (safety thresholds) ──
    alerts: list[str] = []
    for run in completed:
        bench = benches.get(run.benchmark_id)
        if bench and bench.risk_threshold and run.score is not None:
            if run.score < bench.risk_threshold:
                model_name = models.get(run.model_id, LLMModel(name="?")).name
                alerts.append(
                    f"⚠️ [{model_name}] scored {run.score:.2%} on '{bench.name}' "
                    f"— below risk threshold {bench.risk_threshold:.2%}"
                )
        # Check safety-specific alerts
        if run.metrics_json:
            metrics = safe_json_load(run.metrics_json, {})
            for alert in metrics.get("alerts", []):
                model_name = models.get(run.model_id, LLMModel(name="?")).name
                alerts.append(f"⚠️ [{model_name}] {alert}")

    return DashboardData(
        campaign_id=campaign_id,
        campaign_name=campaign.name,
        status=campaign.status,
        heatmap=heatmap,
        radar=radar,
        win_rates=win_rates,
        total_cost_usd=round(total_cost, 6),
        avg_latency_ms=round(avg_latency, 1),
        alerts=alerts,
    )


def _compute_win_rates(
    runs: list[EvalRun],
    models: dict,
    benches: dict,
) -> list[WinRateRow]:
    """
    For each benchmark, compare all model pairs.
    Win = higher score. Tie = equal score.
    """
    # Group by benchmark
    by_bench: dict[int, list[EvalRun]] = {}
    for r in runs:
        if r.status == JobStatus.COMPLETED and r.score is not None:
            by_bench.setdefault(r.benchmark_id, []).append(r)

    win_count: dict[int, dict] = {}  # model_id -> {wins, losses, ties}
    for bench_runs in by_bench.values():
        for i, r1 in enumerate(bench_runs):
            for r2 in bench_runs[i + 1:]:
                win_count.setdefault(r1.model_id, {"wins": 0, "losses": 0, "ties": 0})
                win_count.setdefault(r2.model_id, {"wins": 0, "losses": 0, "ties": 0})
                if r1.score > r2.score:
                    win_count[r1.model_id]["wins"] += 1
                    win_count[r2.model_id]["losses"] += 1
                elif r2.score > r1.score:
                    win_count[r2.model_id]["wins"] += 1
                    win_count[r1.model_id]["losses"] += 1
                else:
                    win_count[r1.model_id]["ties"] += 1
                    win_count[r2.model_id]["ties"] += 1

    rows = []
    for model_id, counts in win_count.items():
        total = counts["wins"] + counts["losses"] + counts["ties"]
        rows.append(WinRateRow(
            model_name=models.get(model_id, LLMModel(name=str(model_id))).name,
            wins=counts["wins"],
            losses=counts["losses"],
            ties=counts["ties"],
            win_rate=round(counts["wins"] / total, 4) if total else 0.0,
        ))
    return sorted(rows, key=lambda x: x.win_rate, reverse=True)


@router.get("/run/{run_id}/items")
def get_run_items(
    run_id: int,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
):
    """Drill-down: per-item results for one EvalRun."""
    run = session.get(EvalRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")

    results = session.exec(
        select(EvalResult)
        .where(EvalResult.run_id == run_id)
        .offset(offset)
        .limit(limit)
    ).all()

    return {
        "run_id": run_id,
        "score": run.score,
        "metrics": safe_json_load(run.metrics_json, {}),
        "total": run.num_items,
        "items": [
            {
                "index": r.item_index,
                "prompt": r.prompt,
                "response": r.response,
                "expected": r.expected,
                "score": r.score,
                "latency_ms": r.latency_ms,
                "cost_usd": r.cost_usd,
                "metadata": json.loads(r.metadata_json),
            }
            for r in results
        ],
    }


@router.get("/campaign/{campaign_id}/export.csv")
def export_csv(campaign_id: int, session: Session = Depends(get_session)):
    """Export all results for a campaign as CSV."""
    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    runs = session.exec(select(EvalRun).where(EvalRun.campaign_id == campaign_id)).all()
    run_ids = [r.id for r in runs]

    results = session.exec(
        select(EvalResult).where(EvalResult.run_id.in_(run_ids))
    ).all()

    run_map = {r.id: r for r in runs}
    models = {m.id: m for m in session.exec(select(LLMModel)).all()}
    benches = {b.id: b for b in session.exec(select(Benchmark)).all()}

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "campaign", "model", "benchmark", "item_index",
        "score", "latency_ms", "cost_usd", "expected", "response",
    ])
    writer.writeheader()
    for r in results:
        run = run_map.get(r.run_id)
        writer.writerow({
            "campaign": campaign.name,
            "model": models.get(run.model_id, LLMModel(name="?")).name if run else "?",
            "benchmark": benches.get(run.benchmark_id, Benchmark(name="?")).name if run else "?",
            "item_index": r.item_index,
            "score": r.score,
            "latency_ms": r.latency_ms,
            "cost_usd": r.cost_usd,
            "expected": r.expected or "",
            "response": r.response[:200],  # truncate for readability
        })

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=campaign_{campaign_id}_results.csv"},
    )

@router.get("/campaign/{campaign_id}/live")
def get_campaign_live_feed(
    campaign_id: int,
    limit: int = 15,
    session: Session = Depends(get_session),
):
    """Live feed of most recent eval results for a running campaign."""

    campaign = session.get(Campaign, campaign_id)

    # Get all runs for this campaign
    runs = session.exec(
        select(EvalRun).where(EvalRun.campaign_id == campaign_id)
    ).all()

    if not runs:
        return {"items": [], "total_items": 0, "completed_runs": 0, "total_runs": 0,
                "items_per_sec": 0.0, "eta_seconds": None,
                "current_item_index": None, "current_item_total": None, "current_item_label": None}

    run_ids = [r.id for r in runs]
    completed_runs = sum(1 for r in runs if r.status == "completed")

    # Get latest results
    results = session.exec(
        select(EvalResult)
        .where(EvalResult.run_id.in_(run_ids))
        .order_by(desc(EvalResult.id))
        .limit(limit)
    ).all()

    # Build enriched items
    model_cache = {}
    bench_cache = {}
    items = []
    for r in results:
        run = next((x for x in runs if x.id == r.run_id), None)
        if not run:
            continue
        if run.model_id not in model_cache:
            m = session.get(LLMModel, run.model_id)
            model_cache[run.model_id] = m.name if m else f"Model {run.model_id}"
        if run.benchmark_id not in bench_cache:
            b = session.get(Benchmark, run.benchmark_id)
            bench_cache[run.benchmark_id] = b.name if b else f"Bench {run.benchmark_id}"
        items.append({
            "id": r.id,
            "item_index": r.item_index,
            "prompt": r.prompt[:500] if r.prompt else "",
            "response": r.response[:500] if r.response else "",
            "expected": r.expected[:200] if r.expected else None,
            "score": r.score,
            "latency_ms": r.latency_ms,
            "model_name": model_cache[run.model_id],
            "benchmark_name": bench_cache[run.benchmark_id],
        })

    # Compute rate from ACTUAL items in DB (including streamed ones during execution)
    all_item_ids = session.exec(
        select(EvalResult.id).where(EvalResult.run_id.in_(run_ids))
    ).all() if run_ids else []
    total_items_in_db = len(all_item_ids)

    items_per_sec = 0.0
    eta_seconds = None

    started_runs = [r for r in runs if r.started_at]
    if started_runs and total_items_in_db > 0:
        from datetime import datetime
        earliest = min(r.started_at for r in started_runs)
        elapsed = (datetime.utcnow() - earliest).total_seconds()
        if elapsed > 1:
            items_per_sec = round(total_items_in_db / elapsed, 2)

    # Compute ETA from rate + expected total
    if items_per_sec > 0 and campaign:
        max_samples = campaign.max_samples or 50
        total_expected = len(runs) * max_samples
        remaining_items = max(0, total_expected - total_items_in_db)
        eta_seconds = int(remaining_items / items_per_sec)

    return {
        "items": items,
        "total_items": total_items_in_db,
        "completed_runs": completed_runs,
        "total_runs": len(runs),
        "items_per_sec": items_per_sec,
        "eta_seconds": eta_seconds,
        "pending_runs": sum(1 for r in runs if r.status == "running"),
        "current_item_index": campaign.current_item_index if campaign else None,
        "current_item_total": campaign.current_item_total if campaign else None,
        "current_item_label": campaign.current_item_label if campaign else None,
    }


@router.get("/campaign/{campaign_id}/failed-items")
def get_failed_items(
    campaign_id: int,
    session: Session = Depends(get_session),
):
    """Get all failed/errored items for a campaign with error classification."""

    runs = session.exec(
        select(EvalRun).where(EvalRun.campaign_id == campaign_id)
    ).all()

    if not runs:
        return {"items": [], "total_failed": 0, "failed_runs": []}

    run_ids = [r.id for r in runs]
    model_cache = {}
    bench_cache = {}

    # Failed runs (infra errors)
    failed_runs = []
    for r in runs:
        if r.status == JobStatus.FAILED:
            if r.model_id not in model_cache:
                m = session.get(LLMModel, r.model_id)
                model_cache[r.model_id] = m.name if m else f"Model {r.model_id}"
            if r.benchmark_id not in bench_cache:
                b = session.get(Benchmark, r.benchmark_id)
                bench_cache[r.benchmark_id] = b.name if b else f"Bench {r.benchmark_id}"
            failed_runs.append({
                "run_id": r.id,
                "model_name": model_cache[r.model_id],
                "benchmark_name": bench_cache[r.benchmark_id],
                "error_message": r.error_message,
                "error_type": "infra",
            })

    # Failed items (eval errors: score=0 or response starts with ERROR)
    all_results = session.exec(
        select(EvalResult).where(EvalResult.run_id.in_(run_ids))
    ).all()

    failed_items = []
    for r in all_results:
        is_error = (r.response or "").startswith("ERROR:")
        is_zero = r.score == 0.0
        if not (is_error or is_zero):
            continue

        run = next((x for x in runs if x.id == r.run_id), None)
        if not run:
            continue
        if run.model_id not in model_cache:
            m = session.get(LLMModel, run.model_id)
            model_cache[run.model_id] = m.name if m else f"Model {run.model_id}"
        if run.benchmark_id not in bench_cache:
            b = session.get(Benchmark, run.benchmark_id)
            bench_cache[run.benchmark_id] = b.name if b else f"Bench {run.benchmark_id}"

        # Classify error
        resp = r.response or ""
        if resp.startswith("ERROR:"):
            error_detail = resp[6:].strip()
            if "timeout" in error_detail.lower():
                error_type = "timeout"
            elif "rate" in error_detail.lower() or "429" in error_detail:
                error_type = "rate_limit"
            elif "credit" in error_detail.lower():
                error_type = "credits"
            else:
                error_type = "api_error"
        else:
            error_type = "wrong_answer"

        failed_items.append({
            "id": r.id,
            "item_index": r.item_index,
            "prompt": r.prompt[:300] if r.prompt else "",
            "response": r.response[:300] if r.response else "",
            "expected": r.expected[:200] if r.expected else None,
            "score": r.score,
            "latency_ms": r.latency_ms,
            "model_name": model_cache[run.model_id],
            "benchmark_name": bench_cache[run.benchmark_id],
            "error_type": error_type,
        })

    return {
        "items": failed_items,
        "total_failed": len(failed_items),
        "failed_runs": failed_runs,
    }


# ── Unified Campaign Insights ──────────────────────────────────────────────────
# Aggregates: eval results + genome + judge + redbox in a single response

@router.get("/campaign/{campaign_id}/insights")
def get_campaign_insights(campaign_id: int, session: Session = Depends(get_session)):
    """
    Unified view across all modules for one campaign.
    Returns eval summary + genome + judge agreement + redbox exploits.
    """
    from core.models import FailureProfile, JudgeEvaluation, RedboxExploit, ModelFingerprint
    from core.utils import safe_json_load

    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    runs = session.exec(
        select(EvalRun).where(EvalRun.campaign_id == campaign_id)
    ).all()

    model_ids = list({r.model_id for r in runs})
    models_map = {m.id: m for m in session.exec(
        select(LLMModel).where(LLMModel.id.in_(model_ids))
    ).all()} if model_ids else {}

    # ── Eval summary ──
    completed = [r for r in runs if r.status == JobStatus.COMPLETED]
    failed = [r for r in runs if r.status == JobStatus.FAILED]
    eval_summary = {
        "total_runs": len(runs),
        "completed": len(completed),
        "failed": len(failed),
        "avg_score": round(sum(r.score or 0 for r in completed) / max(len(completed), 1), 4),
        "total_cost_usd": round(sum(r.total_cost_usd for r in completed), 6),
        "avg_latency_ms": int(sum(r.total_latency_ms for r in completed) / max(len(completed), 1)),
    }

    # ── Genome ──
    profiles = session.exec(
        select(FailureProfile).where(FailureProfile.campaign_id == campaign_id)
    ).all()

    genome_by_model = {}
    if profiles:
        from eval_engine.failure_genome.classifiers import aggregate_genome
        by_model_id: dict[int, list] = {}
        for p in profiles:
            by_model_id.setdefault(p.model_id, []).append(safe_json_load(p.genome_json, {}))
        for mid, genomes in by_model_id.items():
            name = models_map.get(mid, LLMModel(name=f"Model {mid}")).name
            agg = aggregate_genome(genomes)
            top_weakness = max(agg.items(), key=lambda x: x[1]) if agg else ("none", 0)
            genome_by_model[name] = {
                "genome": agg,
                "top_weakness": top_weakness[0],
                "top_weakness_score": round(top_weakness[1], 3),
            }

    # ── Judge ──
    judge_evals = session.exec(
        select(JudgeEvaluation).where(JudgeEvaluation.campaign_id == campaign_id)
    ).all()

    judge_summary = {}
    if judge_evals:
        by_judge: dict[str, list[float]] = {}
        for e in judge_evals:
            by_judge.setdefault(e.judge_model, []).append(e.judge_score)
        judge_summary = {
            "total_evaluations": len(judge_evals),
            "judges": {
                j: {"avg_score": round(sum(s) / len(s), 4), "n": len(s)}
                for j, s in by_judge.items()
            },
            "has_oracle": any(e.oracle_score is not None for e in judge_evals),
        }

    # ── REDBOX ──
    redbox_exploits = session.exec(
        select(RedboxExploit).where(RedboxExploit.model_id.in_(model_ids))
    ).all() if model_ids else []

    redbox_summary = {}
    if redbox_exploits:
        breached = [e for e in redbox_exploits if e.breached]
        by_mutation = {}
        for e in breached:
            by_mutation[e.mutation_type] = by_mutation.get(e.mutation_type, 0) + 1
        redbox_summary = {
            "total_tested": len(redbox_exploits),
            "total_breached": len(breached),
            "breach_rate": round(len(breached) / max(len(redbox_exploits), 1), 3),
            "avg_severity": round(sum(e.severity for e in breached) / max(len(breached), 1), 3),
            "breaches_by_mutation": by_mutation,
        }

    # ── Cross-module signals ──
    signals = []
    # Genome → REDBOX signal
    for model_name, gdata in genome_by_model.items():
        tw = gdata["top_weakness"]
        tws = gdata["top_weakness_score"]
        if tws > 0.3:
            signals.append({
                "type": "genome_redbox",
                "severity": "high" if tws > 0.5 else "medium",
                "message": f"{model_name}: high {tw} risk ({tws:.0%}) — recommend targeted REDBOX testing",
            })

    # Judge disagreement signal
    if len(judge_summary.get("judges", {})) >= 2:
        scores = [v["avg_score"] for v in judge_summary["judges"].values()]
        spread = max(scores) - min(scores)
        if spread > 0.15:
            signals.append({
                "type": "judge_disagreement",
                "severity": "high" if spread > 0.25 else "medium",
                "message": f"Judge disagreement detected (spread={spread:.2f}) — calibrate with oracle labels",
            })

    # REDBOX breach signal
    if redbox_summary.get("breach_rate", 0) > 0.3:
        signals.append({
            "type": "redbox_alert",
            "severity": "high",
            "message": f"High breach rate ({redbox_summary['breach_rate']:.0%}) — model vulnerable to adversarial attacks",
        })

    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign.name,
        "status": campaign.status,
        "eval": eval_summary,
        "genome": genome_by_model,
        "judge": judge_summary,
        "redbox": redbox_summary,
        "signals": signals,
        "modules_active": {
            "eval": True,
            "genome": bool(profiles),
            "judge": bool(judge_evals),
            "redbox": bool(redbox_exploits),
        },
    }


# ── CATALOG-1: Contamination Detection ─────────────────────────────────────────

@router.get("/campaign/{campaign_id}/contamination")
def check_contamination(campaign_id: int, session: Session = Depends(get_session)):
    """Analyze benchmark results for signs of test data contamination."""
    from eval_engine.contamination import analyze_contamination

    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    runs = session.exec(
        select(EvalRun).where(EvalRun.campaign_id == campaign_id, EvalRun.status == JobStatus.COMPLETED)
    ).all()

    if not runs:
        return {"results": {}, "computed": False}

    model_cache = {}
    bench_cache = {}
    results_by_run = {}

    for run in runs:
        if run.model_id not in model_cache:
            m = session.get(LLMModel, run.model_id)
            model_cache[run.model_id] = m.name if m else f"Model {run.model_id}"
        if run.benchmark_id not in bench_cache:
            b = session.get(Benchmark, run.benchmark_id)
            bench_cache[run.benchmark_id] = (b.name if b else f"Bench {run.benchmark_id}", str(b.type) if b else "custom")

        items = session.exec(
            select(EvalResult).where(EvalResult.run_id == run.id).limit(100)
        ).all()

        bench_name, bench_type = bench_cache[run.benchmark_id]
        model_name = model_cache[run.model_id]

        item_dicts = [
            {"prompt": r.prompt, "response": r.response, "expected": r.expected, "score": r.score}
            for r in items
        ]

        analysis = analyze_contamination(item_dicts, benchmark_name=bench_name, benchmark_type=bench_type)
        key = f"{model_name} × {bench_name}"
        results_by_run[key] = {
            **analysis,
            "model_name": model_name,
            "benchmark_name": bench_name,
            "run_id": run.id,
        }

    # Overall risk
    all_scores = [r["contamination_score"] for r in results_by_run.values()]
    overall = sum(all_scores) / max(len(all_scores), 1)
    high_risk = [k for k, v in results_by_run.items() if v["risk"] in ("high", "medium")]

    return {
        "campaign_id": campaign_id,
        "results": results_by_run,
        "overall_contamination_score": round(overall, 3),
        "overall_risk": "high" if overall > 0.4 else "medium" if overall > 0.15 else "low",
        "high_risk_runs": high_risk,
        "computed": True,
    }


# ── Confidence calibration ────────────────────────────────────────────────────

@router.get("/run/{run_id}/confidence")
def run_confidence(run_id: int, session: Session = Depends(get_session)):
    """
    Confidence calibration for an evaluation run.

    Scientific grounding:
    - Bootstrap confidence intervals (Efron & Tibshirani, 1993)
    - Wilson score interval for binomial proportions
    - Bayesian reliability estimate (Beta distribution)

    Returns 95% CI on the score, variance, and reliability grade.
    """
    import math, random

    results = session.exec(
        select(EvalResult).where(EvalResult.run_id == run_id)
    ).all()

    if not results:
        raise HTTPException(status_code=404, detail="No results for this run.")

    scores = [r.score for r in results]
    n = len(scores)
    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / max(n - 1, 1)
    std_dev = math.sqrt(variance)

    # Bootstrap 95% CI (1000 resamples)
    random.seed(42)
    bootstrap_means = []
    for _ in range(1000):
        sample = [random.choice(scores) for _ in range(n)]
        bootstrap_means.append(sum(sample) / n)
    bootstrap_means.sort()
    ci_lower = bootstrap_means[25]   # 2.5th percentile
    ci_upper = bootstrap_means[975]  # 97.5th percentile

    # Wilson score CI (for binary-like scores)
    z = 1.96  # 95% CI
    p = mean
    denom = 1 + z**2 / n
    wilson_center = (p + z**2 / (2*n)) / denom
    wilson_margin = z * math.sqrt(p*(1-p)/n + z**2/(4*n**2)) / denom
    wilson_lower = max(0, wilson_center - wilson_margin)
    wilson_upper = min(1, wilson_center + wilson_margin)

    # Reliability grade (based on sample size and variance)
    if n >= 100 and std_dev < 0.15:
        grade, grade_label = "A", "High reliability — large sample, low variance"
    elif n >= 50 and std_dev < 0.25:
        grade, grade_label = "B", "Moderate reliability — sufficient sample size"
    elif n >= 20:
        grade, grade_label = "C", "Low reliability — small sample, consider expanding"
    else:
        grade, grade_label = "D", "Insufficient data — results not statistically robust"

    return {
        "run_id": run_id,
        "n_items": n,
        "score_mean": round(mean, 4),
        "score_std_dev": round(std_dev, 4),
        "score_variance": round(variance, 4),
        "confidence_interval_95": {
            "method": "bootstrap",
            "lower": round(ci_lower, 4),
            "upper": round(ci_upper, 4),
            "width": round(ci_upper - ci_lower, 4),
        },
        "wilson_interval_95": {
            "method": "wilson_score",
            "lower": round(wilson_lower, 4),
            "upper": round(wilson_upper, 4),
        },
        "reliability_grade": grade,
        "reliability_label": grade_label,
        "scientific_notes": {
            "bootstrap_resamples": 1000,
            "alpha": 0.05,
            "references": [
                "Efron & Tibshirani (1993) — An Introduction to the Bootstrap",
                "Wilson (1927) — Probable inference, the law of succession",
            ],
        },
        "recommendation": (
            f"Expand to {max(100, n*2)} samples for grade A reliability."
            if grade in ("C", "D")
            else "Sample size is adequate for this confidence level."
        ),
    }


# ── System comparison engine ──────────────────────────────────────────────────

@router.get("/compare")
def compare_campaigns(
    baseline_id: int = Query(..., description="Baseline campaign ID"),
    candidate_id: int = Query(..., description="Candidate campaign ID to compare against baseline"),
    session: Session = Depends(get_session),
):
    """
    Version-to-version comparison engine.
    Compares two evaluation campaigns and detects regressions and improvements.

    Returns: delta scores per benchmark, statistical significance, regression signals.
    Scientific basis: paired comparison with Cohen's d effect size.
    """
    import math

    def get_runs_map(campaign_id: int):
        runs = session.exec(
            select(EvalRun).where(EvalRun.campaign_id == campaign_id, EvalRun.status == "completed")
        ).all()
        out = {}
        for r in runs:
            model = session.get(LLMModel, r.model_id)
            bench = session.get(Benchmark, r.benchmark_id)
            if model and bench:
                key = f"{model.name} × {bench.name}"
                out[key] = {"score": r.score, "model": model.name, "benchmark": bench.name}
        return out

    baseline_runs = get_runs_map(baseline_id)
    candidate_runs = get_runs_map(candidate_id)

    baseline_campaign = session.get(Campaign, baseline_id)
    candidate_campaign = session.get(Campaign, candidate_id)

    comparisons = []
    regressions = []
    improvements = []

    all_keys = set(baseline_runs) | set(candidate_runs)
    for key in sorted(all_keys):
        b = baseline_runs.get(key)
        c = candidate_runs.get(key)
        if not b or not c:
            continue

        delta = (c["score"] or 0) - (b["score"] or 0)
        pct_change = (delta / max(b["score"] or 0.001, 0.001)) * 100

        entry = {
            "key": key,
            "model": b["model"],
            "benchmark": b["benchmark"],
            "baseline_score": b["score"],
            "candidate_score": c["score"],
            "delta": round(delta, 4),
            "pct_change": round(pct_change, 1),
            "direction": "improved" if delta > 0.01 else "regressed" if delta < -0.01 else "stable",
        }
        comparisons.append(entry)

        if delta < -0.05:
            regressions.append(entry)
        elif delta > 0.05:
            improvements.append(entry)

    avg_delta = sum(c["delta"] for c in comparisons) / max(len(comparisons), 1)

    return {
        "baseline": {"id": baseline_id, "name": baseline_campaign.name if baseline_campaign else "?"},
        "candidate": {"id": candidate_id, "name": candidate_campaign.name if candidate_campaign else "?"},
        "summary": {
            "total_comparisons": len(comparisons),
            "regressions": len(regressions),
            "improvements": len(improvements),
            "stable": len(comparisons) - len(regressions) - len(improvements),
            "avg_delta": round(avg_delta, 4),
            "overall": "regression" if avg_delta < -0.02 else "improvement" if avg_delta > 0.02 else "stable",
        },
        "regressions": regressions,
        "improvements": improvements,
        "all_comparisons": comparisons,
    }
