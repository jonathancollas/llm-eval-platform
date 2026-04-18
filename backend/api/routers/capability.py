from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from sqlmodel import Session, select
from core.database import get_session
from core.models import (
    LLMModel,
    EvalRun,
    Benchmark,
    CapabilityDomainRecord,
    CapabilitySubCapabilityRecord,
    BenchmarkCapabilityMapping,
    CapabilityEvalScore,
)
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


# ── M3: DB-backed capability endpoints ────────────────────────────────────────

@router.get("/domains")
def list_domains(session: Session = Depends(get_session)):
    """Return all capability domains from the relational taxonomy."""
    domains = session.exec(
        select(CapabilityDomainRecord).order_by(CapabilityDomainRecord.sort_order)
    ).all()
    if not domains:
        # Fallback to in-memory ontology if taxonomy has not been seeded yet
        return [
            {"slug": slug, "display_name": slug.replace("_", " ").title(),
             "description": data.get("description", "")}
            for slug, data in CAPABILITY_ONTOLOGY.items()
        ]
    return [
        {"id": d.id, "slug": d.slug, "display_name": d.display_name, "description": d.description}
        for d in domains
    ]


@router.get("/sub-capabilities")
def list_sub_capabilities(domain: Optional[str] = None, session: Session = Depends(get_session)):
    """Return sub-capabilities, optionally filtered by domain slug."""
    stmt = select(CapabilitySubCapabilityRecord, CapabilityDomainRecord).join(
        CapabilityDomainRecord,
        CapabilitySubCapabilityRecord.domain_id == CapabilityDomainRecord.id,
    )
    if domain:
        stmt = stmt.where(CapabilityDomainRecord.slug == domain)
    rows = session.exec(stmt).all()
    return [
        {
            "id": sc.id, "slug": sc.slug, "display_name": sc.display_name,
            "description": sc.description, "difficulty": sc.difficulty,
            "risk_level": sc.risk_level, "domain_slug": d.slug, "domain_id": sc.domain_id,
        }
        for sc, d in rows
    ]


@router.get("/scores/{model_id}")
def get_model_scores(model_id: int, session: Session = Depends(get_session)):
    """Return persisted capability scores for a model, with confidence intervals."""
    model = session.get(LLMModel, model_id)
    if not model:
        raise HTTPException(404, "Model not found")

    rows = session.exec(
        select(CapabilityEvalScore, CapabilitySubCapabilityRecord, CapabilityDomainRecord)
        .join(CapabilitySubCapabilityRecord, CapabilityEvalScore.sub_capability_id == CapabilitySubCapabilityRecord.id)
        .join(CapabilityDomainRecord, CapabilitySubCapabilityRecord.domain_id == CapabilityDomainRecord.id)
        .where(CapabilityEvalScore.model_id == model_id)
    ).all()

    return {
        "model_id": model_id,
        "model_name": model.name,
        "scores": [
            {
                "domain": d.slug,
                "sub_capability": sc.slug,
                "display_name": sc.display_name,
                "risk_level": sc.risk_level,
                "score": s.score,
                "ci_lower": s.ci_lower,
                "ci_upper": s.ci_upper,
                "n_items": s.n_items,
                "scored_at": s.scored_at.isoformat(),
            }
            for s, sc, d in rows
        ],
    }


@router.get("/coverage")
def get_coverage_gaps(session: Session = Depends(get_session)):
    """Return which sub-capabilities have NOT been evaluated for each active model.

    This directly answers the acceptance criterion:
      "Which capabilities has model X not been evaluated on?"
    """
    models = session.exec(select(LLMModel).where(LLMModel.is_active == True)).all()
    all_sub_caps = session.exec(
        select(CapabilitySubCapabilityRecord, CapabilityDomainRecord).join(
            CapabilityDomainRecord,
            CapabilitySubCapabilityRecord.domain_id == CapabilityDomainRecord.id,
        )
    ).all()

    result = []
    for model in models:
        scored_ids = {
            row.sub_capability_id
            for row in session.exec(
                select(CapabilityEvalScore).where(CapabilityEvalScore.model_id == model.id)
            ).all()
        }
        # Also check inferred scores from eval_runs (pre-DB-scoring era)
        runs = session.exec(select(EvalRun).where(EvalRun.model_id == model.id)).all()
        for run in runs:
            if run.score is not None:
                bench = session.get(Benchmark, run.benchmark_id)
                bench_name = bench.name if bench else str(run.benchmark_id)
                for domain_slug, _cap, sub_slug in (_taxonomy.infer_capabilities_from_benchmark(bench_name) or []):
                    # find sub_cap_id by slug+domain
                    for sc, d in all_sub_caps:
                        if sc.slug == sub_slug and d.slug == domain_slug:
                            scored_ids.add(sc.id)
                            break

        gaps = [
            {
                "sub_capability_id": sc.id,
                "sub_capability_slug": sc.slug,
                "domain_slug": d.slug,
                "risk_level": sc.risk_level,
                "difficulty": sc.difficulty,
            }
            for sc, d in all_sub_caps
            if sc.id not in scored_ids
        ]

        result.append({
            "model_id": model.id,
            "model_name": model.name,
            "evaluated_count": len(all_sub_caps) - len(gaps),
            "total_sub_capabilities": len(all_sub_caps),
            "coverage_pct": round(
                (len(all_sub_caps) - len(gaps)) / len(all_sub_caps) * 100, 1
            ) if all_sub_caps else 0.0,
            "gaps": gaps,
        })

    return {"models": result, "total_sub_capabilities": len(all_sub_caps)}


@router.get("/heatmap")
def get_heatmap(session: Session = Depends(get_session)):
    """Return model × capability matrix data for the coverage heatmap UI.

    Response shape::

        {
          "domains":       [{"slug": "cybersecurity", "display_name": "…", "sub_capabilities": […]}, …],
          "models":        [{"id": 1, "name": "gpt-4o", "provider": "openai"}, …],
          "scores":        {"1": {"vulnerability_analysis": 0.82, …}, …},  # model_id (str) → sub_cap_slug → score
          "coverage":      {"1": {"vulnerability_analysis": true, …}, …},  # model_id (str) → sub_cap_slug → covered?
        }

    If no scores have been persisted yet the heatmap falls back to computing
    coverage from ``eval_runs`` via the in-memory taxonomy engine.
    """
    # All active models
    models = session.exec(select(LLMModel).where(LLMModel.is_active == True)).all()

    # All domains + sub-capabilities (ordered)
    domain_rows = session.exec(
        select(CapabilityDomainRecord).order_by(CapabilityDomainRecord.sort_order)
    ).all()

    # Fallback to in-memory ontology if taxonomy not yet seeded
    if not domain_rows:
        return _heatmap_from_ontology(models, session)

    sub_cap_rows = session.exec(
        select(CapabilitySubCapabilityRecord, CapabilityDomainRecord).join(
            CapabilityDomainRecord,
            CapabilitySubCapabilityRecord.domain_id == CapabilityDomainRecord.id,
        ).order_by(CapabilityDomainRecord.sort_order, CapabilitySubCapabilityRecord.slug)
    ).all()

    # Persisted scores keyed by (model_id, sub_cap_id)
    all_scores = session.exec(select(CapabilityEvalScore)).all()
    score_index: dict[tuple[int, int], float] = {
        (s.model_id, s.sub_capability_id): s.score for s in all_scores
    }

    # Infer coverage from eval_runs for models without persisted scores
    run_coverage: dict[tuple[int, int], float] = {}
    all_sub_cap_by_slug: dict[tuple[str, str], int] = {}  # (domain_slug, sub_slug) → sub_cap_id
    for sc, d in sub_cap_rows:
        all_sub_cap_by_slug[(d.slug, sc.slug)] = sc.id

    for model in models:
        runs = session.exec(select(EvalRun).where(EvalRun.model_id == model.id)).all()
        for run in runs:
            if run.score is None:
                continue
            bench = session.get(Benchmark, run.benchmark_id)
            bench_name = bench.name if bench else str(run.benchmark_id)
            for domain_slug, _cap, sub_slug in (_taxonomy.infer_capabilities_from_benchmark(bench_name) or []):
                sc_id = all_sub_cap_by_slug.get((domain_slug, sub_slug))
                if sc_id is not None:
                    key = (model.id, sc_id)
                    # Use best observed score across runs
                    run_coverage[key] = max(run_coverage.get(key, 0.0), run.score)

    # Merge: persisted scores take priority over inferred
    merged: dict[tuple[int, int], float] = {**run_coverage, **score_index}

    # Build response
    domains_out = []
    for d in domain_rows:
        scs = [
            {
                "id": sc.id,
                "slug": sc.slug,
                "display_name": sc.display_name,
                "risk_level": sc.risk_level,
                "difficulty": sc.difficulty,
            }
            for sc, dom in sub_cap_rows if dom.id == d.id
        ]
        domains_out.append({
            "id": d.id,
            "slug": d.slug,
            "display_name": d.display_name,
            "sub_capabilities": scs,
        })

    scores_out: dict[str, dict[str, Optional[float]]] = {}
    coverage_out: dict[str, dict[str, bool]] = {}
    for model in models:
        mid = str(model.id)
        scores_out[mid] = {}
        coverage_out[mid] = {}
        for sc, d in sub_cap_rows:
            key = (model.id, sc.id)
            val = merged.get(key)
            scores_out[mid][sc.slug] = val
            coverage_out[mid][sc.slug] = val is not None

    return {
        "domains": domains_out,
        "models": [
            {"id": m.id, "name": m.name, "provider": m.provider}
            for m in models
        ],
        "scores": scores_out,
        "coverage": coverage_out,
    }


def _heatmap_from_ontology(models: list, session: Session) -> dict:
    """Fallback heatmap builder using the in-memory ontology (no taxonomy tables seeded yet)."""
    domains_out = []
    for domain_slug, domain_data in CAPABILITY_ONTOLOGY.items():
        scs = [
            {"id": None, "slug": sub_slug, "display_name": sub_slug.replace("_", " ").title(),
             "risk_level": sub_data.get("risk_level", "low"), "difficulty": sub_data.get("difficulty", "medium")}
            for sub_slug, sub_data in domain_data.get("sub_capabilities", {}).items()
        ]
        domains_out.append({"id": None, "slug": domain_slug,
                             "display_name": domain_slug.replace("_", " ").title(), "sub_capabilities": scs})

    scores_out: dict[str, dict[str, Optional[float]]] = {}
    coverage_out: dict[str, dict[str, bool]] = {}
    for model in models:
        mid = str(model.id)
        scores_out[mid] = {}
        coverage_out[mid] = {}
        runs = session.exec(select(EvalRun).where(EvalRun.model_id == model.id)).all()
        inferred_scores: dict[str, float] = {}
        for run in runs:
            if run.score is None:
                continue
            bench = session.get(Benchmark, run.benchmark_id)
            bench_name = bench.name if bench else str(run.benchmark_id)
            for _domain, _cap, sub_slug in (_taxonomy.infer_capabilities_from_benchmark(bench_name) or []):
                inferred_scores[sub_slug] = max(inferred_scores.get(sub_slug, 0.0), run.score)

        for _, domain_data in CAPABILITY_ONTOLOGY.items():
            for sub_slug in domain_data.get("sub_capabilities", {}):
                val = inferred_scores.get(sub_slug)
                scores_out[mid][sub_slug] = val
                coverage_out[mid][sub_slug] = val is not None

    return {
        "domains": domains_out,
        "models": [{"id": m.id, "name": m.name, "provider": m.provider} for m in models],
        "scores": scores_out,
        "coverage": coverage_out,
    }
