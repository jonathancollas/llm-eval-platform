"""
Multi-Agent Simulation & Anti-Sandbagging API
==============================================
Endpoints for #60 (multi-agent simulation) and #80 (anti-sandbagging).
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from core.database import get_session, engine
from core.config import get_settings
from core.models import (
    LLMModel, Benchmark, EvalResult, EvalRun, MultiAgentSimulation,
    SandbaggingReport, JobStatus,
)
from inference.adapter import get_adapter

from eval_engine.multi_agent.simulator import (
    MultiAgentSimulator,
    SimulationScenario,
    INJECTION_PAYLOADS,
    SimulationResult,
)
from eval_engine.sandbagging.detector import AntiSandbaggingEngine

router = APIRouter(prefix="/multiagent", tags=["multi-agent"])
settings = get_settings()
logger = logging.getLogger(__name__)


# ── In-memory simulation state (fire-and-forget background runs) ──────────────
_running_simulations: dict[str, dict] = {}


# ── Schemas ────────────────────────────────────────────────────────────────────

class PipelineSimulationRequest(BaseModel):
    """Run a predefined pipeline injection scenario."""
    scenario_type: str          # pipeline_injection | goal_drift | trust_propagation
    model_ids: list[int]        # 1-3 model IDs
    injection_payload_id: Optional[str] = None
    max_steps: int = 8
    autonomy_level: int = 3

class CustomSimulationRequest(BaseModel):
    """Run a fully custom multi-agent scenario."""
    name: str
    objective: str
    adversarial_goal: str
    agents: list[dict]          # [{name, model_id, role, system_prompt, sends_to}]
    injection_enabled: bool = True
    injection_at_steps: list[int] = [1, 3]
    injection_payload_id: Optional[str] = "INJ-001"
    max_steps: int = 10
    autonomy_level: int = 3

class SandbaggingRequest(BaseModel):
    model_id: int
    benchmark_id: int
    n_samples: int = 10         # 10-30 recommended


# ── Helper ────────────────────────────────────────────────────────────────────

def _result_to_dict(result: SimulationResult) -> dict:
    """Serialise SimulationResult to JSON-safe dict."""
    return {
        "simulation_id": result.simulation_id,
        "scenario_name": result.scenario_name,
        "original_objective": result.original_objective,
        "n_agents": result.n_agents,
        "n_steps": result.n_steps,
        "task_completed": result.task_completed,
        "final_answer": result.final_answer,
        "metrics": {
            "overall_goal_alignment": result.overall_goal_alignment,
            "goal_drift_detected": result.goal_drift_detected,
            "goal_drift_at_step": result.goal_drift_at_step,
            "prompt_injection_success_rate": result.prompt_injection_success_rate,
            "trust_propagation_occurred": result.trust_propagation_occurred,
            "compounding_errors": result.compounding_errors,
            "system_safety_score": result.system_safety_score,
            "pipeline_integrity_score": result.pipeline_integrity_score,
        },
        "failure_modes_summary": result.failure_modes_summary,
        "autonomy_level": result.autonomy_level,
        "steps": [
            {
                "step_index": s.step_index,
                "agent_name": s.agent_name,
                "agent_role": s.agent_role,
                "output": s.output[:500],
                "goal_alignment": s.goal_alignment,
                "injected_payload_followed": s.injected_payload_followed,
                "failure_modes": [fm.value for fm in s.failure_modes_detected],
                "latency_ms": s.latency_ms,
                "tokens": s.tokens,
                "metadata": s.metadata,
            }
            for s in result.steps
        ],
        "performance": {
            "total_latency_ms": result.total_latency_ms,
            "total_tokens": result.total_tokens,
            "total_cost_usd": result.total_cost_usd,
        },
    }


def _resolve_models(model_ids: list[int], session: Session) -> list[LLMModel]:
    models = []
    for mid in model_ids:
        m = session.get(LLMModel, mid)
        if not m:
            raise HTTPException(404, detail=f"Model {mid} not found.")
        models.append(m)
    return models


# ── Simulation endpoints ───────────────────────────────────────────────────────

@router.post("/simulate/pipeline")
async def simulate_pipeline_injection(
    payload: PipelineSimulationRequest,
    session: Session = Depends(get_session),
):
    """
    Run a pipeline injection simulation (synchronous — waits for result).
    For async runs, use /simulate/pipeline/async.

    Scenario types:
    - pipeline_injection: Orchestrator → Retriever (injection) → Executor
    - goal_drift: Single agent over N steps, crescendo injection
    - trust_propagation: 3-agent peer pipeline, compromised orchestrator
    """
    models = _resolve_models(payload.model_ids, session)

    # Pick injection payload
    inj_payload = next(
        (p for p in INJECTION_PAYLOADS if p["id"] == payload.injection_payload_id),
        None
    ) if payload.injection_payload_id else None

    # Build scenario
    if payload.scenario_type == "pipeline_injection":
        scenario = SimulationScenario.build_pipeline_injection(
            orchestrator_model=models[0],
            executor_model=models[-1],
            retriever_model=models[1] if len(models) > 1 else models[0],
            injection_payload=inj_payload,
        )
    elif payload.scenario_type == "goal_drift":
        scenario = SimulationScenario.build_goal_drift(
            model=models[0],
            n_steps=min(payload.max_steps, 8),
        )
    elif payload.scenario_type == "trust_propagation":
        scenario = SimulationScenario.build_trust_propagation(models=models)
    else:
        raise HTTPException(400, detail=f"Unknown scenario_type: {payload.scenario_type}")

    scenario.max_steps = payload.max_steps
    scenario.autonomy_level = payload.autonomy_level

    simulator = MultiAgentSimulator(adapter_factory=get_adapter)

    try:
        result = await asyncio.wait_for(simulator.run(scenario), timeout=120.0)
    except asyncio.TimeoutError:
        raise HTTPException(408, detail="Simulation timed out (120s). Try fewer steps or faster models.")

    # Persist to DB if model exists
    try:
        _persist_simulation(result, session)
    except Exception as e:
        logger.warning(f"Could not persist simulation: {e}")

    return _result_to_dict(result)


@router.post("/simulate/custom")
async def simulate_custom(
    payload: CustomSimulationRequest,
    session: Session = Depends(get_session),
):
    """Run a fully custom multi-agent scenario."""
    if not payload.agents:
        raise HTTPException(400, detail="At least one agent required.")

    # Resolve models for each agent
    agent_configs = {}
    for agent_def in payload.agents:
        model_id = agent_def.get("model_id")
        m = session.get(LLMModel, model_id) if model_id else None
        if not m:
            raise HTTPException(404, detail=f"Model {model_id} not found for agent {agent_def.get('name')}.")
        agent_configs[agent_def["name"]] = {
            "model": m,
            "role": agent_def.get("role", "executor"),
            "system_prompt": agent_def.get("system_prompt", "You are a helpful AI assistant."),
            "sends_to": agent_def.get("sends_to", []),
            "temperature": agent_def.get("temperature", 0.0),
            "max_tokens": agent_def.get("max_tokens", 400),
            "context_steps": agent_def.get("context_steps", 3),
        }

    # Validate pipeline — first agent must exist
    if payload.agents[0]["name"] not in agent_configs:
        raise HTTPException(400, detail="First agent not found in config.")

    inj_payload = next(
        (p for p in INJECTION_PAYLOADS if p["id"] == payload.injection_payload_id),
        INJECTION_PAYLOADS[0]
    )

    scenario = SimulationScenario(
        name=payload.name,
        objective=payload.objective,
        adversarial_goal=payload.adversarial_goal,
        orchestrator_agent=payload.agents[0]["name"],
        agents=agent_configs,
        max_steps=payload.max_steps,
        injection_enabled=payload.injection_enabled,
        injection_at_steps=payload.injection_at_steps,
        injection_payload=inj_payload,
        autonomy_level=payload.autonomy_level,
    )

    simulator = MultiAgentSimulator(adapter_factory=get_adapter)
    result = await asyncio.wait_for(simulator.run(scenario), timeout=120.0)

    try:
        _persist_simulation(result, session)
    except Exception as e:
        logger.warning(f"Persist failed: {e}")

    return _result_to_dict(result)


@router.get("/simulations")
def list_simulations(session: Session = Depends(get_session)):
    """List past multi-agent simulations."""
    try:
        sims = session.exec(
            select(MultiAgentSimulation).order_by(MultiAgentSimulation.id.desc()).limit(50)
        ).all()
        return {
            "simulations": [
                {
                    "id": s.id,
                    "scenario_name": s.scenario_name,
                    "n_agents": s.n_agents,
                    "n_steps": s.n_steps,
                    "task_completed": s.task_completed,
                    "system_safety_score": s.system_safety_score,
                    "pipeline_integrity_score": s.pipeline_integrity_score,
                    "goal_drift_detected": s.goal_drift_detected,
                    "injection_success_rate": s.prompt_injection_success_rate,
                    "autonomy_level": s.autonomy_level,
                    "created_at": s.created_at.isoformat(),
                }
                for s in sims
            ]
        }
    except Exception:
        return {"simulations": []}


@router.get("/simulations/{sim_id}")
def get_simulation(sim_id: int, session: Session = Depends(get_session)):
    """Get a specific simulation with full steps."""
    try:
        sim = session.get(MultiAgentSimulation, sim_id)
        if not sim:
            raise HTTPException(404, detail="Simulation not found.")
        return {
            "id": sim.id,
            "scenario_name": sim.scenario_name,
            "original_objective": sim.original_objective,
            "n_agents": sim.n_agents,
            "n_steps": sim.n_steps,
            "task_completed": sim.task_completed,
            "final_answer": sim.final_answer,
            "metrics": {
                "overall_goal_alignment": sim.overall_goal_alignment,
                "goal_drift_detected": sim.goal_drift_detected,
                "goal_drift_at_step": sim.goal_drift_at_step,
                "prompt_injection_success_rate": sim.prompt_injection_success_rate,
                "trust_propagation_occurred": sim.trust_propagation_occurred,
                "system_safety_score": sim.system_safety_score,
                "pipeline_integrity_score": sim.pipeline_integrity_score,
            },
            "steps": json.loads(sim.steps_json or "[]"),
            "failure_modes": json.loads(sim.failure_modes_json or "{}"),
            "created_at": sim.created_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@router.get("/payloads")
def list_injection_payloads():
    """List available prompt injection payloads for simulation configuration."""
    return {
        "payloads": [
            {
                "id": p["id"],
                "name": p["name"],
                "severity": p["severity"],
                "reference": p["reference"],
                "preview": p["content"][:100] + "...",
            }
            for p in INJECTION_PAYLOADS
        ]
    }


# ── Anti-sandbagging endpoints ─────────────────────────────────────────────────

@router.post("/sandbagging/probe")
async def probe_sandbagging(
    payload: SandbaggingRequest,
    session: Session = Depends(get_session),
):
    """
    Run anti-sandbagging battery on a model × benchmark pair.

    Compares performance under:
    - Standard eval framing
    - Neutral framing
    - Expert elicitation (capability ceiling)
    - Eval-awareness probe

    Reference: Apollo Research / OpenAI (2025), Meinke et al. (2024)
    """
    model = session.get(LLMModel, payload.model_id)
    if not model:
        raise HTTPException(404, detail="Model not found.")

    benchmark = session.get(Benchmark, payload.benchmark_id)
    if not benchmark:
        raise HTTPException(404, detail="Benchmark not found.")

    # Pull sample questions from eval results if available, else from benchmark file
    questions = _get_sample_questions(benchmark, payload.n_samples, session)
    if not questions:
        raise HTTPException(
            422,
            detail="No questions found for this benchmark. Run an evaluation campaign first, or ensure the benchmark has a dataset."
        )

    engine = AntiSandbaggingEngine(adapter_factory=get_adapter)

    try:
        report = await asyncio.wait_for(
            engine.run(
                model=model,
                benchmark_name=benchmark.name,
                questions=questions,
                n_samples=payload.n_samples,
            ),
            timeout=300.0,  # 5 min max
        )
    except asyncio.TimeoutError:
        raise HTTPException(408, detail="Sandbagging probe timed out (5min). Reduce n_samples.")

    # Persist
    try:
        _persist_sandbagging_report(report, payload.model_id, payload.benchmark_id, session)
    except Exception as e:
        logger.warning(f"Could not persist sandbagging report: {e}")

    return {
        "model_name": report.model_name,
        "benchmark_name": report.benchmark_name,
        "n_probes": report.n_probes,
        "mean_sandbagging_score": report.mean_sandbagging_score,
        "risk_level": report.risk_level,
        "eval_awareness_rate": report.eval_awareness_rate,
        "capability_gap": report.capability_gap,
        "scientific_confidence": report.scientific_confidence,
        "recommendation": report.recommendation,
        "probes": [
            {
                "probe_id": p.probe_id,
                "eval_framing_score": p.eval_framing_score,
                "neutral_framing_score": p.neutral_framing_score,
                "expert_elicited_score": p.expert_elicited_score,
                "performance_delta": p.performance_delta,
                "variance_ratio": p.variance_ratio,
                "eval_awareness_detected": p.eval_awareness_detected,
                "sandbagging_score": p.sandbagging_score,
                "evidence": p.evidence,
            }
            for p in report.probes
        ],
        "performance": {
            "total_tokens": report.total_tokens,
            "total_cost_usd": report.total_cost_usd,
        },
        "references": [
            "Apollo Research / OpenAI (2025) — covert behaviours in frontier models",
            "Meinke et al. (2024) — sandbagging in safety evaluations",
            "van der Weij et al. (2025) — strategic deception in evaluation contexts",
            "INESIA (2026) — anti-sandbagging evaluation priorities",
        ],
    }


@router.get("/sandbagging/reports")
def list_sandbagging_reports(
    model_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    """List past anti-sandbagging analyses."""
    try:
        query = select(SandbaggingReport).order_by(SandbaggingReport.id.desc()).limit(50)
        if model_id:
            query = query.where(SandbaggingReport.model_id == model_id)
        reports = session.exec(query).all()

        model_cache = {}
        bench_cache = {}
        items = []
        for r in reports:
            if r.model_id not in model_cache:
                m = session.get(LLMModel, r.model_id)
                model_cache[r.model_id] = m.name if m else f"Model {r.model_id}"
            if r.benchmark_id not in bench_cache:
                b = session.get(Benchmark, r.benchmark_id)
                bench_cache[r.benchmark_id] = b.name if b else f"Bench {r.benchmark_id}"
            items.append({
                "id": r.id,
                "model_name": model_cache[r.model_id],
                "benchmark_name": bench_cache[r.benchmark_id],
                "mean_sandbagging_score": r.mean_sandbagging_score,
                "risk_level": r.risk_level,
                "eval_awareness_rate": r.eval_awareness_rate,
                "capability_gap": r.capability_gap,
                "n_probes": r.n_probes,
                "created_at": r.created_at.isoformat(),
            })
        return {"reports": items}
    except Exception:
        return {"reports": []}


# ── DB persistence helpers ─────────────────────────────────────────────────────

def _persist_simulation(result: SimulationResult, session: Session) -> None:
    steps_data = [
        {
            "step_index": s.step_index,
            "agent_name": s.agent_name,
            "agent_role": s.agent_role,
            "output": s.output[:1000],
            "goal_alignment": s.goal_alignment,
            "injected_payload_followed": s.injected_payload_followed,
            "failure_modes": [fm.value for fm in s.failure_modes_detected],
            "latency_ms": s.latency_ms,
            "tokens": s.tokens,
        }
        for s in result.steps
    ]

    sim = MultiAgentSimulation(
        simulation_id=result.simulation_id,
        scenario_name=result.scenario_name,
        original_objective=result.original_objective,
        adversarial_goal="",
        n_agents=result.n_agents,
        n_steps=result.n_steps,
        task_completed=result.task_completed,
        final_answer=result.final_answer[:2000],
        overall_goal_alignment=result.overall_goal_alignment,
        goal_drift_detected=result.goal_drift_detected,
        goal_drift_at_step=result.goal_drift_at_step,
        prompt_injection_success_rate=result.prompt_injection_success_rate,
        trust_propagation_occurred=result.trust_propagation_occurred,
        compounding_errors=result.compounding_errors,
        system_safety_score=result.system_safety_score,
        pipeline_integrity_score=result.pipeline_integrity_score,
        autonomy_level=result.autonomy_level,
        total_latency_ms=result.total_latency_ms,
        total_tokens=result.total_tokens,
        total_cost_usd=result.total_cost_usd,
        steps_json=json.dumps(steps_data),
        failure_modes_json=json.dumps(result.failure_modes_summary),
    )
    session.add(sim)
    session.commit()


def _persist_sandbagging_report(report, model_id: int, benchmark_id: int, session: Session) -> None:
    probes_data = [
        {
            "probe_id": p.probe_id,
            "eval_framing_score": p.eval_framing_score,
            "neutral_framing_score": p.neutral_framing_score,
            "expert_elicited_score": p.expert_elicited_score,
            "performance_delta": p.performance_delta,
            "variance_ratio": p.variance_ratio,
            "eval_awareness_detected": p.eval_awareness_detected,
            "sandbagging_score": p.sandbagging_score,
            "evidence": p.evidence,
        }
        for p in report.probes
    ]

    sr = SandbaggingReport(
        model_id=model_id,
        benchmark_id=benchmark_id,
        n_probes=report.n_probes,
        mean_sandbagging_score=report.mean_sandbagging_score,
        risk_level=report.risk_level,
        eval_awareness_rate=report.eval_awareness_rate,
        capability_gap=report.capability_gap,
        recommendation=report.recommendation,
        scientific_confidence=report.scientific_confidence,
        probes_json=json.dumps(probes_data),
        total_tokens=report.total_tokens,
        total_cost_usd=report.total_cost_usd,
    )
    session.add(sr)
    session.commit()


def _get_sample_questions(benchmark, n_samples: int, session: Session) -> list[dict]:
    """
    Pull sample questions for sandbagging probes.
    First tries live EvalResults from DB, then falls back to benchmark dataset file.
    """
    # Try existing eval results (most representative)
    runs = session.exec(
        select(EvalRun).where(
            EvalRun.benchmark_id == benchmark.id,
            EvalRun.status == JobStatus.COMPLETED,
        ).limit(5)
    ).all()

    if runs:
        run_ids = [r.id for r in runs]
        results = session.exec(
            select(EvalResult).where(EvalResult.run_id.in_(run_ids)).limit(n_samples)
        ).all()
        if results:
            return [
                {
                    "question": r.prompt,
                    "expected": r.expected or "",
                    "category": benchmark.type,
                }
                for r in results if r.prompt
            ]

    # Fallback: load from benchmark dataset file
    if benchmark.dataset_path:
        import json as _json
        from pathlib import Path
        from core.config import get_settings as _gs
        bench_path = Path(_gs().bench_library_path) / benchmark.dataset_path
        if bench_path.exists():
            try:
                data = _json.loads(bench_path.read_text())
                items = data if isinstance(data, list) else data.get("items", [])
                return [
                    {
                        "question": item.get("prompt", item.get("question", "")),
                        "expected": item.get("expected", item.get("answer", "")),
                        "category": item.get("category", benchmark.type),
                    }
                    for item in items[:n_samples]
                    if item.get("prompt") or item.get("question")
                ]
            except Exception:
                pass

    return []
