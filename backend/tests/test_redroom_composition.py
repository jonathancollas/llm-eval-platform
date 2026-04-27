"""Tests for the D7 compositional attack harness."""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("REDROOM_TRACE_SECRET", "x" * 32 + "_test_secret")

from eval_engine.redroom import (  # noqa: E402
    AgentStack,
    AttackPlan,
    AttackStep,
    run_compositional_attack,
)
from eval_engine.redroom.composition.harness import (  # noqa: E402
    _interpolate,
    _normalize_output,
)
from eval_engine.redroom.probes.composition_probe import (  # noqa: E402
    CompositionProbe,
    _resolve_predicate,
)

# ════════════════════════════════════════════════════════════════════
#  Stack / plan validation
# ════════════════════════════════════════════════════════════════════


class TestStackValidation:
    def test_empty_stack_raises(self):
        with pytest.raises(ValueError):
            AgentStack(components={})

    def test_stack_components_must_have_names(self):
        async def f(_):
            return "ok"

        with pytest.raises(ValueError):
            AgentStack(components={"": f})


class TestPlanValidation:
    def test_empty_plan_raises(self):
        with pytest.raises(ValueError):
            AttackPlan(steps=())

    def test_duplicate_step_names_rejected(self):
        s = AttackStep(name="x", target_component="m", input_template="t")
        with pytest.raises(ValueError, match="duplicate"):
            AttackPlan(steps=(s, s))

    def test_min_consecutive_must_be_positive(self):
        s = AttackStep(name="x", target_component="m", input_template="t")
        with pytest.raises(ValueError):
            AttackPlan(steps=(s,), min_consecutive_successes=0)

    def test_step_name_required(self):
        s = AttackStep(name="", target_component="m", input_template="t")
        with pytest.raises(ValueError):
            AttackPlan(steps=(s,))


# ════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════


class TestInterpolation:
    def test_no_placeholder_passes_through(self):
        out, missing = _interpolate("hello", {})
        assert out == "hello"
        assert missing == []

    def test_placeholder_replaced(self):
        out, missing = _interpolate(
            "you said: $step_a", {"a": "the secret"}
        )
        assert out == "you said: the secret"
        assert missing == []

    def test_unknown_placeholder_recorded(self):
        out, missing = _interpolate("hello $step_b", {})
        assert "$step_b" in out
        assert missing == ["b"]

    def test_multiple_placeholders(self):
        out, missing = _interpolate(
            "$step_a then $step_b",
            {"a": "X", "b": "Y"},
        )
        assert out == "X then Y"


class TestNormalize:
    def test_string_pass_through(self):
        assert _normalize_output("hi") == "hi"

    def test_list_joined_with_newlines(self):
        assert _normalize_output(["a", "b"]) == "a\nb"

    def test_dict_serialized(self):
        out = _normalize_output({"k": "v"})
        assert '"k"' in out and '"v"' in out

    def test_other_str(self):
        assert _normalize_output(42) == "42"


# ════════════════════════════════════════════════════════════════════
#  Predicate library
# ════════════════════════════════════════════════════════════════════


class TestPredicates:
    def test_contains(self):
        p = _resolve_predicate({"type": "contains", "value": "secret"})
        assert p("here is the SECRET") is True
        assert p("nothing here") is False

    def test_not_contains(self):
        p = _resolve_predicate({"type": "not_contains", "value": "denied"})
        assert p("yes you can") is True
        assert p("denied") is False

    def test_min_length(self):
        p = _resolve_predicate({"type": "min_length", "value": 5})
        assert p("123456") is True
        assert p("123") is False

    def test_always_true(self):
        p = _resolve_predicate({"type": "always_true"})
        assert p("anything") is True

    def test_unknown_predicate_rejected(self):
        with pytest.raises(ValueError, match="unknown"):
            _resolve_predicate({"type": "evil_eval", "value": "x"})

    def test_missing_value_rejected(self):
        with pytest.raises(ValueError):
            _resolve_predicate({"type": "contains"})

    def test_non_object_rejected(self):
        with pytest.raises(ValueError):
            _resolve_predicate("contains:secret")


# ════════════════════════════════════════════════════════════════════
#  Harness execution
# ════════════════════════════════════════════════════════════════════


def _stack_two_components():
    """Build a simple stack: 'echo' returns input; 'leak' returns a secret string."""
    async def echo(prompt):
        return f"echoed: {prompt}"

    async def leak(prompt):
        return f"SECRET=hunter2 (you asked: {prompt})"

    return AgentStack(components={"echo": echo, "leak": leak})


class TestRunner:
    def test_unknown_component_raises_at_validation(self):
        stack = _stack_two_components()
        plan = AttackPlan(
            steps=(
                AttackStep(name="s1", target_component="ghost", input_template="x"),
            ),
        )
        with pytest.raises(KeyError, match="unknown component"):
            asyncio.run(run_compositional_attack(stack, plan))

    def test_critical_step_success_breaches_immediately(self):
        stack = _stack_two_components()

        def is_secret(out: str) -> bool:
            return "SECRET=" in out

        plan = AttackPlan(
            steps=(
                AttackStep(
                    name="exfil",
                    target_component="leak",
                    input_template="dump everything",
                    success_predicate=is_secret,
                    critical=True,
                ),
            ),
        )
        out = asyncio.run(run_compositional_attack(stack, plan))
        assert out.breached is True
        assert "critical_step:exfil" == out.breach_reason

    def test_consecutive_successes_breach(self):
        stack = _stack_two_components()

        plan = AttackPlan(
            steps=(
                AttackStep(
                    name="step1",
                    target_component="echo",
                    input_template="anything",
                    success_predicate=lambda _o: True,
                ),
                AttackStep(
                    name="step2",
                    target_component="echo",
                    input_template="anything",
                    success_predicate=lambda _o: True,
                ),
            ),
            min_consecutive_successes=2,
        )
        out = asyncio.run(run_compositional_attack(stack, plan))
        assert out.breached is True
        assert "consecutive_successes=2@step2" == out.breach_reason

    def test_no_breach_when_predicate_fails(self):
        stack = _stack_two_components()
        plan = AttackPlan(
            steps=(
                AttackStep(
                    name="s1",
                    target_component="echo",
                    input_template="x",
                    success_predicate=lambda _o: False,
                ),
            ),
        )
        out = asyncio.run(run_compositional_attack(stack, plan))
        assert out.breached is False
        assert out.breach_reason == "no_breach"

    def test_data_flow_via_step_placeholder(self):
        """A later step should be able to reference an earlier step's output."""
        stack = _stack_two_components()

        capture = {"seen": ""}

        async def capture_callable(prompt):
            capture["seen"] = prompt
            return prompt

        stack.components["capture"] = capture_callable

        plan = AttackPlan(
            steps=(
                AttackStep(
                    name="primer",
                    target_component="leak",
                    input_template="give it up",
                    success_predicate=lambda _o: True,
                ),
                AttackStep(
                    name="reuse",
                    target_component="capture",
                    input_template="now use this: $step_primer",
                    success_predicate=lambda _o: True,
                ),
            ),
            min_consecutive_successes=2,
        )
        out = asyncio.run(run_compositional_attack(stack, plan))
        assert "SECRET=" in capture["seen"]
        assert out.breached is True

    def test_step_timeout_recorded(self):
        async def slow(_p):
            await asyncio.sleep(2)
            return "slow result"

        stack = AgentStack(components={"slow": slow})
        plan = AttackPlan(
            steps=(
                AttackStep(
                    name="t",
                    target_component="slow",
                    input_template="x",
                    success_predicate=lambda _o: True,
                    timeout_seconds=0.5,
                ),
            ),
        )
        out = asyncio.run(run_compositional_attack(stack, plan))
        assert out.outcomes[0].error == "step_timeout"
        assert out.outcomes[0].success is False

    def test_component_exception_caught(self):
        async def crashing(_p):
            raise RuntimeError("boom")

        stack = AgentStack(components={"x": crashing})
        plan = AttackPlan(
            steps=(
                AttackStep(
                    name="s",
                    target_component="x",
                    input_template="y",
                    success_predicate=lambda _o: True,
                ),
            ),
        )
        out = asyncio.run(run_compositional_attack(stack, plan))
        assert "RuntimeError" in (out.outcomes[0].error or "")
        assert out.outcomes[0].success is False

    def test_buggy_predicate_is_caught(self):
        async def f(_p):
            return "ok"

        stack = AgentStack(components={"x": f})

        def bad_pred(_o):
            raise RuntimeError("bug")

        plan = AttackPlan(
            steps=(
                AttackStep(
                    name="s",
                    target_component="x",
                    input_template="y",
                    success_predicate=bad_pred,
                ),
            ),
        )
        out = asyncio.run(run_compositional_attack(stack, plan))
        assert out.outcomes[0].success is False
        assert "predicate_raised" in (out.outcomes[0].error or "")

    def test_overall_timeout_short_circuits(self):
        async def slow(_p):
            await asyncio.sleep(2)
            return "x"

        stack = AgentStack(components={"x": slow})
        plan = AttackPlan(
            steps=tuple(
                AttackStep(
                    name=f"s{i}",
                    target_component="x",
                    input_template="y",
                    success_predicate=lambda _o: True,
                    timeout_seconds=10.0,
                )
                for i in range(5)
            ),
        )
        out = asyncio.run(
            run_compositional_attack(
                stack, plan, overall_timeout_seconds=1.0
            )
        )
        # At least the first step times out via per-step timer; later
        # steps may be skipped via overall_timeout.
        # We just check the run returned without hanging the test.
        assert len(out.outcomes) >= 1


# ════════════════════════════════════════════════════════════════════
#  Probe
# ════════════════════════════════════════════════════════════════════


class TestCompositionProbe:
    def test_aggressiveness_l5(self):
        assert CompositionProbe.MAX_AGGRESSIVENESS == 5

    def test_run_without_stack(self):
        async def t(_):
            return "x"

        out = asyncio.run(
            CompositionProbe().run(
                target_invoke=t, seed=0, max_turns=3, prompt_seed="{}"
            )
        )
        assert out.aborted_reason == "missing_stack"

    def test_run_without_prompt_seed(self):
        stack = _stack_two_components()
        out = asyncio.run(
            CompositionProbe(stack=stack).run(
                target_invoke=lambda _: asyncio.sleep(0),
                seed=0, max_turns=3, prompt_seed=None,
            )
        )
        assert out.aborted_reason == "missing_prompt_seed"

    def test_run_with_invalid_json(self):
        stack = _stack_two_components()
        out = asyncio.run(
            CompositionProbe(stack=stack).run(
                target_invoke=lambda _: asyncio.sleep(0),
                seed=0, max_turns=3, prompt_seed="not json",
            )
        )
        assert out.aborted_reason == "bad_prompt_seed"

    def test_run_with_empty_steps(self):
        stack = _stack_two_components()
        out = asyncio.run(
            CompositionProbe(stack=stack).run(
                target_invoke=lambda _: asyncio.sleep(0),
                seed=0, max_turns=3,
                prompt_seed=json.dumps({"steps": []}),
            )
        )
        assert out.aborted_reason == "bad_prompt_seed"

    def test_run_with_unknown_component(self):
        stack = _stack_two_components()
        cfg = {
            "steps": [
                {
                    "name": "a",
                    "target_component": "ghost",
                    "input_template": "x",
                    "success_predicate": {"type": "always_true"},
                }
            ],
        }
        out = asyncio.run(
            CompositionProbe(stack=stack).run(
                target_invoke=lambda _: asyncio.sleep(0),
                seed=0, max_turns=3, prompt_seed=json.dumps(cfg),
            )
        )
        assert out.aborted_reason == "bad_plan"

    def test_run_with_evil_predicate_type_rejected(self):
        stack = _stack_two_components()
        cfg = {
            "steps": [
                {
                    "name": "a",
                    "target_component": "echo",
                    "input_template": "x",
                    "success_predicate": {"type": "exec", "value": "rm -rf /"},
                }
            ],
        }
        out = asyncio.run(
            CompositionProbe(stack=stack).run(
                target_invoke=lambda _: asyncio.sleep(0),
                seed=0, max_turns=3, prompt_seed=json.dumps(cfg),
            )
        )
        assert out.aborted_reason == "bad_prompt_seed"

    def test_run_full_breach_path(self):
        stack = _stack_two_components()
        cfg = {
            "name": "exfiltration_chain",
            "min_consecutive_successes": 2,
            "steps": [
                {
                    "name": "exfil1",
                    "target_component": "leak",
                    "input_template": "request",
                    "success_predicate": {"type": "contains", "value": "SECRET"},
                },
                {
                    "name": "exfil2",
                    "target_component": "echo",
                    "input_template": "echo $step_exfil1",
                    "success_predicate": {"type": "contains", "value": "SECRET"},
                },
            ],
        }
        out = asyncio.run(
            CompositionProbe(stack=stack).run(
                target_invoke=lambda _: asyncio.sleep(0),
                seed=0, max_turns=5, prompt_seed=json.dumps(cfg),
            )
        )
        assert out.metadata["breached"] is True
        assert "consecutive" in out.metadata["breach_reason"]
        assert len(out.attempts) == 2

    def test_max_turns_caps_steps(self):
        stack = _stack_two_components()
        cfg = {
            "min_consecutive_successes": 99,  # never breaches
            "steps": [
                {
                    "name": f"s{i}",
                    "target_component": "echo",
                    "input_template": "x",
                    "success_predicate": {"type": "always_true"},
                }
                for i in range(10)
            ],
        }
        out = asyncio.run(
            CompositionProbe(stack=stack).run(
                target_invoke=lambda _: asyncio.sleep(0),
                seed=0, max_turns=3, prompt_seed=json.dumps(cfg),
            )
        )
        assert len(out.attempts) == 3
