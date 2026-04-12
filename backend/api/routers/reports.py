"""
Report generation: sends campaign results to Claude and returns a structured
markdown analysis (strengths, weaknesses, recommendations, safety alerts).
Now async with timeout, retry, and proper error handling.
"""
import asyncio
import json
import logging
from datetime import datetime

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from core.database import get_session
from core.config import get_settings
from core.models import Campaign, EvalRun, EvalResult, LLMModel, Benchmark, Report, JobStatus, FailureProfile
from core.utils import safe_json_load
from core.utils import safe_extract_text
from core.relations import get_eval_run_metrics

router = APIRouter(prefix="/reports", tags=["reports"])
settings = get_settings()
logger = logging.getLogger(__name__)


class ReportRequest(BaseModel):
    campaign_id: int
    custom_instructions: str = ""
    include_genome: bool = True
    ollama_model: str = ""   # If set, use this local Ollama model instead of default


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
        "Tone: technical but readable. Write in French if the campaign description is in French."
    )


def _build_user_prompt(session, campaign, runs, models, benches, custom_instructions, genome_data=None, failed_summary=None):
    results_summary = []
    for run in runs:
        if run.status != JobStatus.COMPLETED:
            continue
        model_name = models.get(run.model_id, LLMModel(name=f"Model#{run.model_id}")).name
        bench_name = benches.get(run.benchmark_id, Benchmark(name=f"Bench#{run.benchmark_id}")).name
        metrics = get_eval_run_metrics(session, run)
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

    # Failed runs
    failed_runs_info = []
    for run in runs:
        if run.status == JobStatus.FAILED:
            model_name = models.get(run.model_id, LLMModel(name="?")).name
            bench_name = benches.get(run.benchmark_id, Benchmark(name="?")).name
            failed_runs_info.append(f"{model_name} × {bench_name}: {run.error_message or 'Unknown error'}")

    prompt = f"""# Evaluation Campaign: {campaign.name}

Description: {campaign.description or "N/A"}
Seed: {campaign.seed} | Temperature: {campaign.temperature} | Max samples: {campaign.max_samples}

## Results
```json
{json.dumps(results_summary, indent=2)}
```

## Safety Threshold Violations
{chr(10).join(f"- {v}" for v in violations) if violations else "None detected."}

## Failed Runs ({len(failed_runs_info)})
{chr(10).join(f"- {f}" for f in failed_runs_info) if failed_runs_info else "None."}
"""

    if genome_data:
        prompt += f"""
## Failure Genome Analysis
```json
{json.dumps(genome_data, indent=2)}
```
Analyze the failure genome patterns. Identify which models are most prone to hallucination, reasoning collapse, safety bypass, etc.
"""

    if failed_summary:
        prompt += f"""
## Failed Items Summary
{failed_summary}
Analyze the error patterns: are they concentrated on specific models? benchmarks? error types?
"""

    prompt += f"""
## Custom Instructions
{custom_instructions or "None."}

Write a comprehensive report: Executive Summary, Per-Model Analysis,
Benchmark Breakdown, Safety Assessment, Failure Genome Analysis (if data available),
Cost/Efficiency, Head-to-Head Comparison, Recommendations, Methodological Limitations.
"""
    return prompt


@router.post("/generate", response_model=ReportRead)
async def generate_report(payload: ReportRequest, session: Session = Depends(get_session)):
    campaign = session.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    if campaign.status not in (JobStatus.COMPLETED, JobStatus.FAILED):
        raise HTTPException(status_code=400, detail="Campaign must be completed or failed first.")

    runs = session.exec(select(EvalRun).where(EvalRun.campaign_id == payload.campaign_id)).all()
    model_ids = list({r.model_id for r in runs})
    bench_ids = list({r.benchmark_id for r in runs})
    models_map = {m.id: m for m in session.exec(select(LLMModel).where(LLMModel.id.in_(model_ids))).all()}
    benches_map = {b.id: b for b in session.exec(select(Benchmark).where(Benchmark.id.in_(bench_ids))).all()}

    # Gather genome data if available
    genome_data = None
    if payload.include_genome:
        profiles = session.exec(
            select(FailureProfile).where(FailureProfile.campaign_id == payload.campaign_id)
        ).all()
        if profiles:
            genome_data = {}
            for p in profiles:
                model = session.get(LLMModel, p.model_id)
                name = model.name if model else f"Model {p.model_id}"
                genome_data[name] = safe_json_load(p.genome_json, {})

    # Gather failed items summary
    failed_summary = None
    completed_run_ids = [r.id for r in runs if r.status == JobStatus.COMPLETED]
    if completed_run_ids:
        failed_results = session.exec(
            select(EvalResult).where(
                EvalResult.run_id.in_(completed_run_ids),
                EvalResult.score == 0.0,
            )
        ).all()
        if failed_results:
            by_type = {}
            for r in failed_results:
                resp = r.response or ""
                if resp.startswith("ERROR:"):
                    etype = "api_error"
                else:
                    etype = "wrong_answer"
                by_type[etype] = by_type.get(etype, 0) + 1
            failed_summary = f"Total failed items: {len(failed_results)}. Breakdown: {json.dumps(by_type)}"

    user_prompt = _build_user_prompt(
        session, campaign, list(runs), models_map, benches_map,
        payload.custom_instructions, genome_data, failed_summary,
    )

    if not settings.anthropic_api_key and not settings.ollama_base_url:
        raise HTTPException(status_code=500, detail="No model available for reports. Configure ANTHROPIC_API_KEY or Ollama.")

    # Generate report using best available model (Ollama local → Anthropic)
    from core.utils import generate_text
    try:
        content = await generate_text(
            prompt=user_prompt,
            system_prompt=_build_system_prompt(),
            max_tokens=settings.report_max_tokens,
            timeout=settings.report_timeout_seconds,
            ollama_model=payload.ollama_model or None,
        )
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid ANTHROPIC_API_KEY. Check your configuration.")
    except Exception as e:
        logger.exception(f"Report generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)[:200]}")

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


@router.get("/{report_id}/export.html")
def export_report_html(report_id: int, session: Session = Depends(get_session)):
    """Export report as styled HTML."""
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    campaign = session.get(Campaign, report.campaign_id)
    campaign_name = campaign.name if campaign else "Unknown"

    # Convert markdown to HTML (basic conversion)
    import re
    md = report.content_markdown

    # Headers
    html_body = md
    html_body = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', html_body, flags=re.MULTILINE)
    html_body = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html_body, flags=re.MULTILINE)
    html_body = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html_body, flags=re.MULTILINE)
    html_body = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html_body, flags=re.MULTILINE)
    # Bold, italic
    html_body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_body)
    html_body = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html_body)
    # Code blocks
    html_body = re.sub(r'```(\w*)\n(.*?)```', r'<pre><code>\2</code></pre>', html_body, flags=re.DOTALL)
    html_body = re.sub(r'`(.+?)`', r'<code>\1</code>', html_body)
    # Lists
    html_body = re.sub(r'^- (.+)$', r'<li>\1</li>', html_body, flags=re.MULTILINE)
    # Paragraphs
    html_body = re.sub(r'\n\n', '</p><p>', html_body)

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{report.title}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         max-width: 800px; margin: 40px auto; padding: 0 20px; color: #1e293b; line-height: 1.6; }}
  h1 {{ color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }}
  h2 {{ color: #334155; margin-top: 2em; }}
  h3 {{ color: #475569; }}
  code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }}
  pre {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; overflow-x: auto; }}
  pre code {{ background: none; padding: 0; }}
  li {{ margin: 4px 0; }}
  strong {{ color: #0f172a; }}
  .meta {{ color: #94a3b8; font-size: 0.85em; margin-bottom: 2em; }}
</style>
</head>
<body>
<div class="meta">Campaign: {campaign_name} · Model: {report.model_used} · {report.created_at.strftime('%Y-%m-%d %H:%M')}</div>
<p>{html_body}</p>
</body>
</html>"""

    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": f"attachment; filename=report_{report_id}.html"},
    )
