from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from sqlmodel import Session
from core.database import get_session
from core.models import EvalRun
from eval_engine.plugin_sdk import plugin_registry
from eval_engine.plugin_sdk.validator import validate_benchmark_plugin
from eval_engine.research_export import ExportConfig, export_json_ld, export_csv, export_latex_table, export_bibtex, export_helm, export_eval_card

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
    name: str = ""; version: str = "1.0.0"; author: str = ""; description: str = ""

@router.post("/validate")
def validate_manifest(req: ManifestValidationRequest):
    errors = []
    if not req.name: errors.append("name is required")
    if not req.version: errors.append("version is required")
    return {"valid": len(errors)==0, "errors": errors}

@router.post("/export/{run_id}")
def export_run(run_id: int, format: str = Query("json_ld"), session: Session = Depends(get_session)):
    run = session.get(EvalRun, run_id)
    if not run: raise HTTPException(404, "Run not found")
    config = ExportConfig()
    run_data = {"run_id": run_id, "model_name": str(run.model_id), "benchmark_name": str(run.benchmark_id),
                "score": run.score or 0.0, "n_items": 0, "created_at": str(run.created_at)}
    if format == "json_ld": return {"export": export_json_ld(run_data, config)}
    if format == "csv": return {"export": export_csv([run_data], config)}
    if format == "latex": return {"export": export_latex_table([run_data], config)}
    if format == "bibtex":
        benchmarks = [{"name": run_data["benchmark_name"], "title": run_data["benchmark_name"],
                       "authors": "", "year": config.date[:4], "url": ""}]
        return {"export": export_bibtex(benchmarks)}
    if format == "helm": return {"export": export_helm(run_data, config)}
    if format == "eval_card": return {"export": export_eval_card(run_data, {}, config)}
    raise HTTPException(400, f"Unknown format: {format}")

@router.get("/versions/{benchmark_name}")
def benchmark_versions(benchmark_name: str):
    return []
