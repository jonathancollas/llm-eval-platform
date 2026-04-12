"""
Campaigns — CRUD + run/cancel + live tracking.
"""
import hashlib
import json
import platform
import sys

from datetime import datetime
from typing import Literal, Optional
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
    visibility: Literal["private", "shared", "public"] = "private"
    collaborator_tenant_ids: list[int] = Field(default_factory=list)
    review_state: str = "open"
    comment_count: int = 0
    runs: list[dict] = Field(default_factory=list)


class CampaignShareUpdate(BaseModel):
    visibility: Literal["private", "shared", "public"] = "private"
    collaborator_tenant_ids: list[int] = Field(default_factory=list, max_length=100)


class CampaignCommentCreate(BaseModel):
    author: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=4000)


class CampaignReviewCreate(BaseModel):
    reviewer: str = Field(..., min_length=1, max_length=200)
    decision: Literal["approve", "request_changes", "comment"]
    summary: str = Field(default="", max_length=4000)


class CampaignBundleImport(BaseModel):
    bundle: dict
    import_collaboration: bool = False


def _campaign_context(campaign: Campaign) -> dict:
    if not campaign.run_context_json:
        return {}
    try:
        parsed = json.loads(campaign.run_context_json)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _campaign_collaboration(campaign: Campaign) -> dict:
    context = _campaign_context(campaign)
    collab = context.get("collaboration", {})
    if not isinstance(collab, dict):
        collab = {}
    return {
        "visibility": collab.get("visibility", "private"),
        "collaborator_tenant_ids": [int(tid) for tid in collab.get("collaborator_tenant_ids", []) if isinstance(tid, int)],
        "comments": collab.get("comments", []),
        "reviews": collab.get("reviews", []),
        "review_state": collab.get("review_state", "open"),
    }


def _save_campaign_collaboration(campaign: Campaign, collaboration: dict) -> None:
    context = _campaign_context(campaign)
    context["collaboration"] = collaboration
    campaign.run_context_json = json.dumps(context)


def _can_access_campaign(campaign: Campaign, tenant: Tenant) -> bool:
    if campaign.tenant_id == tenant.id:
        return True
    collab = _campaign_collaboration(campaign)
    if collab["visibility"] == "public":
        return True
    if collab["visibility"] == "shared" and tenant.id in collab["collaborator_tenant_ids"]:
        return True
    return False


def _to_read(session: Session, c: Campaign, runs: list[EvalRun] | None = None) -> CampaignRead:
    collab = _campaign_collaboration(c)
    comments = collab.get("comments", [])
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
        visibility=collab.get("visibility", "private"),
        collaborator_tenant_ids=collab.get("collaborator_tenant_ids", []),
        review_state=collab.get("review_state", "open"),
        comment_count=len(comments) if isinstance(comments, list) else 0,
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
    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, detail="Campaign not found.")
    if not _can_access_campaign(campaign, tenant):
        raise HTTPException(404, detail="Campaign not found.")
    runs = session.exec(select(EvalRun).where(EvalRun.campaign_id == campaign_id)).all()
    return _to_read(session, campaign, list(runs))


@router.get("/shared/available", response_model=list[CampaignRead])
def list_shared_campaigns(
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
):
    campaigns = session.exec(select(Campaign).order_by(Campaign.created_at.desc())).all()
    shared = [c for c in campaigns if c.tenant_id != tenant.id and _can_access_campaign(c, tenant)]
    return [_to_read(session, c) for c in shared]


@router.post("/{campaign_id}/share", response_model=CampaignRead)
def share_campaign(
    campaign_id: int,
    payload: CampaignShareUpdate,
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
):
    campaign = session.exec(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant.id)
    ).first()
    if not campaign:
        raise HTTPException(404, detail="Campaign not found.")
    collaborator_ids = sorted({tid for tid in payload.collaborator_tenant_ids if tid != tenant.id})
    collab = _campaign_collaboration(campaign)
    collab["visibility"] = payload.visibility
    collab["collaborator_tenant_ids"] = collaborator_ids
    collab.setdefault("comments", [])
    collab.setdefault("reviews", [])
    collab.setdefault("review_state", "open")
    _save_campaign_collaboration(campaign, collab)
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return _to_read(session, campaign)


@router.get("/{campaign_id}/comments")
def list_campaign_comments(
    campaign_id: int,
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
):
    campaign = session.get(Campaign, campaign_id)
    if not campaign or not _can_access_campaign(campaign, tenant):
        raise HTTPException(404, detail="Campaign not found.")
    collab = _campaign_collaboration(campaign)
    return {
        "campaign_id": campaign_id,
        "comments": collab.get("comments", []),
        "reviews": collab.get("reviews", []),
        "review_state": collab.get("review_state", "open"),
    }


@router.post("/{campaign_id}/comments")
def create_campaign_comment(
    campaign_id: int,
    payload: CampaignCommentCreate,
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
):
    campaign = session.get(Campaign, campaign_id)
    if not campaign or not _can_access_campaign(campaign, tenant):
        raise HTTPException(404, detail="Campaign not found.")
    collab = _campaign_collaboration(campaign)
    comments = collab.get("comments", [])
    comment = {
        "id": len(comments) + 1,
        "tenant_id": tenant.id,
        "author": payload.author,
        "message": payload.message,
        "created_at": datetime.utcnow().isoformat(),
    }
    comments.append(comment)
    collab["comments"] = comments
    _save_campaign_collaboration(campaign, collab)
    session.add(campaign)
    session.commit()
    return {"created": True, "comment": comment}


@router.post("/{campaign_id}/reviews")
def submit_campaign_review(
    campaign_id: int,
    payload: CampaignReviewCreate,
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
):
    campaign = session.get(Campaign, campaign_id)
    if not campaign or not _can_access_campaign(campaign, tenant):
        raise HTTPException(404, detail="Campaign not found.")
    collab = _campaign_collaboration(campaign)
    reviews = collab.get("reviews", [])
    review = {
        "id": len(reviews) + 1,
        "tenant_id": tenant.id,
        "reviewer": payload.reviewer,
        "decision": payload.decision,
        "summary": payload.summary,
        "created_at": datetime.utcnow().isoformat(),
    }
    reviews.append(review)
    collab["reviews"] = reviews
    collab["review_state"] = "approved" if payload.decision == "approve" else (
        "changes_requested" if payload.decision == "request_changes" else "in_review"
    )
    _save_campaign_collaboration(campaign, collab)
    session.add(campaign)
    session.commit()
    return {"submitted": True, "review": review, "review_state": collab["review_state"]}


@router.get("/{campaign_id}/bundle/export")
def export_campaign_bundle(
    campaign_id: int,
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
):
    campaign = session.get(Campaign, campaign_id)
    if not campaign or not _can_access_campaign(campaign, tenant):
        raise HTTPException(404, detail="Campaign not found.")
    model_ids = get_campaign_model_ids(session, campaign)
    benchmark_ids = get_campaign_benchmark_ids(session, campaign)
    models = [session.get(LLMModel, mid) for mid in model_ids]
    benchmarks = [session.get(Benchmark, bid) for bid in benchmark_ids]
    collab = _campaign_collaboration(campaign)
    return {
        "bundle_version": "1.0",
        "exported_at": datetime.utcnow().isoformat(),
        "campaign": {
            "name": campaign.name,
            "description": campaign.description,
            "seed": campaign.seed,
            "max_samples": campaign.max_samples,
            "temperature": campaign.temperature,
            "dataset_version": campaign.dataset_version,
            "collaboration": collab,
        },
        "models": [
            {"model_id": m.model_id, "name": m.name, "provider": m.provider}
            for m in models if m
        ],
        "benchmarks": [
            {"name": b.name, "type": b.type, "metric": b.metric, "source": getattr(b, "source", "public")}
            for b in benchmarks if b
        ],
    }


@router.post("/bundle/import", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
def import_campaign_bundle(
    payload: CampaignBundleImport,
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
):
    bundle = payload.bundle
    campaign_data = bundle.get("campaign") if isinstance(bundle, dict) else None
    if not isinstance(campaign_data, dict):
        raise HTTPException(422, detail="Invalid bundle format.")

    model_entries = bundle.get("models", [])
    benchmark_entries = bundle.get("benchmarks", [])

    model_ids: list[int] = []
    missing_models: list[str] = []
    for entry in model_entries:
        model_identifier = entry.get("model_id") if isinstance(entry, dict) else None
        if not model_identifier:
            continue
        model = session.exec(select(LLMModel).where(LLMModel.model_id == model_identifier)).first()
        if model:
            model_ids.append(model.id)
        else:
            missing_models.append(model_identifier)

    benchmark_ids: list[int] = []
    missing_benchmarks: list[str] = []
    for entry in benchmark_entries:
        benchmark_name = entry.get("name") if isinstance(entry, dict) else None
        if not benchmark_name:
            continue
        benchmark = session.exec(select(Benchmark).where(Benchmark.name == benchmark_name)).first()
        if benchmark:
            benchmark_ids.append(benchmark.id)
        else:
            missing_benchmarks.append(benchmark_name)

    if missing_models or missing_benchmarks:
        raise HTTPException(
            404,
            detail={
                "missing_models": missing_models,
                "missing_benchmarks": missing_benchmarks,
            },
        )
    if not model_ids or not benchmark_ids:
        raise HTTPException(422, detail="Bundle must include at least one model and benchmark.")

    model_ids = list(dict.fromkeys(model_ids))
    benchmark_ids = list(dict.fromkeys(benchmark_ids))
    campaign = Campaign(
        tenant_id=tenant.id,
        name=campaign_data.get("name") or "Imported campaign",
        description=campaign_data.get("description", ""),
        model_ids=json.dumps(model_ids),
        benchmark_ids=json.dumps(benchmark_ids),
        seed=int(campaign_data.get("seed", 42)),
        max_samples=campaign_data.get("max_samples"),
        temperature=float(campaign_data.get("temperature", 0.0)),
        dataset_version=campaign_data.get("dataset_version"),
        status=JobStatus.PENDING,
    )
    if payload.import_collaboration:
        collab = campaign_data.get("collaboration", {})
        if isinstance(collab, dict):
            collab["collaborator_tenant_ids"] = [
                tid for tid in collab.get("collaborator_tenant_ids", []) if isinstance(tid, int)
            ]
            _save_campaign_collaboration(campaign, collab)
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    replace_campaign_links(session, campaign.id, model_ids, benchmark_ids)
    session.commit()
    return _to_read(session, campaign)


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

    try:
        job_queue.submit_campaign(campaign_id)
    except Exception as e:
        campaign.status = JobStatus.FAILED
        campaign.error_message = f"queue_enqueue_failed: {str(e)[:MAX_QUEUE_ERROR_MESSAGE_LENGTH]}"
        campaign.completed_at = _dt.utcnow()
        session.add(campaign)
        session.commit()
        session.refresh(campaign)
        raise HTTPException(500, detail="Failed to enqueue campaign job.") from e

    _logger.info(f"Campaign {campaign_id} submitted — status set to RUNNING immediately")

    return _to_read(session, campaign)


@router.post("/{campaign_id}/cancel", response_model=CampaignRead)
def cancel_campaign(
    campaign_id: int,
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
):
    campaign = session.exec(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant.id)
    ).first()
    if not campaign:
        raise HTTPException(404, detail="Campaign not found.")

    cancelled = job_queue.cancel_campaign(campaign_id)

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
