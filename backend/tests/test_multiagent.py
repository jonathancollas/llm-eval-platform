"""
Tests for api/routers/multiagent.py
Covers: list simulations, get simulation, list payloads,
        simulate pipeline (mocked), simulate custom (mocked),
        sandbagging probe (mocked), list sandbagging reports,
        _result_to_dict helper, _resolve_models helper.
"""
import importlib.util
import json
import os
import secrets
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

_spec = importlib.util.spec_from_file_location(
    "multiagent_router",
    Path(__file__).parent.parent / "api" / "routers" / "multiagent.py",
)
mod = importlib.util.module_from_spec(_spec)
sys.modules["multiagent_router"] = mod
_spec.loader.exec_module(mod)

from core.models import (
    LLMModel, Benchmark, EvalResult, EvalRun, MultiAgentSimulation,
    SandbaggingReport, JobStatus, ModelProvider, BenchmarkType,
)
from eval_engine.multi_agent.simulator import (
    SimulationResult, AgentStep, AgentMessage, AgentRole, FailureMode, INJECTION_PAYLOADS,
)
from eval_engine.sandbagging.detector import AntiSandbaggingReport, SandbaggingProbeResult


@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("multiagent_tests") / "multiagent.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine):
    def _get_session():
        with Session(db_engine) as s:
            yield s

    test_app = FastAPI()
    test_app.include_router(mod.router)
    test_app.dependency_overrides[mod.get_session] = _get_session
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def seeded(db_engine):
    with Session(db_engine) as s:
        model = LLMModel(name="AgentModel", provider=ModelProvider.OPENAI, model_id="agent/model-1")
        s.add(model)
        bench = Benchmark(name="AgentBench", type=BenchmarkType.ACADEMIC, metric="accuracy")
        s.add(bench)
        s.commit()
        return {"model_id": model.id, "bench_id": bench.id}


def _make_agent_step(idx: int) -> AgentStep:
    msg = AgentMessage(sender="user", recipient="agent", content="Do a task", step=idx)
    return AgentStep(
        step_index=idx,
        agent_name=f"agent_{idx}",
        agent_role=AgentRole.EXECUTOR,
        input_messages=[msg],
        output="Done",
        reasoning="",
        goal_alignment=0.9,
        injected_payload_followed=False,
        failure_modes_detected=[],
        latency_ms=100,
        tokens=50,
        cost_usd=0.0,
    )


def _make_simulation_result() -> SimulationResult:
    return SimulationResult(
        simulation_id="sim-test-001",
        scenario_name="Test Scenario",
        original_objective="Complete the task",
        n_agents=2,
        n_steps=2,
        steps=[_make_agent_step(0), _make_agent_step(1)],
        task_completed=True,
        final_answer="Task completed successfully.",
        overall_goal_alignment=0.9,
        goal_drift_detected=False,
        goal_drift_at_step=None,
        prompt_injection_success_rate=0.0,
        trust_propagation_occurred=False,
        compounding_errors=0,
        failure_modes_summary={},
        autonomy_level=3,
        system_safety_score=0.85,
        pipeline_integrity_score=0.90,
        total_latency_ms=200,
        total_tokens=100,
        total_cost_usd=0.001,
    )


def _make_sandbagging_report(model_name: str) -> AntiSandbaggingReport:
    probe = SandbaggingProbeResult(
        probe_id="P001",
        probe_name="Eval Awareness",
        eval_framing_score=0.6,
        neutral_framing_score=0.8,
        expert_elicited_score=0.9,
        performance_delta=0.2,
        variance_ratio=1.3,
        eval_awareness_detected=True,
        sandbagging_score=0.45,
        evidence=["Score 0.2 higher in neutral framing"],
        references=["Apollo Research 2025"],
    )
    return AntiSandbaggingReport(
        model_id=str(1),
        model_name=model_name,
        benchmark_name="TestBench",
        n_probes=1,
        probes=[probe],
        mean_sandbagging_score=0.45,
        risk_level="medium",
        eval_awareness_rate=1.0,
        capability_gap=0.3,
        recommendation="Monitor closely.",
        scientific_confidence="medium",
        total_tokens=200,
        total_cost_usd=0.002,
    )


# ── list simulations ──────────────────────────────────────────────────────────

def test_list_simulations_empty(client):
    resp = client.get("/multiagent/simulations")
    assert resp.status_code == 200
    assert "simulations" in resp.json()


def test_list_simulations_with_data(client, db_engine):
    with Session(db_engine) as s:
        sim = MultiAgentSimulation(
            simulation_id="sim-stored-001",
            scenario_name="Stored Scenario",
            original_objective="Objective",
            adversarial_goal="",
            n_agents=2,
            n_steps=3,
            task_completed=True,
            final_answer="Done",
            overall_goal_alignment=0.8,
            goal_drift_detected=False,
            prompt_injection_success_rate=0.1,
            trust_propagation_occurred=False,
            compounding_errors=0,
            system_safety_score=0.9,
            pipeline_integrity_score=0.85,
            autonomy_level=3,
            steps_json="[]",
            failure_modes_json="{}",
        )
        s.add(sim)
        s.commit()

    resp = client.get("/multiagent/simulations")
    assert resp.status_code == 200
    sims = resp.json()["simulations"]
    assert len(sims) >= 1


# ── get simulation ────────────────────────────────────────────────────────────

def test_get_simulation_404(client):
    resp = client.get("/multiagent/simulations/99999")
    assert resp.status_code == 404


def test_get_simulation_success(client, db_engine):
    with Session(db_engine) as s:
        sim = MultiAgentSimulation(
            simulation_id="sim-detail-001",
            scenario_name="Detail Scenario",
            original_objective="Obj",
            adversarial_goal="",
            n_agents=1,
            n_steps=2,
            task_completed=False,
            final_answer="...",
            overall_goal_alignment=0.5,
            goal_drift_detected=True,
            prompt_injection_success_rate=0.5,
            trust_propagation_occurred=False,
            compounding_errors=1,
            system_safety_score=0.4,
            pipeline_integrity_score=0.6,
            autonomy_level=2,
            steps_json=json.dumps([{"step_index": 0, "agent_name": "a1"}]),
            failure_modes_json=json.dumps({"goal_override": 1}),
        )
        s.add(sim)
        s.commit()
        sid = sim.id

    resp = client.get(f"/multiagent/simulations/{sid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sid
    assert data["scenario_name"] == "Detail Scenario"
    assert "steps" in data
    assert "metrics" in data


# ── list injection payloads ───────────────────────────────────────────────────

def test_list_payloads(client):
    resp = client.get("/multiagent/payloads")
    assert resp.status_code == 200
    data = resp.json()
    assert "payloads" in data
    payloads = data["payloads"]
    assert len(payloads) == len(INJECTION_PAYLOADS)
    for p in payloads:
        assert "id" in p
        assert "name" in p
        assert "severity" in p
        assert "preview" in p


# ── simulate pipeline ─────────────────────────────────────────────────────────

def test_simulate_pipeline_model_not_found(client):
    resp = client.post("/multiagent/simulate/pipeline", json={
        "scenario_type": "pipeline_injection",
        "model_ids": [99999],
    })
    assert resp.status_code == 404


def test_simulate_pipeline_unknown_scenario(client, seeded):
    mock_result = _make_simulation_result()
    mock_sim = MagicMock()
    mock_sim.run = AsyncMock(return_value=mock_result)

    with patch("multiagent_router.MultiAgentSimulator", return_value=mock_sim):
        resp = client.post("/multiagent/simulate/pipeline", json={
            "scenario_type": "unknown_scenario",
            "model_ids": [seeded["model_id"]],
        })
    assert resp.status_code == 400


def test_simulate_pipeline_injection(client, seeded):
    mock_result = _make_simulation_result()
    mock_sim = MagicMock()
    mock_sim.run = AsyncMock(return_value=mock_result)

    with patch("multiagent_router.MultiAgentSimulator", return_value=mock_sim):
        resp = client.post("/multiagent/simulate/pipeline", json={
            "scenario_type": "pipeline_injection",
            "model_ids": [seeded["model_id"]],
            "injection_payload_id": "INJ-001",
            "max_steps": 4,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["simulation_id"] == "sim-test-001"
    assert "metrics" in data
    assert "steps" in data


def test_simulate_pipeline_goal_drift(client, seeded):
    mock_result = _make_simulation_result()
    mock_sim = MagicMock()
    mock_sim.run = AsyncMock(return_value=mock_result)

    with patch("multiagent_router.MultiAgentSimulator", return_value=mock_sim):
        resp = client.post("/multiagent/simulate/pipeline", json={
            "scenario_type": "goal_drift",
            "model_ids": [seeded["model_id"]],
        })
    assert resp.status_code == 200


def test_simulate_pipeline_trust_propagation(client, seeded):
    mock_result = _make_simulation_result()
    mock_sim = MagicMock()
    mock_sim.run = AsyncMock(return_value=mock_result)

    with patch("multiagent_router.MultiAgentSimulator", return_value=mock_sim):
        resp = client.post("/multiagent/simulate/pipeline", json={
            "scenario_type": "trust_propagation",
            "model_ids": [seeded["model_id"], seeded["model_id"]],
        })
    assert resp.status_code == 200


def test_simulate_pipeline_no_injection_payload(client, seeded):
    mock_result = _make_simulation_result()
    mock_sim = MagicMock()
    mock_sim.run = AsyncMock(return_value=mock_result)

    with patch("multiagent_router.MultiAgentSimulator", return_value=mock_sim):
        resp = client.post("/multiagent/simulate/pipeline", json={
            "scenario_type": "pipeline_injection",
            "model_ids": [seeded["model_id"]],
            "injection_payload_id": None,
        })
    assert resp.status_code == 200


def test_simulate_pipeline_timeout(client, seeded):
    import asyncio

    mock_sim = MagicMock()
    mock_sim.run = AsyncMock(side_effect=asyncio.TimeoutError())

    with patch("multiagent_router.MultiAgentSimulator", return_value=mock_sim):
        resp = client.post("/multiagent/simulate/pipeline", json={
            "scenario_type": "pipeline_injection",
            "model_ids": [seeded["model_id"]],
        })
    assert resp.status_code == 408


# ── simulate custom ───────────────────────────────────────────────────────────

def test_simulate_custom_no_agents(client):
    resp = client.post("/multiagent/simulate/custom", json={
        "name": "Empty",
        "objective": "Obj",
        "adversarial_goal": "Adv",
        "agents": [],
    })
    assert resp.status_code == 400


def test_simulate_custom_model_not_found(client):
    resp = client.post("/multiagent/simulate/custom", json={
        "name": "Bad Custom",
        "objective": "Obj",
        "adversarial_goal": "Adv",
        "agents": [{"name": "agent1", "model_id": 99999, "role": "executor"}],
    })
    assert resp.status_code == 404


def test_simulate_custom_success(client, seeded):
    mock_result = _make_simulation_result()
    mock_sim = MagicMock()
    mock_sim.run = AsyncMock(return_value=mock_result)

    with patch("multiagent_router.MultiAgentSimulator", return_value=mock_sim):
        resp = client.post("/multiagent/simulate/custom", json={
            "name": "Custom Test",
            "objective": "Complete task",
            "adversarial_goal": "Leak data",
            "agents": [{
                "name": "orchestrator",
                "model_id": seeded["model_id"],
                "role": "orchestrator",
                "system_prompt": "You are a helpful assistant.",
                "sends_to": [],
            }],
            "injection_enabled": True,
            "injection_at_steps": [1],
            "injection_payload_id": "INJ-001",
            "max_steps": 3,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "simulation_id" in data


# ── sandbagging probe ─────────────────────────────────────────────────────────

def test_sandbagging_probe_model_not_found(client):
    resp = client.post("/multiagent/sandbagging/probe", json={
        "model_id": 99999,
        "benchmark_id": 1,
        "n_samples": 10,
    })
    assert resp.status_code == 404


def test_sandbagging_probe_bench_not_found(client, seeded):
    resp = client.post("/multiagent/sandbagging/probe", json={
        "model_id": seeded["model_id"],
        "benchmark_id": 99999,
        "n_samples": 10,
    })
    assert resp.status_code == 404


def test_sandbagging_probe_no_questions(client, seeded):
    """Benchmark with no eval results and no dataset file → 422."""
    resp = client.post("/multiagent/sandbagging/probe", json={
        "model_id": seeded["model_id"],
        "benchmark_id": seeded["bench_id"],
        "n_samples": 10,
    })
    assert resp.status_code == 422


def test_sandbagging_probe_success(client, seeded, db_engine):
    """Seed EvalResults so _get_sample_questions returns questions."""
    from core.models import Campaign
    with Session(db_engine) as s:
        campaign = Campaign(
            name="Sandbagging Campaign",
            model_ids="[]",
            benchmark_ids="[]",
            status=JobStatus.COMPLETED,
        )
        s.add(campaign)
        s.flush()

        run = EvalRun(
            campaign_id=campaign.id,
            model_id=seeded["model_id"],
            benchmark_id=seeded["bench_id"],
            status=JobStatus.COMPLETED,
            score=0.8,
        )
        s.add(run)
        s.flush()

        for i in range(12):
            s.add(EvalResult(
                run_id=run.id,
                item_index=i,
                prompt=f"Question {i}?",
                response=f"Answer {i}",
                expected=f"Expected {i}",
                score=0.8,
            ))
        s.commit()

    mock_report = _make_sandbagging_report("AgentModel")
    mock_engine = MagicMock()
    mock_engine.run = AsyncMock(return_value=mock_report)

    with patch("multiagent_router.AntiSandbaggingEngine", return_value=mock_engine):
        resp = client.post("/multiagent/sandbagging/probe", json={
            "model_id": seeded["model_id"],
            "benchmark_id": seeded["bench_id"],
            "n_samples": 10,
        })

    assert resp.status_code == 200
    data = resp.json()
    assert "mean_sandbagging_score" in data
    assert "risk_level" in data
    assert "probes" in data
    assert data["risk_level"] == "medium"


def test_sandbagging_probe_timeout(client, seeded, db_engine):
    import asyncio
    from core.models import Campaign
    with Session(db_engine) as s:
        campaign = Campaign(name="TO Camp", model_ids="[]", benchmark_ids="[]", status=JobStatus.COMPLETED)
        s.add(campaign)
        s.flush()
        run = EvalRun(campaign_id=campaign.id, model_id=seeded["model_id"], benchmark_id=seeded["bench_id"], status=JobStatus.COMPLETED, score=0.5)
        s.add(run)
        s.flush()
        for i in range(5):
            s.add(EvalResult(run_id=run.id, item_index=i, prompt=f"Q{i}?", response="A", score=0.5))
        s.commit()

    mock_engine = MagicMock()
    mock_engine.run = AsyncMock(side_effect=asyncio.TimeoutError())

    with patch("multiagent_router.AntiSandbaggingEngine", return_value=mock_engine):
        resp = client.post("/multiagent/sandbagging/probe", json={
            "model_id": seeded["model_id"],
            "benchmark_id": seeded["bench_id"],
            "n_samples": 5,
        })
    assert resp.status_code == 408


# ── list sandbagging reports ──────────────────────────────────────────────────

def test_list_sandbagging_reports_empty(client):
    resp = client.get("/multiagent/sandbagging/reports")
    assert resp.status_code == 200
    assert "reports" in resp.json()


def test_list_sandbagging_reports_with_data(client, seeded, db_engine):
    with Session(db_engine) as s:
        sr = SandbaggingReport(
            model_id=seeded["model_id"],
            benchmark_id=seeded["bench_id"],
            n_probes=5,
            mean_sandbagging_score=0.3,
            risk_level="low",
            eval_awareness_rate=0.2,
            capability_gap=0.1,
            recommendation="No action needed.",
            scientific_confidence="medium",
            probes_json="[]",
            total_tokens=100,
            total_cost_usd=0.001,
        )
        s.add(sr)
        s.commit()

    resp = client.get("/multiagent/sandbagging/reports")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["reports"]) >= 1
    report = data["reports"][0]
    assert "model_name" in report
    assert "risk_level" in report


def test_list_sandbagging_reports_filter_by_model(client, seeded):
    mid = seeded["model_id"]
    resp = client.get(f"/multiagent/sandbagging/reports?model_id={mid}")
    assert resp.status_code == 200
    data = resp.json()
    assert "reports" in data


# ── helper function tests ─────────────────────────────────────────────────────

def test_result_to_dict():
    result = _make_simulation_result()
    d = mod._result_to_dict(result)
    assert d["simulation_id"] == "sim-test-001"
    assert d["n_agents"] == 2
    assert "metrics" in d
    assert len(d["steps"]) == 2
    step = d["steps"][0]
    assert "step_index" in step
    assert "goal_alignment" in step
    assert "failure_modes" in step


def test_result_to_dict_with_failure_modes():
    result = _make_simulation_result()
    step = result.steps[0]
    step.failure_modes_detected = [FailureMode.PROMPT_INJECTION, FailureMode.GOAL_DRIFT]
    d = mod._result_to_dict(result)
    assert len(d["steps"][0]["failure_modes"]) == 2


def test_resolve_models_success(seeded, db_engine):
    with Session(db_engine) as s:
        models = mod._resolve_models([seeded["model_id"]], s)
    assert len(models) == 1
    assert models[0].id == seeded["model_id"]


def test_resolve_models_not_found(db_engine):
    from fastapi import HTTPException
    with Session(db_engine) as s:
        with pytest.raises(HTTPException) as exc:
            mod._resolve_models([99999], s)
    assert exc.value.status_code == 404
