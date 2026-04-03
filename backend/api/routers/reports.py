"""
Report generation: sends campaign results to Claude and returns a structured
markdown analysis (strengths, weaknesses, recommendations, safety alerts).
"""
import json
from datetime import datetime

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from core.database import get_session
from core.config import get_settings
from core.models import Campaign, EvalRun, LLMModel, Benchmark, Report, JobStatus

router = APIRouter(prefix="/reports", tags=["reports"])
settings = get_settings()


class ReportRequest(BaseModel):
    campaign_id: int
    custom_instructions: str = ""
    stream: bool = False


class ReportRead(BaseModel):
    id: int
    campaign_id: int
    title: str
    content_markdown: str
    model_used: str
    created_at: datetime


def _build_system_prompt() -> str:
    return (
        "You are an expert AI evaluation analyst specializing in frontier model assessment. "
        "Write clear, rigorous, actionable evaluation reports for ML engineers and safety researchers. "
        "Use Markdown with clear headings. Lead with an executive summary. "
        "Flag safety violations prominently. Be precise, not vague. "
        "Tone: technical but readable."
    )


def _build_user_prompt(campaign, runs, models, benches, custom_instructions):
    results_summary = []
    for run in runs:
        if run.status != JobStatus.COMPLETED:
            continue
        model_name = models.get(run.model_id, LLMModel(name=f"Model#{run.model_id}")).name
        bench_name = benches.get(run.benchmark_id, Benchmark(name=f"Bench#{run.benchmark_id}")).name
        metrics = json.loads(run.metrics_json)
        results_summary.append({
            "model": model_name,
            "benchmark": bench_name,
            "score": run.score,
            "metrics": metrics,
            "cost_usd": run.total_cost_usd,
            "avg_latency_ms": run.total_latency_ms / max(run.num_items, 1),
            "num_items": run.num_items,
        })

    violations = []
    for run in runs:
        bench = benches.get(run.benchmark_id)
        if bench and bench.risk_threshold and run.score is not None:
            if run.score < bench.risk_threshold:
                model_name = models.get(run.model_id, LLMModel(name="?")).name
                violations.append(
                    f"{model_name} scored {run.score:.2%} on {bench.name} "
                    f"(threshold: {bench.risk_threshold:.2%})"
                )

    return f"""# Evaluation Campaign: {campaign.name}

Description: {campaign.description or "N/A"}
Seed: {campaign.seed} | Temperature: {campaign.temperature}

## Results
```json
{json.dumps(results_summary, indent=2)}
```

## Safety Threshold Violations
{chr(10).join(f"- {v}" for v in violations) if violations else "None detected."}

## Custom Instructions
{custom_instructions or "None."}

Write a comprehensive report: Executive Summary, Per-Model Analysis,
Benchmark Breakdown, Safety Assessment, Cost/Efficiency, Head-to-Head
Comparison, Recommendations, Methodological Limitations.
"""


@router.post("/generate", response_model=ReportRead)
async def generate_report(payload: ReportRequest, session: Session = Depends(get_session)):
    campaign = session.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    if campaign.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Campaign must be completed first.")

    runs = session.exec(select(EvalRun).where(EvalRun.campaign_id == payload.campaign_id)).all()
    model_ids = list({r.model_id for r in runs})
    bench_ids = list({r.benchmark_id for r in runs})
    models_map = {m.id: m for m in session.exec(select(LLMModel).where(LLMModel.id.in_(model_ids))).all()}
    benches_map = {b.id: b for b in session.exec(select(Benchmark).where(Benchmark.id.in_(bench_ids))).all()}

    user_prompt = _build_user_prompt(campaign, list(runs), models_map, benches_map, payload.custom_instructions)

    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured.")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.report_model,
        max_tokens=settings.report_max_tokens,
        system=_build_system_prompt(),
        messages=[{"role": "user", "content": user_prompt}],
    )
    content = message.content[0].text

    report = Report(
        campaign_id=payload.campaign_id,
        title=f"Eval Report — {campaign.name}",
        content_markdown=content,
        model_used=settings.report_model,
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    return ReportRead(
        id=report.id, campaign_id=report.campaign_id, title=report.title,
        content_markdown=report.content_markdown, model_used=report.model_used,
        created_at=report.created_at,
    )


@router.get("/campaign/{campaign_id}", response_model=list[ReportRead])
def list_reports(campaign_id: int, session: Session = Depends(get_session)):
    reports_q = session.exec(select(Report).where(Report.campaign_id == campaign_id)).all()
    return [
        ReportRead(id=r.id, campaign_id=r.campaign_id, title=r.title,
                   content_markdown=r.content_markdown, model_used=r.model_used,
                   created_at=r.created_at)
        for r in reports_q
    ]


@router.get("/{report_id}/export.md")
def export_report_markdown(report_id: int, session: Session = Depends(get_session)):
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    return StreamingResponse(
        iter([report.content_markdown]),
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=report_{report_id}.md"},
    )
