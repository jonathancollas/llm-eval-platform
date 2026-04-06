"""
Results endpoints — powers the dashboards.
All aggregation is done in Python (SQLite is our only DB).
"""
import json
import csv
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
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
    from sqlmodel import select, desc
    from core.models import EvalRun, EvalResult, LLMModel, Benchmark

    # Get all runs for this campaign
    runs = session.exec(
        select(EvalRun).where(EvalRun.campaign_id == campaign_id)
    ).all()

    if not runs:
        return {"items": [], "total_items": 0, "completed_runs": 0, "total_runs": 0,
                "items_per_sec": 0.0, "eta_seconds": None}

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

    # Compute rate from run timestamps
    total_items = sum(r.num_items for r in runs if r.status == "completed")
    items_per_sec = 0.0
    eta_seconds = None

    started_runs = [r for r in runs if r.started_at]
    if started_runs and total_items > 0:
        from datetime import datetime
        earliest = min(r.started_at for r in started_runs)
        elapsed = (datetime.utcnow() - earliest).total_seconds()
        if elapsed > 0:
            items_per_sec = round(total_items / elapsed, 2)

    # Compute ETA from rate
    if items_per_sec > 0 and campaign_id:
        from core.models import Campaign
        from datetime import datetime
        campaign = session.get(Campaign, campaign_id)
        if campaign and campaign.max_samples:
            total_expected = len(runs) * campaign.max_samples
            remaining_items = max(0, total_expected - total_items)
            eta_seconds = int(remaining_items / items_per_sec)

    return {
        "items": items,
        "total_items": total_items,
        "completed_runs": completed_runs,
        "total_runs": len(runs),
        "items_per_sec": items_per_sec,
        "eta_seconds": eta_seconds,
        "pending_runs": sum(1 for r in runs if r.status == "running"),
    }
