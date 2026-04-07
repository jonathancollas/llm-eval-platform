from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import json

from core.utils import safe_json_load
from core.database import get_session
from core.models import Campaign, EvalRun, LLMModel, Benchmark, JobStatus
from core import job_queue

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CampaignCreate(BaseModel):
    name: str
    description: str = ""
    model_ids: list[int]
    benchmark_ids: list[int]
    seed: int = 42
    max_samples: Optional[int] = None
    temperature: float = 0.0


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


def _to_read(c: Campaign, runs: list[EvalRun] | None = None) -> CampaignRead:
    return CampaignRead(
        id=c.id,
        name=c.name,
        description=c.description,
        model_ids=safe_json_load(c.model_ids, []),
        benchmark_ids=safe_json_load(c.benchmark_ids, []),
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
                "metrics": safe_json_load(r.metrics_json, {}),
                "total_cost_usd": r.total_cost_usd,
                "total_latency_ms": r.total_latency_ms,
                "num_items": r.num_items,
                "error_message": r.error_message,
            }
            for r in (runs or [])
        ],
    )


@router.get("/", response_model=list[CampaignRead])
def list_campaigns(session: Session = Depends(get_session)):
    campaigns = session.exec(select(Campaign).order_by(Campaign.created_at.desc())).all()
    return [_to_read(c) for c in campaigns]


@router.post("/", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
def create_campaign(payload: CampaignCreate, session: Session = Depends(get_session)):
    for mid in payload.model_ids:
        if not session.get(LLMModel, mid):
            raise HTTPException(404, detail=f"Model {mid} not found.")
    for bid in payload.benchmark_ids:
        if not session.get(Benchmark, bid):
            raise HTTPException(404, detail=f"Benchmark {bid} not found.")

    campaign = Campaign(
        name=payload.name,
        description=payload.description,
        model_ids=json.dumps(payload.model_ids),
        benchmark_ids=json.dumps(payload.benchmark_ids),
        seed=payload.seed,
        max_samples=payload.max_samples,
        temperature=payload.temperature,
        status=JobStatus.PENDING,
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return _to_read(campaign)


@router.get("/{campaign_id}", response_model=CampaignRead)
def get_campaign(campaign_id: int, session: Session = Depends(get_session)):
    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, detail="Campaign not found.")
    runs = session.exec(select(EvalRun).where(EvalRun.campaign_id == campaign_id)).all()
    return _to_read(campaign, list(runs))


@router.post("/{campaign_id}/run", response_model=CampaignRead)
async def run_campaign(campaign_id: int, session: Session = Depends(get_session)):
    """Start or re-run a campaign."""
    campaign = session.get(Campaign, campaign_id)
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

    import logging
    from datetime import datetime as _dt
    _logger = logging.getLogger(__name__)

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
    job_queue.submit_campaign(campaign_id, execute_campaign(campaign_id))
    _logger.info(f"Campaign {campaign_id} submitted — status set to RUNNING immediately")

    return _to_read(campaign)


@router.post("/{campaign_id}/cancel", response_model=CampaignRead)
def cancel_campaign(campaign_id: int, session: Session = Depends(get_session)):
    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, detail="Campaign not found.")

    cancelled = job_queue.cancel_campaign(campaign_id)

    if not cancelled:
        # Task not in queue — force status update if DB still shows running
        if campaign.status == JobStatus.RUNNING:
            campaign.status = JobStatus.CANCELLED
            campaign.error_message = "Cancelled by user."
            campaign.completed_at = datetime.utcnow()
            session.add(campaign)
            session.commit()
        else:
            raise HTTPException(400, detail=f"Campaign is not running (status: {campaign.status}).")

    session.refresh(campaign)
    return _to_read(campaign)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(campaign_id: int, session: Session = Depends(get_session)):
    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, detail="Campaign not found.")
    if campaign.status == JobStatus.RUNNING:
        raise HTTPException(409, detail="Stop the campaign before deleting.")
    # Cascade delete runs
    for r in session.exec(select(EvalRun).where(EvalRun.campaign_id == campaign_id)).all():
        session.delete(r)
    session.delete(campaign)
    session.commit()
