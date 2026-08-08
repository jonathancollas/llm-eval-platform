import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from sqlmodel import Session

from core.auth import require_tenant
from core.database import get_session
from core.models import Campaign, EvalRun, Tenant
from eval_engine.plugin_sdk import plugin_registry
from eval_engine.research_export import (
    ExportConfig,
    export_json_ld,
    export_csv,
    export_latex_table,
    export_bibtex,
    export_helm,
    export_eval_card,
)

router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.get("/")
def list_all_plugins(plugin_type: Optional[str] = None):
    plugins = plugin_registry.list_plugins(plugin_type)
    return [{"name": p.manifest_name, "type": p.plugin_type} for p in plugins]


@router.get("/{plugin_type}")
def list_plugins_by_type(plugin_type: str):
    plugins = plugin_registry.list_plugins(plugin_type)
    return [{"name": p.manifest_name, "type": p.plugin_type} for p in plugins]


class ManifestValidationRequest(BaseModel):
    name: str = ""
    version: str = "1.0.0"
    author: str = ""
    description: str = ""


@router.post("/validate")
def validate_manifest(req: ManifestValidationRequest):
    errors = []
    if not req.name:
        errors.append("name is required")
    if not req.version:
        errors.append("version is required")
    return {"valid": len(errors) == 0, "errors": errors}


def _can_access_campaign(campaign: Campaign, tenant: Tenant) -> bool:
    """Mirror campaigns._can_access_campaign without importing that router."""
    if campaign.tenant_id == tenant.id:
        return True
    try:
        context = json.loads(campaign.run_context_json or "{}")
    except json.JSONDecodeError:
        context = {}
    collab = context.get("collaboration") or {}
    visibility = collab.get("visibility", "private")
    if visibility == "public":
        return True
    if visibility == "shared" and tenant.id in (collab.get("collaborator_tenant_ids") or []):
        return True
    return False


def _get_accessible_run(session: Session, run_id: int, tenant: Tenant) -> EvalRun:
    """Load an EvalRun only if its campaign is accessible to the tenant."""
    run = session.get(EvalRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    campaign = session.get(Campaign, run.campaign_id)
    if not campaign or not _can_access_campaign(campaign, tenant):
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/export/{run_id}")
def export_run(
    run_id: int,
    format: str = Query("json_ld"),
    tenant: Tenant = Depends(require_tenant),
    session: Session = Depends(get_session),
):
    run = _get_accessible_run(session, run_id, tenant)
    config = ExportConfig()
    # EvalRun has started_at/completed_at, not created_at (legacy export key).
    stamp = run.completed_at or run.started_at
    run_data = {
        "run_id": run_id,
        "model_name": str(run.model_id),
        "benchmark_name": str(run.benchmark_id),
        "score": run.score or 0.0,
        "n_items": run.num_items or 0,
        "created_at": str(stamp) if stamp is not None else config.date,
    }
    if format == "json_ld":
        return {"export": export_json_ld(run_data, config)}
    if format == "csv":
        return {"export": export_csv([run_data], config)}
    if format == "latex":
        return {"export": export_latex_table([run_data], config)}
    if format == "bibtex":
        benchmarks = [
            {
                "name": run_data["benchmark_name"],
                "title": run_data["benchmark_name"],
                "authors": "",
                "year": config.date[:4],
                "url": "",
            }
        ]
        return {"export": export_bibtex(benchmarks)}
    if format == "helm":
        return {"export": export_helm(run_data, config)}
    if format == "eval_card":
        return {"export": export_eval_card(run_data, {}, config)}
    raise HTTPException(400, f"Unknown format: {format}")


@router.get("/versions/{benchmark_name}")
def benchmark_versions(benchmark_name: str):
    return []
