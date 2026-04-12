"""
Results endpoints — powers the dashboards.
All aggregation is done in Python (SQLite is our only DB).
Engine-driven refactor (#88): logic in eval_engine/, routes orchestrate only.
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
from eval_engine.confidence_engine import compute_confidence
from eval_engine.comparison_engine import compare_campaigns as _compare_campaigns_engine
from eval_engine.win_rate_engine import compute_win_rates

router = APIRouter(prefix="/results", tags=["results"])

_CSV_FORMULA_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _csv_escape(value: str) -> str:
    """Prevent CSV formula injection by prefixing formula-triggering characters.

    Leading whitespace is stripped before the check so that values like
    ' =cmd' (space then formula) are also caught.
    """
    if value and value.lstrip()[0:1] in _CSV_FORMULA_CHARS:
        return "'" + value
    return value


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


# _compute_win_rates moved to eval_engine/win_rate_engine.py (#88)


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
                "metadata": safe_json_load(r.metadata_json, {}),
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
    model_ids = list({r.model_id for r in runs})
    bench_ids = list({r.benchmark_id for r in runs})
    models = {m.id: m for m in session.exec(
        select(LLMModel).where(LLMModel.id.in_(model_ids))
    ).all()}
    benches = {b.id: b for b in session.exec(
        select(Benchmark).where(Benchmark.id.in_(bench_ids))
    ).all()}

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "campaign", "model", "benchmark", "item_index",
        "score", "latency_ms", "cost_usd", "expected", "response",
    ])
    writer.writeheader()
    for r in results:
        run = run_map.get(r.run_id)
        writer.writerow({
            "campaign": _csv_escape(campaign.name),
            "model": _csv_escape(models.get(run.model_id, LLMModel(name="?")).name if run else "?"),
            "benchmark": _csv_escape(benches.get(run.benchmark_id, Benchmark(name="?")).name if run else "?"),
            "item_index": r.item_index,
            "score": r.score,
            "latency_ms": r.latency_ms,
            "cost_usd": r.cost_usd,
            "expected": _csv_escape(r.expected or ""),
            "response": _csv_escape(r.response[:200]),  # truncate for readability
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
    Logic in eval_engine/confidence_engine.py (#88).

    Returns 95% bootstrap CI, Wilson interval, reliability grade A-D.
    """
    results = session.exec(
        select(EvalResult).where(EvalResult.run_id == run_id)
    ).all()
    if not results:
        raise HTTPException(status_code=404, detail="No results for this run.")

    scores = [r.score for r in results if r.score is not None]
    if not scores:
        raise HTTPException(status_code=422, detail="No scored items for this run.")

    r = compute_confidence(run_id, scores)
    return {
        "run_id": r.run_id,
        "n_items": r.n_items,
        "score_mean": r.score_mean,
        "score_std_dev": r.score_std_dev,
        "score_variance": r.score_variance,
        "confidence_interval_95": {
            "method": "bootstrap",
            "lower": r.ci_lower,
            "upper": r.ci_upper,
            "width": r.ci_width,
        },
        "wilson_interval_95": {
            "method": "wilson_score",
            "lower": r.wilson_lower,
            "upper": r.wilson_upper,
        },
        "reliability_grade": r.reliability_grade,
        "reliability_label": r.reliability_label,
        "scientific_notes": {
            "bootstrap_resamples": 1000,
            "alpha": 0.05,
            "references": [
                "Efron & Tibshirani (1993) — An Introduction to the Bootstrap",
                "Wilson (1927) — Probable inference, the law of succession",
            ],
        },
        "recommendation": r.recommendation,
    }


# ── System comparison engine (#88 — uses eval_engine/comparison_engine.py) ────

@router.get("/compare")
def compare_campaigns_endpoint(
    baseline_id: int = Query(..., description="Baseline campaign ID"),
    candidate_id: int = Query(..., description="Candidate campaign ID"),
    session: Session = Depends(get_session),
):
    """
    Version-to-version comparison. Logic lives in eval_engine/comparison_engine.py.
    Compares two campaigns and detects regressions and improvements.
    """
    def get_runs_map(campaign_id: int) -> dict:
        runs = session.exec(
            select(EvalRun).where(
                EvalRun.campaign_id == campaign_id,
                EvalRun.status == JobStatus.COMPLETED,
            )
        ).all()
        out = {}
        for r in runs:
            model = session.get(LLMModel, r.model_id)
            bench = session.get(Benchmark, r.benchmark_id)
            if model and bench and r.score is not None:
                key = f"{model.name} × {bench.name}"
                out[key] = {"score": r.score, "model": model.name, "benchmark": bench.name}
        return out

    b_runs = get_runs_map(baseline_id)
    c_runs = get_runs_map(candidate_id)
    b_camp = session.get(Campaign, baseline_id)
    c_camp = session.get(Campaign, candidate_id)

    report = _compare_campaigns_engine(
        baseline_runs=b_runs,
        candidate_runs=c_runs,
        baseline_id=baseline_id,
        candidate_id=candidate_id,
        baseline_name=b_camp.name if b_camp else "?",
        candidate_name=c_camp.name if c_camp else "?",
    )

    def _entry(e):
        return {
            "key": e.key, "model": e.model, "benchmark": e.benchmark,
            "baseline_score": e.baseline_score, "candidate_score": e.candidate_score,
            "delta": e.delta, "pct_change": e.pct_change, "direction": e.direction,
        }

    return {
        "baseline":  {"id": report.baseline_id,  "name": report.baseline_name},
        "candidate": {"id": report.candidate_id, "name": report.candidate_name},
        "summary": {
            "total_comparisons": report.total_comparisons,
            "regressions":  len(report.regressions),
            "improvements": len(report.improvements),
            "stable":       report.stable,
            "avg_delta":    report.avg_delta,
            "overall":      report.overall,
        },
        "regressions":   [_entry(e) for e in report.regressions],
        "improvements":  [_entry(e) for e in report.improvements],
        "all_comparisons": [_entry(e) for e in report.all_comparisons],
    }
