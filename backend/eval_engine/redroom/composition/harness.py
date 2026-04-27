"""
Compositional attack harness.

Treats an agentic system as a graph of named components:

    {
        "model":     async (str) -> str,
        "retriever": async (str) -> list[str],
        "tool":      async (str) -> str,
        "memory":    async (str) -> str,
        ...
    }

An AttackPlan is a list of AttackSteps, each with:
  - target_component:  one of the keys in the stack
  - input_template:    str template that may reference prior step outputs
  - success_predicate: a callable (output_str) -> bool. The step
                       "succeeded" when this returns True.
  - critical:          if True, a single success of this step alone
                       constitutes a system breach.

The harness runs steps in order. Inter-step data flow is supported via a
``$step_N`` placeholder in input_template (replaced with the prior
step's output).

A breach is declared if:
  - a critical step succeeds, OR
  - ``min_consecutive_successes`` non-critical steps succeed in a row.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
import time
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
#  Types
# ────────────────────────────────────────────────────────────────────


# Each component is a callable input → output. Output is normalized to
# str; lists/dicts are JSON-serialised before being passed to the next
# step's success predicate.
ComponentCallable = Callable[[str], Awaitable[object]]
SuccessPredicate = Callable[[str], bool]


@dataclasses.dataclass
class AgentStack:
    """Named components composing an agent under test."""
    components: dict[str, ComponentCallable]

    def __post_init__(self):
        if not self.components:
            raise ValueError("AgentStack must have at least one component")
        for name in self.components:
            if not name or not isinstance(name, str):
                raise ValueError("component names must be non-empty strings")

    def __contains__(self, name: str) -> bool:
        return name in self.components

    def get(self, name: str) -> ComponentCallable:
        return self.components[name]


@dataclasses.dataclass(frozen=True)
class AttackStep:
    """One step in a compositional attack plan.

    Fields:
        name:               short stable id (used for trace + interpolation)
        target_component:   key into AgentStack.components
        input_template:     string with optional ``$step_<name>`` placeholders
                            that reference prior step outputs.
        success_predicate:  callable(output_str) -> bool. Defaults to
                            "always False" so the caller is forced to
                            think about what success means.
        critical:           a single-step breach sufficient to declare
                            the whole attack a success.
        timeout_seconds:    per-step wall-clock cap (default 30s).
    """
    name: str
    target_component: str
    input_template: str
    success_predicate: SuccessPredicate = dataclasses.field(
        default=lambda _output: False
    )
    critical: bool = False
    timeout_seconds: float = 30.0


@dataclasses.dataclass(frozen=True)
class AttackPlan:
    """Ordered sequence of AttackSteps with breach criteria."""
    steps: tuple[AttackStep, ...]
    min_consecutive_successes: int = 2
    name: str = "compositional"

    def __post_init__(self):
        if not self.steps:
            raise ValueError("AttackPlan must have at least one step")
        seen_names: set[str] = set()
        for s in self.steps:
            if not s.name:
                raise ValueError("step names must be non-empty")
            if s.name in seen_names:
                raise ValueError(f"duplicate step name {s.name!r}")
            seen_names.add(s.name)
        if self.min_consecutive_successes < 1:
            raise ValueError("min_consecutive_successes must be >= 1")


@dataclasses.dataclass(frozen=True)
class StepOutcome:
    """Per-step result."""
    step_name: str
    target_component: str
    rendered_input: str
    output: str
    success: bool
    duration_seconds: float
    error: str | None = None     # populated when step raised


@dataclasses.dataclass(frozen=True)
class CompositionResult:
    """End-of-plan summary."""
    plan_name: str
    outcomes: tuple[StepOutcome, ...]
    breached: bool
    breach_reason: str
    total_duration_seconds: float
    metadata: dict


# ────────────────────────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────────────────────────


_PLACEHOLDER_RE = re.compile(r"\$step_([A-Za-z0-9_\-]+)")


def _normalize_output(o: object) -> str:
    """Coerce arbitrary component output to a string for downstream use."""
    if isinstance(o, str):
        return o
    if isinstance(o, (list, tuple)):
        return "\n".join(_normalize_output(x) for x in o)
    if isinstance(o, dict):
        import json as _json
        return _json.dumps(o, sort_keys=True, default=str)
    return str(o)


def _interpolate(
    template: str, prior_outputs: dict[str, str]
) -> tuple[str, list[str]]:
    """Replace $step_<name> placeholders with prior outputs.

    Returns (rendered, missing_refs). If a referenced step has no output
    yet, the placeholder is left as-is and the name is reported.
    """
    missing: list[str] = []

    def _sub(m):
        ref = m.group(1)
        if ref in prior_outputs:
            return prior_outputs[ref]
        missing.append(ref)
        return m.group(0)

    rendered = _PLACEHOLDER_RE.sub(_sub, template)
    return rendered, missing


# ────────────────────────────────────────────────────────────────────
#  Runner
# ────────────────────────────────────────────────────────────────────


async def run_compositional_attack(
    stack: AgentStack,
    plan: AttackPlan,
    *,
    overall_timeout_seconds: float = 600.0,
) -> CompositionResult:
    """Execute the attack plan against the stack, with safety bounds.

    Returns a CompositionResult; never raises on component errors. Raises
    only on misconfiguration: unknown target_component or violated
    constraints surfaced at validation.
    """
    # Validate targets exist before any I/O.
    for s in plan.steps:
        if s.target_component not in stack:
            raise KeyError(
                f"step {s.name!r} targets unknown component "
                f"{s.target_component!r}; known: {sorted(stack.components)}"
            )

    deadline = time.monotonic() + max(1.0, float(overall_timeout_seconds))
    outcomes: list[StepOutcome] = []
    prior_outputs: dict[str, str] = {}
    consecutive_successes = 0
    breached = False
    breach_reason = ""
    started = time.monotonic()

    for step in plan.steps:
        if time.monotonic() > deadline:
            outcomes.append(
                StepOutcome(
                    step_name=step.name,
                    target_component=step.target_component,
                    rendered_input="",
                    output="",
                    success=False,
                    duration_seconds=0.0,
                    error="overall_timeout_exceeded",
                )
            )
            break

        rendered, missing = _interpolate(step.input_template, prior_outputs)
        callable_ = stack.get(step.target_component)
        step_started = time.monotonic()
        per_step_remaining = max(
            0.5, min(float(step.timeout_seconds), deadline - step_started)
        )

        try:
            raw_output = await asyncio.wait_for(
                callable_(rendered),
                timeout=per_step_remaining,
            )
            output = _normalize_output(raw_output)
            error = None
        except TimeoutError:
            output = ""
            error = "step_timeout"
        except Exception as exc:  # noqa: BLE001
            output = ""
            error = f"{type(exc).__name__}: {exc}"

        try:
            success = bool(step.success_predicate(output)) if not error else False
        except Exception:  # noqa: BLE001
            # A buggy predicate should not crash the harness — log and treat
            # as failure.
            success = False
            error = (error + "; ") if error else ""
            error += "predicate_raised"

        outcomes.append(
            StepOutcome(
                step_name=step.name,
                target_component=step.target_component,
                rendered_input=rendered,
                output=output,
                success=success,
                duration_seconds=time.monotonic() - step_started,
                error=error if error else (
                    f"missing_refs={missing}" if missing else None
                ),
            )
        )
        prior_outputs[step.name] = output

        if success:
            consecutive_successes += 1
            if step.critical:
                breached = True
                breach_reason = f"critical_step:{step.name}"
                break
            if consecutive_successes >= plan.min_consecutive_successes:
                breached = True
                breach_reason = (
                    f"consecutive_successes={consecutive_successes}"
                    f"@{step.name}"
                )
                break
        else:
            consecutive_successes = 0

    total_duration = time.monotonic() - started

    return CompositionResult(
        plan_name=plan.name,
        outcomes=tuple(outcomes),
        breached=breached,
        breach_reason=breach_reason or "no_breach",
        total_duration_seconds=total_duration,
        metadata={
            "n_steps": len(plan.steps),
            "n_steps_executed": len(outcomes),
            "n_successes": sum(1 for o in outcomes if o.success),
            "min_consecutive_successes": plan.min_consecutive_successes,
            "components_targeted": sorted(
                {o.target_component for o in outcomes}
            ),
        },
    )
