from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
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


# ── Schemas ────────────────────────────────────────────────────────────────────

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
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    runs: list[dict] = Field(default_factory=list)  # EvalRun summaries


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
            }
            for r in (runs or [])
        ],
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[CampaignRead])
def list_campaigns(session: Session = Depends(get_session)):
    campaigns = session.exec(select(Campaign).order_by(Campaign.created_at.desc())).all()
    return [_to_read(c) for c in campaigns]


@router.post("/", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
def create_campaign(payload: CampaignCreate, session: Session = Depends(get_session)):
    # Validate model and benchmark IDs exist
    for mid in payload.model_ids:
        if not session.get(LLMModel, mid):
            raise HTTPException(status_code=404, detail=f"Model {mid} not found.")
    for bid in payload.benchmark_ids:
        if not session.get(Benchmark, bid):
            raise HTTPException(status_code=404, detail=f"Benchmark {bid} not found.")

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
        raise HTTPException(status_code=404, detail="Campaign not found.")
    runs = session.exec(select(EvalRun).where(EvalRun.campaign_id == campaign_id)).all()
    return _to_read(campaign, list(runs))


@router.post("/{campaign_id}/run", response_model=CampaignRead)
async def run_campaign(campaign_id: int, session: Session = Depends(get_session)):
    """Start executing a campaign as a background task."""
    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    if campaign.status == JobStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Campaign is already running.")
    if campaign.status == JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Campaign already completed. Create a new one to re-run.")

    from eval_engine.runner import execute_campaign
    job_queue.submit_campaign(campaign_id, execute_campaign(campaign_id))

    # Brief delay so the status update is visible
    import asyncio
    await asyncio.sleep(0.1)
    session.refresh(campaign)
    return _to_read(campaign)


@router.post("/{campaign_id}/cancel", response_model=CampaignRead)
def cancel_campaign(campaign_id: int, session: Session = Depends(get_session)):
    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    cancelled = job_queue.cancel_campaign(campaign_id)
    if not cancelled:
        raise HTTPException(status_code=400, detail="Campaign is not running.")
    session.refresh(campaign)
    return _to_read(campaign)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(campaign_id: int, session: Session = Depends(get_session)):
    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    if campaign.status == JobStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Stop the campaign before deleting.")
    session.delete(campaign)
    session.commit()
