"""Invariant tests for the AuthorizedScope guard (P0-1).

The Red Room's central invariant is that no adversarial engine function
runs without the charter having said yes first. The :class:`AuthorizedScope`
context manager turns that convention into a runtime check: every
engine entry point is decorated with ``@requires_authorized_scope`` and
will raise :class:`RedRoomScopeError` if called outside a scope.

This file:

  - asserts that every adversarial engine function refuses to run
    outside an AuthorizedScope (the bypass scenario from the audit);
  - asserts that ``run_probe`` opens the scope correctly (positive path);
  - asserts that the scope propagates across ``await`` and across
    asyncio.create_task — the contextvars semantics that make the
    guard usable in real async code.

Tests in this file opt out of the autouse fixture via
``pytest.mark.no_authorized_scope`` because they need to observe the
default (unauthorized) state of the contextvar.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("REDROOM_TRACE_SECRET", "x" * 32 + "_test_secret")

from eval_engine.redroom._authorized_scope import (  # noqa: E402
    AuthorizedScope,
    RedRoomScopeError,
    is_authorized,
    requires_authorized_scope,
)


# ════════════════════════════════════════════════════════════════════════
#  Default state and basic context manager semantics
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.no_authorized_scope
class TestScopeBasics:
    def test_default_state_is_unauthorized(self):
        assert is_authorized() is False

    def test_context_manager_opens_and_closes(self):
        assert is_authorized() is False
        with AuthorizedScope():
            assert is_authorized() is True
        assert is_authorized() is False

    def test_nested_scopes_are_safe(self):
        with AuthorizedScope():
            assert is_authorized() is True
            with AuthorizedScope():
                assert is_authorized() is True
            assert is_authorized() is True
        assert is_authorized() is False

    def test_scope_restored_on_exception(self):
        with pytest.raises(RuntimeError, match="oops"):
            with AuthorizedScope():
                assert is_authorized() is True
                raise RuntimeError("oops")
        assert is_authorized() is False


# ════════════════════════════════════════════════════════════════════════
#  Decorator behavior
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.no_authorized_scope
class TestDecorator:
    def test_sync_function_refuses_outside_scope(self):
        @requires_authorized_scope
        def f(x: int) -> int:
            return x + 1

        with pytest.raises(RedRoomScopeError, match="outside an AuthorizedScope"):
            f(1)

    def test_sync_function_runs_inside_scope(self):
        @requires_authorized_scope
        def f(x: int) -> int:
            return x + 1

        with AuthorizedScope():
            assert f(1) == 2

    def test_async_function_refuses_outside_scope(self):
        @requires_authorized_scope
        async def f(x: int) -> int:
            return x + 1

        with pytest.raises(RedRoomScopeError, match="outside an AuthorizedScope"):
            asyncio.run(f(1))

    def test_async_function_runs_inside_scope(self):
        @requires_authorized_scope
        async def f(x: int) -> int:
            return x + 1

        async def driver():
            with AuthorizedScope():
                return await f(1)

        assert asyncio.run(driver()) == 2

    def test_decorator_preserves_function_name(self):
        @requires_authorized_scope
        def some_engine_call() -> int:
            return 1

        assert some_engine_call.__name__ == "some_engine_call"

    def test_error_message_names_the_function(self):
        @requires_authorized_scope
        def specific_engine_function() -> int:
            return 1

        with pytest.raises(RedRoomScopeError, match="specific_engine_function"):
            specific_engine_function()


# ════════════════════════════════════════════════════════════════════════
#  Async propagation — the contextvar must survive await and create_task
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.no_authorized_scope
class TestAsyncPropagation:
    def test_propagates_across_await(self):
        @requires_authorized_scope
        async def inner() -> bool:
            await asyncio.sleep(0)
            return is_authorized()

        async def driver():
            with AuthorizedScope():
                return await inner()

        assert asyncio.run(driver()) is True

    def test_propagates_into_created_task(self):
        @requires_authorized_scope
        async def inner() -> bool:
            return is_authorized()

        async def driver():
            with AuthorizedScope():
                # Tasks created inside the scope inherit the contextvar
                # snapshot — that's the Python 3.11+ default semantic.
                t = asyncio.create_task(inner())
                return await t

        assert asyncio.run(driver()) is True

    def test_gather_children_inherit_scope(self):
        @requires_authorized_scope
        async def child() -> bool:
            return is_authorized()

        async def driver():
            with AuthorizedScope():
                results = await asyncio.gather(child(), child(), child())
            return results

        assert asyncio.run(driver()) == [True, True, True]


# ════════════════════════════════════════════════════════════════════════
#  Bypass invariant — every advertised engine function MUST refuse
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.no_authorized_scope
class TestBypassInvariant:
    """If any of these tests fails, the audit's P0-1 bypass is back."""

    def test_run_compositional_attack_refuses(self):
        from eval_engine.redroom.composition.harness import (
            AgentStack,
            AttackPlan,
            AttackStep,
            run_compositional_attack,
        )

        async def _noop(_: str) -> str:
            return ""

        stack = AgentStack(components={"x": _noop})
        plan = AttackPlan(steps=(
            AttackStep(name="s", target_component="x", input_template="t"),
        ))
        with pytest.raises(RedRoomScopeError):
            asyncio.run(run_compositional_attack(stack, plan))

    def test_run_coevolution_refuses(self):
        from eval_engine.redroom.coevolution.engine import (
            CoevolutionConfig,
            run_coevolution,
        )
        from eval_engine.redroom.coevolution.strategy_memory import (
            Strategy,
            StrategyMemory,
        )

        async def _t(_p): return ""
        async def _a(_p): return "x"
        async def _j(_p, _r): return 0.0

        memory = StrategyMemory([Strategy(name="x", template="t")])
        cfg = CoevolutionConfig(objective="o", max_rounds=1)
        with pytest.raises(RedRoomScopeError):
            asyncio.run(
                run_coevolution(
                    target=_t, attacker=_a, judge=_j, memory=memory, config=cfg
                )
            )

    def test_run_pair_refuses(self):
        from eval_engine.redroom.integrations.pyrit_runner import run_pair

        async def _t(_p): return ""
        async def _a(_p): return ""
        async def _j(_p, _r): return 0.0

        with pytest.raises(RedRoomScopeError):
            asyncio.run(
                run_pair(
                    target=_t, attacker=_a, judge=_j,
                    objective="o", max_rounds=1,
                )
            )

    def test_run_tap_refuses(self):
        from eval_engine.redroom.integrations.pyrit_runner import run_tap

        async def _t(_p): return ""
        async def _a(_p): return ""
        async def _j(_p, _r): return 0.0

        with pytest.raises(RedRoomScopeError):
            asyncio.run(
                run_tap(
                    target=_t, attacker=_a, judge=_j,
                    objective="o", max_rounds=1, branching_factor=1, beam_width=1,
                )
            )

    def test_pyrit_runner_run_refuses(self):
        from eval_engine.redroom.integrations.pyrit_runner import PyRITRunner

        async def _t(_p): return ""
        async def _a(_p): return ""
        async def _j(_p, _r): return 0.0

        with pytest.raises(RedRoomScopeError):
            asyncio.run(
                PyRITRunner().run(
                    technique="pair",
                    target=_t, attacker=_a, judge=_j,
                    objective="o", max_rounds=1,
                )
            )

    def test_run_pyrit_subprocess_refuses(self):
        from eval_engine.redroom.integrations.pyrit_runner import (
            run_pyrit_subprocess,
        )

        # We don't even need pyrit-cli installed — the scope check fires first.
        with pytest.raises(RedRoomScopeError):
            run_pyrit_subprocess("pair", target_model_id="m")

    def test_run_garak_subprocess_refuses(self):
        from eval_engine.redroom.integrations.garak_runner import (
            run_garak_subprocess,
        )

        with pytest.raises(RedRoomScopeError):
            run_garak_subprocess("dan.Dan_11_0", target_model_id="m")

    def test_garak_runner_run_static_refuses(self):
        from eval_engine.redroom.integrations.garak_runner import GarakRunner

        async def _t(_p): return ""

        with pytest.raises(RedRoomScopeError):
            asyncio.run(GarakRunner().run_static("dan.Dan_11_0", _t))


# ════════════════════════════════════════════════════════════════════════
#  Positive path — run_probe opens the scope so engines can run
# ════════════════════════════════════════════════════════════════════════


class TestRunProbeOpensScope:
    """These tests use the autouse fixture (default for test_redroom_*)."""

    def test_runner_path_executes_decorated_engine(self):
        # Inside the autouse scope, decorated calls should pass.
        from eval_engine.redroom.integrations.pyrit_runner import run_pair

        async def _t(_p): return "ok"
        async def _a(_p): return "x"
        async def _j(_p, _r): return 0.5

        result = asyncio.run(
            run_pair(
                target=_t, attacker=_a, judge=_j,
                objective="ok", max_rounds=1,
            )
        )
        assert result.metadata["algorithm"] == "pair"
