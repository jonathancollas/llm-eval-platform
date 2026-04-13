"""
Campaigns — CRUD + run/cancel + live tracking.
"""
import hashlib
import json
import platform
import sys

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from core.database import get_session
from core.models import Benchmark, Campaign, EvalRun, JobStatus, LLMModel, Tenant
from core.relations import get_campaign_benchmark_ids, get_campaign_model_ids, get_eval_run_metrics, replace_campaign_links
from core.auth import require_tenant
from core import job_queue

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
# Keep queue error details bounded for DB/UI readability.
MAX_QUEUE_ERROR_MESSAGE_LENGTH = 300


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    model_ids: list[int] = Field(..., min_length=1, max_length=50)
    benchmark_ids: list[int] = Field(..., min_length=1, max_length=50)
    seed: int = Field(default=42, ge=0, le=999999)
    max_samples: Optional[int] = Field(default=None, ge=1, le=10000)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class CampaignRead(BaseModel):
    id: int
    name: str
    description: str
    model_ids: list[int]
    benchmark_ids: list[int]
    seed: int
    max_samples: Optional[int]
    temperature: float
    status: JobStatus
    progress: float
    error_message: Optional[str]
    current_item_index: Optional[int] = None
    current_item_total: Optional[int] = None
    current_item_label: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    runs: list[dict] = Field(default_factory=list)


def _to_read(session: Session, c: Campaign, runs: list[EvalRun] | None = None) -> CampaignRead:
    return CampaignRead(
        id=c.id,
        name=c.name,
        description=c.description,
        model_ids=get_campaign_model_ids(session, c),
        benchmark_ids=get_campaign_benchmark_ids(session, c),
        seed=c.seed,
        max_samples=c.max_samples,
        temperature=c.temperature,
        status=c.status,
        progress=c.progress,
        error_message=c.error_message,
        current_item_index=c.current_item_index,
        current_item_total=c.current_item_total,
        current_item_label=c.current_item_label,
        created_at=c.created_at,
        started_at=c.started_at,
        completed_at=c.completed_at,
        runs=[
            {
                "id": r.id,
                "model_id": r.model_id,
                "benchmark_id": r.benchmark_id,
                "status": r.status,
                "score": r.score,
                "capability_score": r.capability_score,
                "propensity_score": r.propensity_score,
                "metrics": get_eval_run_metrics(session, r),
                "total_cost_usd": r.total_cost_usd,
                "total_latency_ms": r.total_latency_ms,
                "num_items": r.num_items,
                "error_message": r.error_message,
            }
            for r in (runs or [])
        ],
    )


@router.get("/", response_model=list[CampaignRead])
def list_campaigns(
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
):
    campaigns = session.exec(
        select(Campaign)
        .where(Campaign.tenant_id == tenant.id)
        .order_by(Campaign.created_at.desc())
    ).all()
    return [_to_read(session, c) for c in campaigns]

@router.post("/", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreate,
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
):
    for mid in payload.model_ids:
        if not session.get(LLMModel, mid):
            raise HTTPException(404, detail=f"Model {mid} not found.")
    for bid in payload.benchmark_ids:
        if not session.get(Benchmark, bid):
            raise HTTPException(404, detail=f"Benchmark {bid} not found.")

    model_ids = list(dict.fromkeys(payload.model_ids))
    benchmark_ids = list(dict.fromkeys(payload.benchmark_ids))

    campaign = Campaign(
        tenant_id=tenant.id,
        name=payload.name,
        description=payload.description,
        model_ids=json.dumps(model_ids),
        benchmark_ids=json.dumps(benchmark_ids),
        seed=payload.seed,
        max_samples=payload.max_samples,
        temperature=payload.temperature,
        status=JobStatus.PENDING,
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    replace_campaign_links(session, campaign.id, model_ids, benchmark_ids)
    session.commit()
    return _to_read(session, campaign)


@router.get("/{campaign_id}", response_model=CampaignRead)
def get_campaign(
    campaign_id: int,
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
):
    campaign = session.exec(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant.id)
    ).first()
    if not campaign:
        raise HTTPException(404, detail="Campaign not found.")
    runs = session.exec(select(EvalRun).where(EvalRun.campaign_id == campaign_id)).all()
    return _to_read(session, campaign, list(runs))


@router.post("/{campaign_id}/run", response_model=CampaignRead)
async def run_campaign(
    campaign_id: int,
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
):
    """Start or re-run a campaign."""
    import logging
    from datetime import datetime as _dt
    _logger = logging.getLogger(__name__)

    campaign = session.exec(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant.id)
    ).first()
    if not campaign:
        raise HTTPException(404, detail="Campaign not found.")
    if campaign.status == JobStatus.RUNNING:
        raise HTTPException(409, detail="Campaign is already running.")

    # Reset state for re-run (completed or failed campaigns)
    if campaign.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        # Delete previous runs to allow fresh start
        prev_runs = session.exec(
            select(EvalRun).where(EvalRun.campaign_id == campaign_id)
        ).all()
        for r in prev_runs:
            session.delete(r)
        campaign.status = JobStatus.PENDING
        campaign.progress = 0.0
        campaign.error_message = None
        campaign.started_at = None
        campaign.completed_at = None
        session.add(campaign)
        session.commit()
        session.refresh(campaign)

    # Set RUNNING immediately — before submitting the task
    # This prevents the "pending forever" appearance in the UI
    campaign.status = JobStatus.RUNNING
    campaign.started_at = _dt.utcnow()
    campaign.progress = 0.0
    campaign.error_message = None
    session.add(campaign)
    session.commit()
    session.refresh(campaign)

    from eval_engine.runner import execute_campaign
    try:
        job_queue.submit_campaign(campaign_id, execute_campaign(campaign_id))
    except Exception as e:
        campaign.status = JobStatus.FAILED
        campaign.error_message = f"queue_enqueue_failed: {str(e)[:MAX_QUEUE_ERROR_MESSAGE_LENGTH]}"
        campaign.completed_at = _dt.utcnow()
        session.add(campaign)
        session.commit()
        session.refresh(campaign)
        raise HTTPException(500, detail="Failed to enqueue campaign job.") from e

    _logger.info(f"Campaign {campaign_id} submitted to Celery task={task_id} — status set to RUNNING immediately")

    return _to_read(session, campaign)


@router.post("/{campaign_id}/cancel", response_model=CampaignRead)
async def cancel_campaign(
    campaign_id: int,
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
):
    campaign = session.exec(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant.id)
    ).first()
    if not campaign:
        raise HTTPException(404, detail="Campaign not found.")

    cancelled = await job_queue.cancel(campaign_id)

    if cancelled:
        # Task was actively running in this process and has now been cancelled.
        campaign.status = JobStatus.CANCELLED
        campaign.error_message = "Cancelled by user."
        campaign.completed_at = datetime.utcnow()
        session.add(campaign)
        session.commit()
    else:
        # Task was not found in the in-memory queue — force status update
        # only when DB still shows RUNNING.
        if campaign.status == JobStatus.RUNNING:
            campaign.status = JobStatus.CANCELLED
            campaign.error_message = "Cancelled by user."
            campaign.completed_at = datetime.utcnow()
            session.add(campaign)
            session.commit()
        else:
            raise HTTPException(400, detail=f"Campaign is not running (status: {campaign.status}).")

    session.refresh(campaign)
    return _to_read(session, campaign)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(
    campaign_id: int,
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
):
    campaign = session.exec(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant.id)
    ).first()
    if not campaign:
        raise HTTPException(404, detail="Campaign not found.")
    if campaign.status == JobStatus.RUNNING:
        raise HTTPException(409, detail="Stop the campaign before deleting.")
    # Cascade delete runs
    for r in session.exec(select(EvalRun).where(EvalRun.campaign_id == campaign_id)).all():
        session.delete(r)
    session.delete(campaign)
    session.commit()


@router.get("/{campaign_id}/manifest")
def get_reproducibility_manifest(
    campaign_id: int,
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
):
    """
    Reproducibility manifest — everything needed to replay this experiment exactly.
    Returns a JSON object capturing the full configuration snapshot at run time.
    Aligned with INESIA research doctrine: every evaluation must be reproducible.
    """
    campaign = session.exec(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant.id)
    ).first()
    if not campaign:
        raise HTTPException(404, detail="Campaign not found.")

    runs = session.exec(select(EvalRun).where(EvalRun.campaign_id == campaign_id)).all()

    model_ids = get_campaign_model_ids(session, campaign)
    bench_ids = get_campaign_benchmark_ids(session, campaign)

    models = [session.get(LLMModel, mid) for mid in model_ids]
    benches = [session.get(Benchmark, bid) for bid in bench_ids]

    model_configs = [
        {"model_id": m.id, "model_name": m.name, "provider": m.provider,
         "model_identifier": m.model_id, "endpoint": m.endpoint}
        for m in models if m
    ]
    bench_configs = [
        {"benchmark_id": b.id, "benchmark_name": b.name,
         "metric": b.metric, "num_samples": b.num_samples,
         "dataset_path": b.dataset_path, "source": getattr(b, "source", "public")}
        for b in benches if b
    ]

    # Deterministic hash of the full configuration
    config_str = json.dumps({
        "campaign_id": campaign_id,
        "seed": campaign.seed,
        "temperature": campaign.temperature,
        "model_configs": model_configs,
        "bench_configs": bench_configs,
    }, sort_keys=True)
    experiment_hash = hashlib.sha256(config_str.encode()).hexdigest()[:16]

    # Results summary
    completed_runs = [r for r in runs if r.status == "completed"]
    scores = [r.score for r in completed_runs if r.score is not None]
    cap_scores = [r.capability_score for r in completed_runs if r.capability_score is not None]
    prop_scores = [r.propensity_score for r in completed_runs if r.propensity_score is not None]

    return {
        "experiment_hash": experiment_hash,
        "campaign_id": campaign_id,
        "campaign_name": campaign.name,
        "platform_version": "eval-research-os-v0.6.0",
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "execution": {
            "seed": campaign.seed,
            "temperature": campaign.temperature,
            "max_samples": campaign.max_samples,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
            "completed_at": campaign.completed_at.isoformat() if campaign.completed_at else None,
        },
        "model_configs": model_configs,
        "benchmark_configs": bench_configs,
        "results_summary": {
            "total_runs": len(runs),
            "completed_runs": len(completed_runs),
            "avg_score": round(sum(scores) / len(scores), 4) if scores else None,
            "avg_capability_score": round(sum(cap_scores) / len(cap_scores), 4) if cap_scores else None,
            "avg_propensity_score": round(sum(prop_scores) / len(prop_scores), 4) if prop_scores else None,
        },
        "reproducibility_instructions": (
            "To replay this experiment: use the same seed, temperature, model_configs, and benchmark_configs. "
            "Run via POST /campaigns/ with these parameters, then POST /campaigns/{id}/run. "
            "Results may vary if model providers update their models."
        ),
    }
