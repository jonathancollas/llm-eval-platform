"""Scenario Runtime Engine — multi-step stateful evaluation scenarios."""
from __future__ import annotations
import random
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional


@dataclass
class ScenarioStep:
    step_id: str
    description: str
    expected_action_type: str
    expected_tool: Optional[str] = None
    success_condition: str = "contains_keyword"
    keywords: list = field(default_factory=list)
    partial_credit: float = 1.0
    hints: list = field(default_factory=list)


@dataclass
class Scenario:
    name: str
    description: str
    goal: str
    initial_state: dict
    max_steps: int
    timeout_seconds: int
    success_criteria: list
    steps: list
    domain: str = ""
    difficulty: str = "medium"
    capability_tags: list = field(default_factory=list)
    version: str = "1.0.0"
    author: str = ""


@dataclass
class StepExecutionResult:
    step_id: str
    step_index: int
    agent_action: str
    agent_reasoning: str
    agent_tool: str
    success: bool
    partial_credit_earned: float
    latency_ms: int = 0
    tokens_used: int = 0
    error: Optional[str] = None


@dataclass
class ScenarioRunResult:
    scenario_name: str
    goal: str
    model_name: str
    n_steps_executed: int
    max_steps: int
    overall_success: bool
    completion_rate: float
    partial_credit_score: float
    autonomy_score: float
    efficiency_score: float
    total_tokens: int
    total_cost_usd: float
    total_latency_ms: int
    step_results: list
    failure_modes: list
    seed: int
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


EXAMPLE_SCENARIOS = [
    {
        "name": "data_extraction",
        "description": "Extract structured data",
        "goal": "Extract all numerical values and their labels",
        "initial_state": {
            "document": "Revenue: $1.2M, Users: 45000, Growth: 23%, Churn: 2.1%"
        },
        "max_steps": 5,
        "timeout_seconds": 60,
        "success_criteria": ["all_values_extracted"],
        "domain": "data_analysis",
        "difficulty": "easy",
        "capability_tags": ["instruction_following"],
        "steps": [
            {
                "step_id": "identify_values",
                "description": "Identify numerical values",
                "expected_action_type": "reasoning",
                "success_condition": "contains_keyword",
                "keywords": ["revenue", "users", "growth", "churn"],
                "partial_credit": 0.4,
            },
            {
                "step_id": "extract_labels",
                "description": "Associate labels with values",
                "expected_action_type": "answer",
                "success_condition": "contains_keyword",
                "keywords": ["1.2", "45000", "23", "2.1"],
                "partial_credit": 0.6,
            },
        ],
    },
    {
        "name": "code_debugging",
        "description": "Identify a bug in pseudocode",
        "goal": "Find the off-by-one error",
        "initial_state": {"code": "for i in range(1, n): sum += arr[i]"},
        "max_steps": 4,
        "timeout_seconds": 60,
        "success_criteria": ["bug_identified"],
        "domain": "coding",
        "difficulty": "medium",
        "capability_tags": ["reasoning"],
        "steps": [
            {
                "step_id": "identify_bug",
                "description": "Identify the bug",
                "expected_action_type": "reasoning",
                "success_condition": "contains_keyword",
                "keywords": ["off-by-one", "index", "range", "0"],
                "partial_credit": 0.5,
            },
            {
                "step_id": "describe_fix",
                "description": "Describe the fix",
                "expected_action_type": "answer",
                "success_condition": "contains_keyword",
                "keywords": ["range(0", "range(n", "start"],
                "partial_credit": 0.5,
            },
        ],
    },
    {
        "name": "information_synthesis",
        "description": "Synthesize from multiple sources",
        "goal": "Combine facts to answer the question",
        "initial_state": {
            "fact1": "Mercury was founded in 2024",
            "fact2": "It is now 2026",
            "question": "How old is Mercury?",
        },
        "max_steps": 3,
        "timeout_seconds": 45,
        "success_criteria": ["correct_answer"],
        "domain": "reasoning",
        "difficulty": "easy",
        "capability_tags": ["reasoning"],
        "steps": [
            {
                "step_id": "recall_facts",
                "description": "Recall relevant facts",
                "expected_action_type": "reasoning",
                "success_condition": "contains_keyword",
                "keywords": ["2024", "2026"],
                "partial_credit": 0.4,
            },
            {
                "step_id": "compute_answer",
                "description": "Compute the answer",
                "expected_action_type": "answer",
                "success_condition": "contains_keyword",
                "keywords": ["2", "two", "years"],
                "partial_credit": 0.6,
            },
        ],
    },
]


def load_scenario(d: dict) -> Scenario:
    steps = [ScenarioStep(**s) for s in d.get("steps", [])]
    kw = {k: v for k, v in d.items() if k != "steps"}
    return Scenario(**kw, steps=steps)


def validate_scenario(s: Scenario) -> list:
    errors = []
    if not s.name:
        errors.append("name is required")
    if not s.goal:
        errors.append("goal is required")
    if s.max_steps < 1:
        errors.append("max_steps must be >= 1")
    if not s.steps:
        errors.append("at least one step required")
    return errors


def evaluate_step(step: ScenarioStep, response: dict, state: dict) -> tuple:
    text = (
        response.get("text", "") + " "
        + response.get("answer", "") + " "
        + response.get("reasoning", "")
    ).lower()

    if step.success_condition == "contains_keyword":
        if step.keywords and any(kw.lower() in text for kw in step.keywords):
            return True, step.partial_credit
        return False, 0.0
    elif step.success_condition == "tool_called":
        matched = response.get("tool") == step.expected_tool
        return matched, step.partial_credit if matched else 0.0
    elif step.success_condition == "any":
        return True, step.partial_credit
    else:
        expected = step.keywords[0].lower() if step.keywords else ""
        matched = bool(expected and expected in text)
        return matched, step.partial_credit if matched else 0.0


class ScenarioRuntime:
    def __init__(self, seed: int = 42):
        self.seed = seed

    def load_scenario(self, d: dict) -> Scenario:
        return load_scenario(d)

    def list_example_scenarios(self) -> list:
        return EXAMPLE_SCENARIOS

    def simulate_run(self, scenario: Scenario, model_responses: list,
                     model_name: str = "test") -> ScenarioRunResult:
        step_results = []
        for i, step in enumerate(scenario.steps):
            resp = model_responses[i] if i < len(model_responses) else {}
            success, credit = evaluate_step(step, resp, scenario.initial_state)
            step_results.append(StepExecutionResult(
                step_id=step.step_id, step_index=i,
                agent_action=resp.get("action", ""),
                agent_reasoning=resp.get("reasoning", ""),
                agent_tool=resp.get("tool", ""),
                success=success, partial_credit_earned=credit,
                tokens_used=resp.get("tokens", 0),
            ))
        succeeded = sum(1 for r in step_results if r.success)
        total = len(scenario.steps)
        completion_rate = round(succeeded / max(total, 1), 4)
        total_credit = sum(r.partial_credit_earned for r in step_results)
        max_credit = sum(s.partial_credit for s in scenario.steps)
        pcs = round(total_credit / max(max_credit, 1), 4)
        autonomy = round(1 - sum(1 for r in step_results if not r.success) / max(len(step_results), 1), 4)
        efficiency = max(0.0, round(1 - len(step_results) / max(scenario.max_steps, 1), 4))
        return ScenarioRunResult(
            scenario_name=scenario.name, goal=scenario.goal, model_name=model_name,
            n_steps_executed=len(step_results), max_steps=scenario.max_steps,
            overall_success=completion_rate >= 0.5, completion_rate=completion_rate,
            partial_credit_score=pcs, autonomy_score=autonomy, efficiency_score=efficiency,
            total_tokens=sum(r.tokens_used for r in step_results), total_cost_usd=0.0,
            total_latency_ms=0, step_results=step_results,
            failure_modes=[r.step_id for r in step_results if not r.success],
            seed=self.seed,
        )

    def evaluate_partial_credit(self, step_results: list) -> float:
        if not step_results:
            return 0.0
        return round(sum(r.partial_credit_earned for r in step_results) / len(step_results), 4)

    def classify_failures(self, step_results: list) -> list:
        return [f"step_{r.step_id}_failed" for r in step_results if not r.success]
