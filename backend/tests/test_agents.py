"""
Tests for api/routers/agents.py
Covers: pure scoring functions (6 axes + genome bridge),
        CRUD endpoints (create_trajectory, list, get, evaluate rule-based, dashboard).
"""
import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

_spec = importlib.util.spec_from_file_location(
    "agents_router",
    Path(__file__).parent.parent / "api" / "routers" / "agents.py",
)
agents_mod = importlib.util.module_from_spec(_spec)
sys.modules["agents_router"] = agents_mod
_spec.loader.exec_module(agents_mod)

from agents_router import (
    _score_task_completion,
    _score_tool_precision,
    _score_planning_coherence,
    _score_error_recovery,
    _score_safety_compliance,
    _score_cost_efficiency,
    _agent_scores_to_genome,
)
from core.models import AgentTrajectory, LLMModel, ModelProvider


# ── DB & app fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("agents_tests") / "agents.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine):
    def _get_session():
        with Session(db_engine) as s:
            yield s

    test_app = FastAPI()
    test_app.include_router(agents_mod.router)
    test_app.dependency_overrides[agents_mod.get_session] = _get_session
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def model_id(db_engine):
    """Seed a LLMModel and return its id."""
    with Session(db_engine) as s:
        m = LLMModel(
            name="TestAgent", provider=ModelProvider.CUSTOM, model_id="test/agent-v1",
            cost_input_per_1k=0.001, cost_output_per_1k=0.002,
        )
        s.add(m)
        s.commit()
        mid = m.id
    return mid


# ══════════════════════════════════════════════════════════════════════════════
# Pure scoring functions
# ══════════════════════════════════════════════════════════════════════════════

def _make_traj(**kwargs) -> AgentTrajectory:
    defaults = dict(
        model_id=1, task_description="test", task_type="generic",
        task_completed=False, final_answer="", expected_answer=None,
        num_steps=1, total_tokens=0, total_cost_usd=0.0, total_latency_ms=0,
        steps_json="[]",
    )
    defaults.update(kwargs)
    return AgentTrajectory(**defaults)


# ── _score_task_completion ────────────────────────────────────────────────────

def test_task_completion_completed_flag():
    traj = _make_traj(task_completed=True)
    assert _score_task_completion(traj, []) == 1.0


def test_task_completion_expected_contained_in_answer():
    traj = _make_traj(task_completed=False, expected_answer="paris", final_answer="The answer is Paris, France.")
    assert _score_task_completion(traj, []) == 0.9


def test_task_completion_answer_no_match():
    traj = _make_traj(task_completed=False, expected_answer="london", final_answer="The answer is Paris.")
    assert _score_task_completion(traj, []) == 0.3


def test_task_completion_long_answer_without_expected():
    traj = _make_traj(task_completed=False, final_answer="A" * 25)
    assert _score_task_completion(traj, []) == 0.5


def test_task_completion_empty_answer():
    traj = _make_traj(task_completed=False)
    assert _score_task_completion(traj, []) == 0.0


# ── _score_tool_precision ─────────────────────────────────────────────────────

def test_tool_precision_no_steps_neutral():
    assert _score_tool_precision([]) == 0.5


def test_tool_precision_no_tool_steps_neutral():
    steps = [{"action": "think", "observation": "ok"}]
    assert _score_tool_precision(steps) == 0.5


def test_tool_precision_all_good_tools():
    steps = [{"tool": "search", "observation": "result", "error": None}]
    assert _score_tool_precision(steps) == 1.0


def test_tool_precision_all_errors():
    steps = [
        {"tool": "search", "observation": "", "error": "timeout"},
        {"tool": "code", "observation": "", "error": "syntax error"},
    ]
    score = _score_tool_precision(steps)
    assert score < 1.0


def test_tool_precision_mixed():
    steps = [
        {"tool": "search", "observation": "ok", "error": None},
        {"tool": "code", "observation": "", "error": "oops"},
    ]
    score = _score_tool_precision(steps)
    assert 0.0 < score < 1.0


# ── _score_planning_coherence ─────────────────────────────────────────────────

def test_planning_coherence_single_step():
    assert _score_planning_coherence([{"action": "search"}]) == 0.8


def test_planning_coherence_unique_diverse_steps():
    steps = [
        {"action": "search", "tool_args": {"q": "1"}, "thought": "I should search"},
        {"action": "code",   "tool_args": {"q": "2"}, "thought": "Now I will code"},
        {"action": "reply",  "tool_args": {},          "thought": "Done"},
    ]
    score = _score_planning_coherence(steps)
    assert score > 0.7


def test_planning_coherence_repeated_actions_penalized():
    step = {"action": "search", "tool_args": {"q": "same"}, "thought": ""}
    steps = [step] * 8
    score = _score_planning_coherence(steps)
    assert score < 0.8


# ── _score_error_recovery ─────────────────────────────────────────────────────

def test_error_recovery_no_errors():
    steps = [{"action": "search", "observation": "result"}]
    assert _score_error_recovery(steps) == 1.0


def test_error_recovery_error_with_recovery():
    steps = [
        {"action": "search", "error": "timeout", "observation": ""},
        {"action": "search", "error": None, "observation": "result"},
    ]
    assert _score_error_recovery(steps) == 1.0


def test_error_recovery_error_no_recovery():
    steps = [
        {"action": "code", "error": "crash", "observation": ""},
    ]
    assert _score_error_recovery(steps) == 0.0


def test_error_recovery_partial():
    steps = [
        {"action": "a", "error": "err1", "observation": ""},
        {"action": "b", "error": "err2", "observation": ""},
        {"action": "c", "error": None,   "observation": "ok"},
    ]
    score = _score_error_recovery(steps)
    # err1 has recovery (step c), err2 has recovery (step c)
    assert score > 0.0


# ── _score_safety_compliance ──────────────────────────────────────────────────

def test_safety_compliance_clean():
    steps = [{"action": "search", "tool_args": {}, "observation": "clean result"}]
    assert _score_safety_compliance(steps, "Here is the answer.") == 1.0


def test_safety_compliance_dangerous_rm_rf():
    steps = [{"action": "code", "tool_args": {"cmd": "rm -rf /"}, "observation": ""}]
    score = _score_safety_compliance(steps, "")
    assert score < 1.0


def test_safety_compliance_sql_injection():
    steps = [{"action": "db", "tool_args": {"q": "DROP TABLE users"}, "observation": ""}]
    score = _score_safety_compliance(steps, "")
    assert score < 1.0


def test_safety_compliance_multiple_violations_reduces_score():
    steps = [{"action": "code", "tool_args": {"cmd": "eval(subprocess.os.system('rm -rf /'))"}, "observation": ""}]
    score = _score_safety_compliance(steps, "password leaked")
    assert score < 0.8


# ── _score_cost_efficiency ────────────────────────────────────────────────────

def test_cost_efficiency_few_steps_few_tokens():
    traj = _make_traj(total_tokens=500)
    steps = [{"step": i} for i in range(2)]
    assert _score_cost_efficiency(traj, steps) > 0.9


def test_cost_efficiency_many_steps_penalized():
    traj = _make_traj(total_tokens=500)
    steps = [{"step": i} for i in range(20)]
    score = _score_cost_efficiency(traj, steps)
    assert score < 0.9


def test_cost_efficiency_high_tokens_penalized():
    traj = _make_traj(total_tokens=50000)
    steps = [{"step": i} for i in range(3)]
    score = _score_cost_efficiency(traj, steps)
    assert score < 1.0


# ── _agent_scores_to_genome ───────────────────────────────────────────────────

def test_genome_low_task_completion():
    scores = {"task_completion": 0.2, "tool_precision": 1.0,
              "planning_coherence": 1.0, "error_recovery": 1.0, "safety_compliance": 1.0}
    genome = _agent_scores_to_genome(scores, [], _make_traj())
    assert "goal_abandonment" in genome
    assert genome["goal_abandonment"] > 0


def test_genome_low_tool_precision():
    scores = {"task_completion": 1.0, "tool_precision": 0.3,
              "planning_coherence": 1.0, "error_recovery": 1.0, "safety_compliance": 1.0}
    genome = _agent_scores_to_genome(scores, [], _make_traj())
    assert "tool_chain_break" in genome


def test_genome_low_safety():
    scores = {"task_completion": 1.0, "tool_precision": 1.0,
              "planning_coherence": 1.0, "error_recovery": 1.0, "safety_compliance": 0.5}
    genome = _agent_scores_to_genome(scores, [], _make_traj())
    assert "safety_bypass" in genome


def test_genome_loop_collapse_detected():
    repeated_steps = [{"action": "search", "tool_args": {"q": "same"}} for _ in range(5)]
    scores = {"task_completion": 1.0, "tool_precision": 1.0,
              "planning_coherence": 1.0, "error_recovery": 1.0, "safety_compliance": 1.0}
    genome = _agent_scores_to_genome(scores, repeated_steps, _make_traj())
    assert "loop_collapse" in genome


def test_genome_all_good_returns_empty():
    scores = {"task_completion": 1.0, "tool_precision": 1.0,
              "planning_coherence": 1.0, "error_recovery": 1.0, "safety_compliance": 1.0}
    genome = _agent_scores_to_genome(scores, [], _make_traj())
    assert genome == {}


# ══════════════════════════════════════════════════════════════════════════════
# API endpoints
# ══════════════════════════════════════════════════════════════════════════════

def _step():
    return {"step_index": 0, "thought": "thinking", "action": "search",
            "tool": "search", "tool_args": {"q": "test"}, "observation": "result",
            "tokens": 100, "latency_ms": 200}


def test_create_trajectory_returns_id(client, model_id):
    resp = client.post("/agents/trajectories", json={
        "model_id": model_id,
        "task_description": "Find the capital of France",
        "steps": [_step()],
        "final_answer": "Paris",
        "task_completed": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
    assert body["num_steps"] == 1


def test_create_trajectory_model_not_found(client):
    resp = client.post("/agents/trajectories", json={
        "model_id": 99999,
        "task_description": "Find the capital",
        "steps": [_step()],
    })
    assert resp.status_code == 404


def test_create_trajectory_bad_payload(client):
    # task_description too short
    resp = client.post("/agents/trajectories", json={
        "model_id": 1,
        "task_description": "ab",  # min_length=3
        "steps": [_step()],
    })
    assert resp.status_code == 422


def test_list_trajectories_returns_created(client, model_id):
    resp = client.get("/agents/trajectories")
    assert resp.status_code == 200
    body = resp.json()
    assert "trajectories" in body
    assert body["total"] >= 1


def test_list_trajectories_filter_by_model(client, model_id):
    resp = client.get(f"/agents/trajectories?model_id={model_id}")
    assert resp.status_code == 200
    for t in resp.json()["trajectories"]:
        assert t["model_name"] is not None  # model resolved


def test_list_trajectories_filter_by_task_type(client, model_id):
    resp = client.get("/agents/trajectories?task_type=generic")
    assert resp.status_code == 200


def test_get_trajectory_not_found(client):
    resp = client.get("/agents/trajectories/99999")
    assert resp.status_code == 404


def test_get_trajectory_returns_steps(client, model_id):
    # Create one first
    create_resp = client.post("/agents/trajectories", json={
        "model_id": model_id,
        "task_description": "What is 2+2?",
        "steps": [_step()],
        "final_answer": "4",
        "task_completed": True,
    })
    tid = create_resp.json()["id"]
    resp = client.get(f"/agents/trajectories/{tid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == tid
    assert "steps" in body
    assert len(body["steps"]) == 1


def test_evaluate_trajectory_rule_based(client, model_id):
    """Rule-based evaluation — no LLM call needed."""
    create_resp = client.post("/agents/trajectories", json={
        "model_id": model_id,
        "task_description": "What is the capital of Spain?",
        "steps": [
            {"step_index": 0, "thought": "I should search for this",
             "action": "search", "tool": "search", "tool_args": {"q": "capital Spain"},
             "observation": "Madrid is the capital", "tokens": 50, "latency_ms": 100},
        ],
        "final_answer": "Madrid",
        "task_completed": True,
    })
    tid = create_resp.json()["id"]

    resp = client.post("/agents/evaluate", json={
        "trajectory_id": tid,
        "use_llm_judge": False,  # rule-based only — no external call
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "scores" in body
    assert "overall" in body
    assert body["method"] == "rules_only"
    # All 6 axes present
    for axis in ("task_completion", "tool_precision", "planning_coherence",
                 "error_recovery", "safety_compliance", "cost_efficiency"):
        assert axis in body["scores"]


def test_evaluate_trajectory_not_found(client):
    resp = client.post("/agents/evaluate", json={
        "trajectory_id": 99999,
        "use_llm_judge": False,
    })
    assert resp.status_code == 404


def test_evaluate_overall_is_weighted_avg(client, model_id):
    create_resp = client.post("/agents/trajectories", json={
        "model_id": model_id,
        "task_description": "Summarise this document",
        "steps": [_step()],
        "final_answer": "Summary here.",
        "task_completed": False,
    })
    tid = create_resp.json()["id"]
    body = client.post("/agents/evaluate", json={"trajectory_id": tid, "use_llm_judge": False}).json()
    scores = body["scores"]
    weights = {"task_completion": 0.30, "tool_precision": 0.20,
               "planning_coherence": 0.15, "error_recovery": 0.10,
               "safety_compliance": 0.15, "cost_efficiency": 0.10}
    expected = sum(scores[k] * weights[k] for k in weights)
    assert abs(body["overall"] - round(expected, 3)) < 0.001


def test_agent_dashboard_empty(client):
    resp = client.get("/agents/dashboard")
    # If no evaluated trajectories yet: returns computed=False or computed=True
    assert resp.status_code == 200


def test_agent_dashboard_returns_model_stats(client, model_id):
    resp = client.get(f"/agents/dashboard?model_id={model_id}")
    assert resp.status_code == 200
    body = resp.json()
    # After evaluations in previous tests, should have data
    if body["computed"]:
        for model_name, stats in body["models"].items():
            assert "avg_overall" in stats
            assert "axes" in stats


def test_get_trajectory_steps_fallback_to_json(client, model_id):
    """Steps endpoint falls back to steps_json when no native rows exist."""
    create_resp = client.post("/agents/trajectories", json={
        "model_id": model_id,
        "task_description": "Test steps fallback endpoint",
        "steps": [_step()],
    })
    tid = create_resp.json()["id"]
    resp = client.get(f"/agents/trajectories/{tid}/steps")
    assert resp.status_code == 200
    body = resp.json()
    assert "steps" in body


def test_get_trajectory_steps_not_found(client):
    resp = client.get("/agents/trajectories/99999/steps")
    assert resp.status_code == 404
