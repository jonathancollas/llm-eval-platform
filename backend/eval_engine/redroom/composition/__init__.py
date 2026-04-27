"""D7 — Compositional attack harness.

Tests deployed agentic stacks rather than single models. A stack here is
a set of named components — model, retriever, tool router, memory store —
each exposed as an async callable. An attack plan is a DAG of steps,
each targeting one component with a structured payload.

The harness:
  - validates the plan against the stack (every named component exists)
  - runs steps sequentially with a hard wall-clock budget
  - collects per-step outcomes (matched success predicate or not)
  - declares a system-level breach when ``min_consecutive_successes``
    in a row are reached, or when a marked critical step fires.

Aggressiveness: L5.
"""
from eval_engine.redroom.composition.harness import (
    AgentStack,
    AttackPlan,
    AttackStep,
    CompositionResult,
    StepOutcome,
    run_compositional_attack,
)

__all__ = [
    "AgentStack",
    "AttackPlan",
    "AttackStep",
    "CompositionResult",
    "StepOutcome",
    "run_compositional_attack",
]
