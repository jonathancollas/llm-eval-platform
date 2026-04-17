from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class SubGoal:
    sub_goal_id: str
    description: str
    required_for_completion: bool = True
    max_steps: int = 3
    success_criteria: list = field(default_factory=list)
    partial_credit_weight: float = 1.0
    dependencies: list = field(default_factory=list)


@dataclass
class LongHorizonTask:
    task_id: str
    name: str
    domain: str
    description: str
    main_goal: str
    sub_goals: list
    max_total_steps: int = 15
    token_budget: int = 8000
    difficulty: str = "medium"
    capability_tags: list = field(default_factory=list)
    success_threshold: float = 0.7
    context_documents: list = field(default_factory=list)
    evaluation_rubric: dict = field(default_factory=dict)


@dataclass
class SubGoalResult:
    sub_goal_id: str
    completed: bool
    partial_credit: float
    steps_taken: int
    tokens_used: int
    recovery_occurred: bool = False
    evidence: str = ""


@dataclass
class LongHorizonResult:
    task_id: str
    model_name: str
    main_goal_achieved: bool
    sub_goal_results: list
    completion_rate: float
    partial_credit_score: float
    recovery_rate: float
    total_steps: int
    total_tokens: int
    total_cost_usd: float
    within_budget: bool
    efficiency_ratio: float
    frontier_metrics: dict
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


LONG_HORIZON_TASKS = [
    {
        "task_id": "data_analysis_pipeline",
        "name": "Multi-Step Data Analysis",
        "domain": "data_analysis",
        "description": "Analyze a dataset through multiple stages",
        "main_goal": "Extract insights and produce summary report",
        "max_total_steps": 12,
        "token_budget": 6000,
        "difficulty": "medium",
        "capability_tags": ["reasoning", "instruction_following"],
        "success_threshold": 0.7,
        "context_documents": [
            {"title": "Sales Data", "content": "Q1: $1.2M, Q2: $1.5M, Q3: $1.1M, Q4: $1.8M"}
        ],
        "evaluation_rubric": {"completeness": 0.4, "accuracy": 0.4, "clarity": 0.2},
        "sub_goals": [
            {
                "sub_goal_id": "load_data",
                "description": "Parse the data",
                "required_for_completion": True,
                "max_steps": 2,
                "success_criteria": ["Q1", "Q2", "Q3", "Q4"],
                "partial_credit_weight": 0.2,
            },
            {
                "sub_goal_id": "compute_stats",
                "description": "Compute statistics",
                "required_for_completion": True,
                "max_steps": 3,
                "success_criteria": ["total", "average", "sum"],
                "partial_credit_weight": 0.3,
            },
            {
                "sub_goal_id": "identify_trend",
                "description": "Identify trend",
                "required_for_completion": True,
                "max_steps": 2,
                "success_criteria": ["growth", "increase", "trend"],
                "partial_credit_weight": 0.3,
            },
            {
                "sub_goal_id": "write_summary",
                "description": "Write summary",
                "required_for_completion": False,
                "max_steps": 3,
                "success_criteria": ["summary", "report"],
                "partial_credit_weight": 0.2,
            },
        ],
    },
    {
        "task_id": "code_review_comprehensive",
        "name": "Comprehensive Code Review",
        "domain": "code_review",
        "description": "Review code for bugs and security issues",
        "main_goal": "Produce a detailed code review",
        "max_total_steps": 10,
        "token_budget": 5000,
        "difficulty": "hard",
        "capability_tags": ["reasoning", "knowledge"],
        "success_threshold": 0.6,
        "context_documents": [
            {
                "title": "Code",
                "content": "def login(user, pwd): return db.query(f'SELECT * FROM users WHERE user={user}')",
            }
        ],
        "evaluation_rubric": {"bug_detection": 0.5, "security": 0.3, "style": 0.2},
        "sub_goals": [
            {
                "sub_goal_id": "identify_sql_injection",
                "description": "Identify SQL injection",
                "required_for_completion": True,
                "max_steps": 2,
                "success_criteria": ["sql injection", "injection"],
                "partial_credit_weight": 0.5,
            },
            {
                "sub_goal_id": "suggest_fix",
                "description": "Suggest parameterized queries",
                "required_for_completion": True,
                "max_steps": 2,
                "success_criteria": ["parameterized", "prepared statement", "placeholder"],
                "partial_credit_weight": 0.3,
            },
            {
                "sub_goal_id": "check_style",
                "description": "Comment on style",
                "required_for_completion": False,
                "max_steps": 2,
                "success_criteria": ["style", "naming", "format"],
                "partial_credit_weight": 0.2,
            },
        ],
    },
    {
        "task_id": "research_synthesis",
        "name": "Research Synthesis",
        "domain": "research_synthesis",
        "description": "Synthesize findings from multiple sources",
        "main_goal": "Write a coherent synthesis",
        "max_total_steps": 10,
        "token_budget": 7000,
        "difficulty": "hard",
        "capability_tags": ["reasoning", "knowledge", "instruction_following"],
        "success_threshold": 0.7,
        "context_documents": [
            {"title": "Paper A", "content": "LLMs achieve 85% on MMLU with 70B parameters"},
            {"title": "Paper B", "content": "Safety alignment reduces capability by 2-5%"},
        ],
        "evaluation_rubric": {"accuracy": 0.5, "coherence": 0.3, "completeness": 0.2},
        "sub_goals": [
            {
                "sub_goal_id": "extract_findings",
                "description": "Extract key findings",
                "required_for_completion": True,
                "max_steps": 3,
                "success_criteria": ["85%", "70B", "safety"],
                "partial_credit_weight": 0.4,
            },
            {
                "sub_goal_id": "identify_tension",
                "description": "Note capability-safety tradeoff",
                "required_for_completion": True,
                "max_steps": 2,
                "success_criteria": ["tradeoff", "tension", "reduces"],
                "partial_credit_weight": 0.4,
            },
            {
                "sub_goal_id": "write_synthesis",
                "description": "Write synthesis",
                "required_for_completion": False,
                "max_steps": 3,
                "success_criteria": ["therefore", "suggest", "conclude", "overall"],
                "partial_credit_weight": 0.2,
            },
        ],
    },
    {
        "task_id": "system_design_iterative",
        "name": "Iterative System Design",
        "domain": "system_design",
        "description": "Design a rate-limiting system",
        "main_goal": "Design a rate-limiting system for an API",
        "max_total_steps": 15,
        "token_budget": 8000,
        "difficulty": "expert",
        "capability_tags": ["reasoning", "agentic"],
        "success_threshold": 0.6,
        "context_documents": [
            {
                "title": "Requirements",
                "content": "API receives 10k req/s, max 100 req/s per user, SLA 99.9%",
            }
        ],
        "evaluation_rubric": {"feasibility": 0.4, "completeness": 0.4, "scalability": 0.2},
        "sub_goals": [
            {
                "sub_goal_id": "identify_approach",
                "description": "Choose rate-limiting algorithm",
                "required_for_completion": True,
                "max_steps": 2,
                "success_criteria": [
                    "token bucket",
                    "sliding window",
                    "leaky bucket",
                    "fixed window",
                ],
                "partial_credit_weight": 0.3,
            },
            {
                "sub_goal_id": "storage_design",
                "description": "Design storage layer",
                "required_for_completion": True,
                "max_steps": 3,
                "success_criteria": ["redis", "cache", "memory", "counter"],
                "partial_credit_weight": 0.3,
            },
            {
                "sub_goal_id": "handle_edge_cases",
                "description": "Address edge cases",
                "required_for_completion": False,
                "max_steps": 3,
                "success_criteria": [
                    "failover",
                    "fallback",
                    "race condition",
                    "distributed",
                ],
                "partial_credit_weight": 0.2,
            },
            {
                "sub_goal_id": "sla_analysis",
                "description": "Analyze SLA feasibility",
                "required_for_completion": False,
                "max_steps": 3,
                "success_criteria": ["99.9", "downtime", "availability"],
                "partial_credit_weight": 0.2,
            },
        ],
    },
    {
        "task_id": "debugging_complex",
        "name": "Complex Multi-Component Debugging",
        "domain": "debugging_complex",
        "description": "Debug a system with multiple interacting components",
        "main_goal": "Identify root cause of system failure",
        "max_total_steps": 12,
        "token_budget": 6000,
        "difficulty": "expert",
        "capability_tags": ["reasoning", "knowledge"],
        "success_threshold": 0.7,
        "context_documents": [
            {
                "title": "Error Log",
                "content": "DB timeout at 30s -> cache miss spike -> memory OOM -> service restart loop",
            }
        ],
        "evaluation_rubric": {"root_cause": 0.5, "causal_chain": 0.3, "fix": 0.2},
        "sub_goals": [
            {
                "sub_goal_id": "identify_root_cause",
                "description": "Identify root cause",
                "required_for_completion": True,
                "max_steps": 3,
                "success_criteria": ["database", "DB", "timeout", "query"],
                "partial_credit_weight": 0.4,
            },
            {
                "sub_goal_id": "trace_causal_chain",
                "description": "Trace causal chain",
                "required_for_completion": True,
                "max_steps": 3,
                "success_criteria": ["cache", "memory", "OOM", "restart"],
                "partial_credit_weight": 0.3,
            },
            {
                "sub_goal_id": "propose_fix",
                "description": "Propose fix",
                "required_for_completion": False,
                "max_steps": 3,
                "success_criteria": ["index", "query", "optimize", "timeout"],
                "partial_credit_weight": 0.3,
            },
        ],
    },
]


class LongHorizonEvaluator:
    def load_task(self, d):
        sub_goals = [SubGoal(**sg) for sg in d.get("sub_goals", [])]
        kw = {k: v for k, v in d.items() if k != "sub_goals"}
        return LongHorizonTask(**kw, sub_goals=sub_goals)

    def list_tasks(self, domain=None):
        if domain:
            return [t for t in LONG_HORIZON_TASKS if t["domain"] == domain]
        return LONG_HORIZON_TASKS

    def evaluate_sub_goal(self, sub_goal, agent_response, context):
        text = (
            agent_response.get("text", "")
            + " "
            + agent_response.get("reasoning", "")
            + " "
            + agent_response.get("evidence", "")
        ).lower()
        completed = any(c.lower() in text for c in sub_goal.success_criteria)
        credit = sub_goal.partial_credit_weight if completed else 0.0
        return SubGoalResult(
            sub_goal_id=sub_goal.sub_goal_id,
            completed=completed,
            partial_credit=credit,
            steps_taken=1,
            tokens_used=agent_response.get("tokens", 0),
        )

    def simulate_run(self, task, step_responses, seed=42):
        sub_goal_results = []
        total_tokens = 0
        for i, sg in enumerate(task.sub_goals):
            resp = step_responses[i] if i < len(step_responses) else {}
            result = self.evaluate_sub_goal(sg, resp, {})
            total_tokens += resp.get("tokens", 0)
            sub_goal_results.append(result)
        completed = sum(1 for r in sub_goal_results if r.completed)
        completion_rate = round(completed / max(len(sub_goal_results), 1), 4)
        partial_credit = self.compute_partial_credit(sub_goal_results)
        recovery_rate = self.compute_recovery_rate(sub_goal_results)
        total_steps = len(step_responses)
        main_achieved = completion_rate >= task.success_threshold
        return LongHorizonResult(
            task_id=task.task_id,
            model_name="simulated",
            main_goal_achieved=main_achieved,
            sub_goal_results=sub_goal_results,
            completion_rate=completion_rate,
            partial_credit_score=partial_credit,
            recovery_rate=recovery_rate,
            total_steps=total_steps,
            total_tokens=total_tokens,
            total_cost_usd=0.0,
            within_budget=total_tokens <= task.token_budget,
            efficiency_ratio=round(
                partial_credit
                / max(total_steps / max(task.max_total_steps, 1), 0.01),
                4,
            ),
            frontier_metrics={
                "autonomy": 1.0
                - sum(1 for r in sub_goal_results if not r.completed)
                / max(len(sub_goal_results), 1),
                "adaptivity": recovery_rate,
                "efficiency": 1 - total_steps / max(task.max_total_steps, 1),
            },
        )

    def compute_partial_credit(self, sub_goal_results):
        if not sub_goal_results:
            return 0.0
        return round(sum(r.partial_credit for r in sub_goal_results) / len(sub_goal_results), 4)

    def compute_recovery_rate(self, sub_goal_results):
        failures = sum(1 for r in sub_goal_results if not r.completed)
        if failures == 0:
            return 1.0
        recoveries = sum(1 for r in sub_goal_results if r.recovery_occurred)
        return round(recoveries / failures, 4)
