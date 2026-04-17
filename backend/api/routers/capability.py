from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from sqlmodel import Session, select
from core.database import get_session
from core.models import LLMModel, EvalRun
from eval_engine.capability_taxonomy import CAPABILITY_ONTOLOGY, CapabilityTaxonomyEngine, CapabilityScore
from eval_engine.trajectory_analysis import TrajectoryAnalysisEngine
from eval_engine.cross_benchmark import CrossBenchmarkAnalyzer

router = APIRouter(prefix="/capability", tags=["capability"])
_taxonomy = CapabilityTaxonomyEngine()
_traj = TrajectoryAnalysisEngine()
_cross = CrossBenchmarkAnalyzer()

@router.get("/taxonomy")
def get_taxonomy(): return CAPABILITY_ONTOLOGY

@router.get("/taxonomy/{domain}")
def get_domain_taxonomy(domain: str):
    if domain not in CAPABILITY_ONTOLOGY: raise HTTPException(404, f"Domain '{domain}' not found")
    return CAPABILITY_ONTOLOGY[domain]

@router.get("/profile/{model_id}")
def get_model_profile(model_id: int, session: Session = Depends(get_session)):
    model = session.get(LLMModel, model_id)
    if not model: raise HTTPException(404, "Model not found")
    runs = session.exec(select(EvalRun).where(EvalRun.model_id == model_id)).all()
    scores = []
    for run in runs:
        if run.score is not None:
            inferred = _taxonomy.infer_capabilities_from_benchmark(str(run.benchmark_id))
            for domain, cap, sub_cap in (inferred or [("reasoning","reasoning","logical")]):
                scores.append(CapabilityScore(model_name=model.name, domain=domain, capability=cap,
                    sub_capability=sub_cap, score=run.score, run_id=run.id))
    profile = _taxonomy.compute_profile(model.name, scores)
    return profile.__dict__

@router.get("/gaps/{model_id}")
def get_capability_gaps(model_id: int, session: Session = Depends(get_session)):
    model = session.get(LLMModel, model_id)
    if not model: raise HTTPException(404, "Model not found")
    runs = session.exec(select(EvalRun).where(EvalRun.model_id == model_id)).all()
    scores = []
    for run in runs:
        if run.score is not None:
            inferred = _taxonomy.infer_capabilities_from_benchmark(str(run.benchmark_id))
            for domain, cap, sub_cap in (inferred or []):
                scores.append(CapabilityScore(model_name=model.name, domain=domain, capability=cap,
                    sub_capability=sub_cap, score=run.score, run_id=run.id))
    gaps = _taxonomy.find_coverage_gaps(model.name, scores)
    return [{"domain": g.domain, "sub_capability": g.sub_capability, "risk_level": g.risk_level} for g in gaps]

class TrajectoryRequest(BaseModel):
    steps: List[dict]

@router.post("/trajectory/analyze")
def analyze_trajectory(req: TrajectoryRequest):
    result = _traj.analyze_steps(req.steps)
    return {
        "steps_analyzed": result.steps_analyzed,
        "loop_detected": result.loop_detection.detected,
        "autonomy_score": result.autonomy_score,
        "adaptivity_score": result.adaptivity_score,
        "efficiency_score": result.efficiency_score,
        "overall_quality_score": result.overall_quality_score,
        "failure_types": result.failure_types,
        "recommendations": result.recommendations,
    }

@router.get("/cross-benchmark/{model_id}")
def cross_benchmark(model_id: int, session: Session = Depends(get_session)):
    model = session.get(LLMModel, model_id)
    if not model: raise HTTPException(404, "Model not found")
    runs = session.exec(select(EvalRun).where(EvalRun.model_id == model_id)).all()
    run_dicts = [{"model_name": model.name, "benchmark_name": str(r.benchmark_id), "score": r.score or 0.0} for r in runs if r.score is not None]
    if not run_dicts: return {"model_name": model.name, "generalization_index": 0.5, "benchmarks": []}
    report = _cross.generate_report(model.name, run_dicts)
    return {"model_name": report.model_name, "generalization_index": report.generalization_index,
            "mean_score": report.mean_score, "benchmarks": report.benchmarks_evaluated, "scores": report.scores}
