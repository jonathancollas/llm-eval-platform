"""Charter-authorized scope for adversarial engine functions.

Every adversarial engine function (run_pair, run_tap, run_compositional_attack,
run_coevolution, run_garak_subprocess, run_pyrit_subprocess, GarakRunner.run_*,
PyRITRunner.run) MUST execute inside an :class:`AuthorizedScope`.

The scope is opened by :func:`runner.run_probe` AFTER ``charter.enforce()``
returns OK. It is the runtime mechanism that turns "the charter is the single
gate" from a code-review convention into an enforced invariant.

Direct callers (tests, scripts, ad-hoc tooling) must open the scope
explicitly and document why::

    from eval_engine.redroom._authorized_scope import AuthorizedScope

    with AuthorizedScope():
        result = await run_pair(...)

Without this guard, a developer who imports an engine function and calls
it directly would bypass the charter (cf. audit P0-1).

Implementation details:
  - Uses :mod:`contextvars`. The flag propagates across ``await`` and
    across asyncio task boundaries (Python 3.11+ semantics).
  - Stack-safe: nested ``with AuthorizedScope()`` blocks are fine.
  - Read-only ``is_authorized()`` for diagnostics.
  - Decorator works on sync and async callables. The error message names
    the decorated function for fast triage.
"""
from __future__ import annotations

import asyncio
import contextvars
import functools
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

__all__ = [
    "AuthorizedScope",
    "RedRoomScopeError",
    "is_authorized",
    "requires_authorized_scope",
]

P = ParamSpec("P")
R = TypeVar("R")


_authorized: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "redroom_authorized", default=False
)


class RedRoomScopeError(RuntimeError):
    """Raised when an adversarial function runs outside an :class:`AuthorizedScope`."""


class AuthorizedScope:
    """Context manager that flags the current task as charter-authorized.

    Opened by :func:`runner.run_probe` after :func:`charter.enforce` returns OK.
    Tests and scripts that call engine functions directly open it themselves.
    """

    def __enter__(self) -> "AuthorizedScope":
        self._token = _authorized.set(True)
        return self

    def __exit__(self, *_: Any) -> None:
        _authorized.reset(self._token)


def is_authorized() -> bool:
    """Return True iff the current async task is inside an :class:`AuthorizedScope`."""
    return _authorized.get()


def _raise_unauthorized(qualname: str) -> None:
    raise RedRoomScopeError(
        f"{qualname} called outside an AuthorizedScope. "
        "Adversarial engine functions must be invoked via "
        "runner.run_probe() (which opens the scope after "
        "charter.enforce()) or inside an explicit "
        "`with AuthorizedScope():` block."
    )


def requires_authorized_scope(fn: Callable[P, R]) -> Callable[P, R]:
    """Decorator: refuse to run unless an :class:`AuthorizedScope` is active.

    Works on sync and async callables; the wrapper preserves the original
    signature via ``functools.wraps`` so introspection / docstrings stay
    intact.
    """
    if asyncio.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not _authorized.get():
                _raise_unauthorized(fn.__qualname__)
            return await fn(*args, **kwargs)  # type: ignore[no-any-return,misc]

        return async_wrapper  # type: ignore[return-value]

    @functools.wraps(fn)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        if not _authorized.get():
            _raise_unauthorized(fn.__qualname__)
        return fn(*args, **kwargs)

    return sync_wrapper
