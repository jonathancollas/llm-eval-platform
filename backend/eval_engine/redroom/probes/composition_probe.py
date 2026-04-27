"""
CompositionProbe — runs a compositional attack plan as a Probe.

The probe expects ``prompt_seed`` to be a JSON object with a ``plan`` key
describing an AttackPlan in serialised form. The actual stack is
provided at construction time (the runner builds it once per session).

Aggressiveness: L5.

The probe does NOT accept arbitrary Python callables in prompt_seed —
that would be code-injection. Instead, the JSON describes which
named template predicates to apply (e.g. "contains_string"), and the
probe instantiates them.
"""
from __future__ import annotations

import json
from collections.abc import Callable

from eval_engine.redroom._text_safety import truncate_error
from eval_engine.redroom.composition.harness import (
    AgentStack,
    AttackPlan,
    AttackStep,
    run_compositional_attack,
)
from eval_engine.redroom.probes.base import (
    Probe,
    ProbeAttempt,
    ProbeResult,
    TargetInvoke,
)

# ────────────────────────────────────────────────────────────────────
#  Predicate library
# ────────────────────────────────────────────────────────────────────


def _pred_contains(needle: str):
    needle_lower = str(needle).lower()
    def f(out: str) -> bool:
        return needle_lower in (out or "").lower()
    return f


def _pred_not_contains(needle: str):
    needle_lower = str(needle).lower()
    def f(out: str) -> bool:
        return needle_lower not in (out or "").lower()
    return f


def _pred_min_length(n: int):
    n_int = max(0, int(n))
    def f(out: str) -> bool:
        return len(out or "") >= n_int
    return f


def _pred_always_true(_arg=None):
    def f(_out: str) -> bool:
        return True
    return f


_PREDICATES: dict[str, Callable[..., Callable[[str], bool]]] = {
    "contains": _pred_contains,
    "not_contains": _pred_not_contains,
    "min_length": _pred_min_length,
    "always_true": _pred_always_true,
}


def _resolve_predicate(spec: dict) -> Callable[[str], bool]:
    """Translate a JSON predicate spec to a Python callable.

    Examples accepted:
      {"type": "contains", "value": "secret"}
      {"type": "min_length", "value": 100}
      {"type": "always_true"}
    """
    if not isinstance(spec, dict):
        raise ValueError("predicate must be an object")
    kind = spec.get("type")
    if kind not in _PREDICATES:
        raise ValueError(
            f"unknown predicate type {kind!r}; "
            f"known: {sorted(_PREDICATES)}"
        )
    factory = _PREDICATES[kind]
    if kind in ("always_true",):
        return factory()
    if "value" not in spec:
        raise ValueError(f"predicate {kind!r} requires 'value'")
    return factory(spec["value"])


# ────────────────────────────────────────────────────────────────────
#  Probe
# ────────────────────────────────────────────────────────────────────


class CompositionProbe(Probe):
    """L5 probe — composes attacks across a stack of named components."""

    TECHNIQUE = "composition"
    MAX_AGGRESSIVENESS = 5

    def __init__(self, *, stack: AgentStack | None = None):
        super().__init__()
        self._stack = stack

    async def run(
        self,
        *,
        target_invoke: TargetInvoke,
        seed: int,
        max_turns: int,
        prompt_seed: str | None = None,
    ) -> ProbeResult:
        del seed

        if self._stack is None:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={
                    "error": "CompositionProbe requires an AgentStack at "
                             "construction time"
                },
                aborted_reason="missing_stack",
            )
        if not prompt_seed:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": "prompt_seed required (JSON plan)"},
                aborted_reason="missing_prompt_seed",
            )
        try:
            cfg = json.loads(prompt_seed)
        except json.JSONDecodeError as exc:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": f"invalid JSON: {exc}"},
                aborted_reason="bad_prompt_seed",
            )
        if not isinstance(cfg, dict):
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": "prompt_seed must be an object"},
                aborted_reason="bad_prompt_seed",
            )
        steps_raw = cfg.get("steps")
        if not isinstance(steps_raw, list) or not steps_raw:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": "steps must be a non-empty list"},
                aborted_reason="bad_prompt_seed",
            )

        try:
            steps = tuple(_parse_step(i, raw) for i, raw in enumerate(steps_raw))
            plan = AttackPlan(
                steps=steps[: max(1, int(max_turns))],
                min_consecutive_successes=int(
                    cfg.get("min_consecutive_successes", 2)
                ),
                name=str(cfg.get("name", "compositional_attack")),
            )
        except (ValueError, TypeError) as exc:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": f"plan_invalid: {exc}"},
                aborted_reason="bad_prompt_seed",
            )

        try:
            result = await run_compositional_attack(self._stack, plan)
        except KeyError as exc:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": f"unknown_component: {exc}"},
                aborted_reason="bad_plan",
            )

        attempts = tuple(
            ProbeAttempt(
                turn=i,
                prompt=f"[{o.target_component}] {o.rendered_input}",
                response=o.output if not o.error else f"<{o.error}> {o.output}",
            )
            for i, o in enumerate(result.outcomes)
        )

        return ProbeResult(
            technique=self.TECHNIQUE,
            attempts=attempts,
            metadata={
                "plan_name": result.plan_name,
                "breached": result.breached,
                "breach_reason": result.breach_reason,
                "total_duration_seconds": round(result.total_duration_seconds, 3),
                **result.metadata,
                "outcomes": [
                    {
                        "step_name": o.step_name,
                        "component": o.target_component,
                        "success": o.success,
                        "error": truncate_error(o.error, max_chars=80),
                    }
                    for o in result.outcomes
                ],
            },
        )


def _parse_step(idx: int, raw) -> AttackStep:
    if not isinstance(raw, dict):
        raise ValueError(f"steps[{idx}] is not an object")
    name = str(raw.get("name") or f"step_{idx}")
    target = raw.get("target_component")
    if not isinstance(target, str) or not target:
        raise ValueError(f"steps[{idx}] missing target_component")
    template = raw.get("input_template")
    if not isinstance(template, str):
        raise ValueError(f"steps[{idx}] input_template must be a string")
    pred_spec = raw.get("success_predicate", {"type": "always_true"})
    pred = _resolve_predicate(pred_spec)
    return AttackStep(
        name=name,
        target_component=target,
        input_template=template,
        success_predicate=pred,
        critical=bool(raw.get("critical", False)),
        timeout_seconds=float(raw.get("timeout_seconds", 30.0)),
    )
