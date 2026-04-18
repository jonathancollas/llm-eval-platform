"""Scenario Runtime Engine — multi-step stateful evaluation scenarios."""
from __future__ import annotations
import os
import re
import random
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional

try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:  # pragma: no cover
    _YAML_AVAILABLE = False


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
    # Conditional branching: optional step_id to jump to on success/failure
    next_step_if_success: Optional[str] = None
    next_step_if_fail: Optional[str] = None
    # Condition expression evaluated against current state (e.g. "tool_used == 'search'")
    condition: Optional[str] = None


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
    failure_criteria: list = field(default_factory=list)
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
        "failure_criteria": ["incorrect_year"],
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
                "next_step_if_success": "compute_answer",
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
    {
        "name": "multi_turn_qa",
        "description": "Answer a sequence of follow-up questions using context from prior turns",
        "goal": "Correctly answer all questions while retaining session context",
        "initial_state": {
            "topic": "solar system",
            "turn": 1,
        },
        "max_steps": 4,
        "timeout_seconds": 90,
        "success_criteria": ["all_questions_answered"],
        "failure_criteria": ["context_lost"],
        "domain": "conversational",
        "difficulty": "medium",
        "capability_tags": ["context_retention", "instruction_following"],
        "steps": [
            {
                "step_id": "initial_question",
                "description": "Answer: How many planets are in the solar system?",
                "expected_action_type": "answer",
                "success_condition": "contains_keyword",
                "keywords": ["8", "eight"],
                "partial_credit": 0.25,
            },
            {
                "step_id": "follow_up_largest",
                "description": "Answer follow-up: Which is the largest?",
                "expected_action_type": "answer",
                "success_condition": "contains_keyword",
                "keywords": ["jupiter"],
                "partial_credit": 0.25,
            },
            {
                "step_id": "follow_up_moons",
                "description": "Answer: How many moons does it have?",
                "expected_action_type": "answer",
                "success_condition": "contains_keyword",
                "keywords": ["95", "moons", "moon"],
                "partial_credit": 0.25,
            },
            {
                "step_id": "follow_up_distance",
                "description": "Answer: How far is it from the Sun?",
                "expected_action_type": "answer",
                "success_condition": "contains_keyword",
                "keywords": ["778", "million", "km", "au", "5.2"],
                "partial_credit": 0.25,
            },
        ],
    },
    {
        "name": "tool_use",
        "description": "Use available tools to answer a factual question",
        "goal": "Retrieve current weather data for a city using the search tool",
        "initial_state": {
            "city": "Paris",
            "available_tools": ["search", "calculator", "code_interpreter"],
        },
        "max_steps": 3,
        "timeout_seconds": 60,
        "success_criteria": ["tool_invoked", "answer_provided"],
        "failure_criteria": ["hallucinated_without_tool"],
        "domain": "tool_use",
        "difficulty": "easy",
        "capability_tags": ["tool_use", "instruction_following"],
        "steps": [
            {
                "step_id": "select_tool",
                "description": "Select the appropriate tool for weather lookup",
                "expected_action_type": "tool",
                "expected_tool": "search",
                "success_condition": "tool_called",
                "partial_credit": 0.4,
            },
            {
                "step_id": "formulate_query",
                "description": "Formulate a weather query for Paris",
                "expected_action_type": "reasoning",
                "success_condition": "contains_keyword",
                "keywords": ["paris", "weather", "temperature"],
                "partial_credit": 0.3,
            },
            {
                "step_id": "provide_answer",
                "description": "Provide the weather answer based on tool result",
                "expected_action_type": "answer",
                "success_condition": "contains_keyword",
                "keywords": ["paris", "degrees", "celsius", "fahrenheit", "weather"],
                "partial_credit": 0.3,
            },
        ],
    },
]


def _inject_env_vars(value: str, env: Optional[dict] = None) -> str:
    """Replace ${VAR} placeholders with values from *env* or os.environ."""
    if not isinstance(value, str):
        return value
    context = dict(os.environ)
    if env:
        context.update(env)

    def _replace(match: re.Match) -> str:
        return context.get(match.group(1), match.group(0))

    # Use a precise character class for valid env-var names to avoid ReDoS.
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", _replace, value)


def _inject_env_vars_deep(obj, env: Optional[dict] = None):
    """Recursively inject env vars into all string values of a dict/list."""
    if isinstance(obj, str):
        return _inject_env_vars(obj, env)
    if isinstance(obj, dict):
        return {k: _inject_env_vars_deep(v, env) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_inject_env_vars_deep(item, env) for item in obj]
    return obj


def load_scenario(d: dict, env: Optional[dict] = None) -> "Scenario":
    d = _inject_env_vars_deep(d, env)
    _STEP_FIELDS = {f.name for f in ScenarioStep.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    steps = [ScenarioStep(**{k: v for k, v in s.items() if k in _STEP_FIELDS})
             for s in d.get("steps", [])]
    _SCENARIO_FIELDS = {f.name for f in Scenario.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    kw = {k: v for k, v in d.items() if k != "steps" and k in _SCENARIO_FIELDS}
    return Scenario(**kw, steps=steps)


def load_scenario_from_yaml(yaml_str: str, env: Optional[dict] = None) -> "Scenario":
    """Parse a YAML string and return a :class:`Scenario`."""
    if not _YAML_AVAILABLE:
        raise ImportError("PyYAML is required to load YAML scenarios. Install it with: pip install pyyaml")
    data = _yaml.safe_load(yaml_str)
    return load_scenario(data, env=env)


def load_scenario_from_file(path: str, env: Optional[dict] = None) -> "Scenario":
    """Load a :class:`Scenario` from a YAML file on disk."""
    with open(path, "r", encoding="utf-8") as fh:
        return load_scenario_from_yaml(fh.read(), env=env)


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
    step_ids = [step.step_id for step in s.steps]
    for step in s.steps:
        if step.next_step_if_success and step.next_step_if_success not in step_ids:
            errors.append(
                f"step '{step.step_id}' next_step_if_success references unknown step_id "
                f"'{step.next_step_if_success}'"
            )
        if step.next_step_if_fail and step.next_step_if_fail not in step_ids:
            errors.append(
                f"step '{step.step_id}' next_step_if_fail references unknown step_id "
                f"'{step.next_step_if_fail}'"
            )
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
        random.seed(seed)

    def load_scenario(self, d: dict, env: Optional[dict] = None) -> Scenario:
        return load_scenario(d, env=env)

    def load_scenario_from_yaml(self, yaml_str: str, env: Optional[dict] = None) -> Scenario:
        return load_scenario_from_yaml(yaml_str, env=env)

    def load_scenario_from_file(self, path: str, env: Optional[dict] = None) -> Scenario:
        return load_scenario_from_file(path, env=env)

    def list_example_scenarios(self) -> list:
        return EXAMPLE_SCENARIOS

    def simulate_run(self, scenario: Scenario, model_responses: list,
                     model_name: str = "test") -> ScenarioRunResult:
        """Execute scenario steps, honouring conditional branching.

        *model_responses* is consumed in order — one dict per step executed.
        Branching (``next_step_if_success`` / ``next_step_if_fail``) can skip
        or reorder steps; the run always terminates after ``scenario.max_steps``
        steps have been attempted.
        """
        step_index_by_id = {s.step_id: s for s in scenario.steps}
        response_iter = iter(model_responses)

        # Start from the first step
        current_step = scenario.steps[0] if scenario.steps else None
        step_results: list[StepExecutionResult] = []
        steps_attempted = 0

        while current_step is not None and steps_attempted < scenario.max_steps:
            resp = next(response_iter, {})
            success, credit = evaluate_step(current_step, resp, scenario.initial_state)
            step_results.append(StepExecutionResult(
                step_id=current_step.step_id,
                step_index=steps_attempted,
                agent_action=resp.get("action", ""),
                agent_reasoning=resp.get("reasoning", ""),
                agent_tool=resp.get("tool", ""),
                success=success,
                partial_credit_earned=credit,
                tokens_used=resp.get("tokens", 0),
            ))
            steps_attempted += 1

            # Determine next step via conditional branching or linear order
            next_id = current_step.next_step_if_success if success else current_step.next_step_if_fail
            if next_id:
                current_step = step_index_by_id.get(next_id)
            else:
                # Linear: advance to next step in the original list
                idx = next(
                    (i for i, s in enumerate(scenario.steps) if s.step_id == current_step.step_id),
                    None,
                )
                if idx is not None and idx + 1 < len(scenario.steps):
                    current_step = scenario.steps[idx + 1]
                else:
                    current_step = None

        succeeded = sum(1 for r in step_results if r.success)
        total = len(step_results)
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
