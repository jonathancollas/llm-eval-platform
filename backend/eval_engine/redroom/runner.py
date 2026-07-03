"""
Native Red Room runner.

The single function ``run_probe()`` is the only sanctioned way to issue
an adversarial probe through the native engine. It:

  1. Takes the request through the charter (charter.enforce()).
  2. Records an AUTHORIZE trace.
  3. Invokes the probe with a timeout.
  4. Records PROBE / RESPONSE traces for every attempt.
  5. Returns the final result with the verdict information.

All four steps are mandatory. If any step is bypassed (e.g. by calling
the probe directly), the resulting work is not Red-Room-compliant and
will not appear in any audit. This is enforced by code organization:
nothing outside this module imports the probe classes directly except
the test suite.

After the AUTHORIZE trace is written, :class:`~eval_engine.redroom._authorized_scope.AuthorizedScope`
is entered for the duration of the probe and follow-up PROBE/RESPONSE trace
emission. Code that needs to know it is on a charter-sanctioned path can
call :func:`~eval_engine.redroom._authorized_scope.is_authorized`.

External integrations (Garak D3, PyRIT D4) MUST follow the same
discipline: charter authorize → trace start → invoke external tool with
timeout → trace each emitted probe → trace finding.

This module deliberately does not implement Judge — that's a separate
concern that lands in D5 (coevolution). For now, the runner records
PROBE and RESPONSE; the FINDING trace will come from a later module
that consumes the trace stream.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
import uuid

from sqlmodel import Session

from eval_engine.redroom._authorized_scope import AuthorizedScope
from eval_engine.redroom.charter import (
    AttackRequest,
    CharterDecision,
    CharterPolicy,
    enforce,
    load_charter,
)
from eval_engine.redroom.probes.aiid_replay import AIIDReplayProbe
from eval_engine.redroom.probes.base import Probe, ProbeResult, TargetInvoke
from eval_engine.redroom.probes.crescendo import CrescendoProbe
from eval_engine.redroom.probes.garak_probe import GarakProbe
from eval_engine.redroom.probes.many_shot import ManyShotProbe
from eval_engine.redroom.trace_store import (
    TraceKind,
    TraceVerdict,
    compute_replay_hash,
    write_trace,
)

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
#  Probe registry
# ────────────────────────────────────────────────────────────────────


def build_default_registry() -> dict[str, Probe]:
    """Build the default registry of native probes.

    Tests and integrations override this when they need a custom
    catalogue (e.g. a real AIID dataset instead of the built-in samples).
    """
    return {
        "aiid_replay": AIIDReplayProbe(),
        "many_shot": ManyShotProbe(),
        "crescendo": CrescendoProbe(),
        "garak": GarakProbe(),
    }


# ────────────────────────────────────────────────────────────────────
#  Run inputs / outputs
# ────────────────────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class RunInputs:
    """Everything the runner needs to execute one probe.

    Fields the runner consumes itself; the probe-specific configuration
    travels through ``prompt_seed`` and ``seed``.
    """

    technique: str
    target_model_id: int
    tenant_id: int
    session_id: str          # groups multiple runs of one Red Room session
    target_invoke: TargetInvoke
    target_class: str = "self"
    aggressiveness: int = 2
    seed: int = 0
    max_turns: int = 4
    prompt_seed: str | None = None
    has_signed_consent: bool = False
    dual_approval_signers: tuple[str, ...] = ()
    created_by_user_id: int | None = None
    # Hard wall-clock cap for the whole probe run, in seconds.
    # Defaults to 60s — operators tighten or loosen via the charter
    # max_duration_seconds, which the runner clamps to.
    timeout_seconds: float = 60.0


@dataclasses.dataclass(frozen=True)
class RunOutput:
    """Result of one runner invocation.

    Always non-None: even rejections produce an output so the caller can
    show the user why the run didn't happen.
    """

    decision: CharterDecision
    result: ProbeResult | None
    duration_seconds: float
    session_uuid: str            # the run's stable id, surfaces in URLs


# ────────────────────────────────────────────────────────────────────
#  Public entry point
# ────────────────────────────────────────────────────────────────────


async def run_probe(
    inputs: RunInputs,
    *,
    session: Session,
    registry: dict[str, Probe] | None = None,
    policy: CharterPolicy | None = None,
) -> RunOutput:
    """Run one probe, end to end, with full audit trail.

    Raises HTTPException(403) if the charter refuses (via enforce()).
    Raises ValueError if the requested technique is unknown.

    On any other path, returns a RunOutput. The result.aborted_reason
    field tells the caller why a run that started couldn't finish — the
    runner does not propagate exceptions from the target itself, those
    are caught and recorded as aborted runs.
    """
    p = policy if policy is not None else load_charter()
    reg = registry if registry is not None else build_default_registry()

    # ── 0. Resolve the probe ────────────────────────────────────────
    probe = reg.get(inputs.technique)
    if probe is None:
        raise ValueError(
            f"unknown technique {inputs.technique!r}; "
            f"registered: {sorted(reg.keys())}"
        )

    # Enforce probe-level aggressiveness ceiling, separately from charter.
    # This is a defense-in-depth: even if a misconfigured charter allowed
    # L5, a probe that's only safe up to L2 must not be invoked at L3+.
    if inputs.aggressiveness > probe.MAX_AGGRESSIVENESS:
        raise ValueError(
            f"technique {inputs.technique!r} is capped at "
            f"L{probe.MAX_AGGRESSIVENESS}; got L{inputs.aggressiveness}"
        )

    # ── 1. Charter authorization ────────────────────────────────────
    request = AttackRequest(
        target_class=inputs.target_class,  # type: ignore[arg-type]
        aggressiveness=_int_to_aggressiveness(inputs.aggressiveness),
        has_signed_consent=inputs.has_signed_consent,
        dual_approval_signers=inputs.dual_approval_signers,
    )
    decision = enforce(request, p)  # raises HTTPException(403) on refusal

    session_uuid = str(uuid.uuid4())

    # ── 2. AUTHORIZE trace ─────────────────────────────────────────
    replay_hash = compute_replay_hash(
        technique=inputs.technique,
        prompt=inputs.prompt_seed or "",
        target_model_id=inputs.target_model_id,
        extra={"seed": inputs.seed, "max_turns": inputs.max_turns},
    )
    write_trace(
        session,
        tenant_id=inputs.tenant_id,
        session_id=inputs.session_id,
        kind=TraceKind.AUTHORIZE,
        target_class=inputs.target_class,
        aggressiveness=inputs.aggressiveness,
        replay_hash=replay_hash,
        target_model_id=inputs.target_model_id,
        verdict=None,
        engine="native",
        payload={
            "session_uuid": session_uuid,
            "technique": inputs.technique,
            "decision_reason": decision.reason,
            "effective_disclosure": decision.effective_disclosure,
            "max_turns": inputs.max_turns,
        },
        created_by_user_id=inputs.created_by_user_id,
    )

    # ── 3. Run the probe with timeout ──────────────────────────────
    # The runner enforces a wall-clock cap. The charter's
    # max_duration_seconds is the operator-side cap; the runner uses
    # the smaller of the two.
    effective_timeout = min(inputs.timeout_seconds, float(p.max_duration_seconds))
    started = time.monotonic()

    with AuthorizedScope():
        try:
            result = await asyncio.wait_for(
                probe.run(
                    target_invoke=inputs.target_invoke,
                    seed=inputs.seed,
                    max_turns=inputs.max_turns,
                    prompt_seed=inputs.prompt_seed,
                ),
                timeout=effective_timeout,
            )
        except TimeoutError:
            duration = time.monotonic() - started
            # Record the abort as a single PROBE trace with timeout reason.
            # We don't have actual prompts/responses to record — that's
            # expected for a timed-out run.
            write_trace(
                session,
                tenant_id=inputs.tenant_id,
                session_id=inputs.session_id,
                kind=TraceKind.PROBE,
                target_class=inputs.target_class,
                aggressiveness=inputs.aggressiveness,
                replay_hash=replay_hash,
                target_model_id=inputs.target_model_id,
                verdict=TraceVerdict.INCONCLUSIVE,
                engine="native",
                payload={
                    "session_uuid": session_uuid,
                    "technique": inputs.technique,
                    "aborted_reason": "timeout",
                    "timeout_seconds": effective_timeout,
                    "duration_seconds": duration,
                },
                created_by_user_id=inputs.created_by_user_id,
            )
            session.commit()
            timeout_result = ProbeResult(
                technique=inputs.technique,
                attempts=(),
                metadata={
                    "timeout_seconds": effective_timeout,
                    "duration_seconds": duration,
                },
                aborted_reason="timeout",
            )
            return RunOutput(
                decision=decision,
                result=timeout_result,
                duration_seconds=duration,
                session_uuid=session_uuid,
            )

        duration = time.monotonic() - started

        # ── 4. PROBE / RESPONSE traces for each attempt ────────────────
        for attempt in result.attempts:
            write_trace(
                session,
                tenant_id=inputs.tenant_id,
                session_id=inputs.session_id,
                kind=TraceKind.PROBE,
                target_class=inputs.target_class,
                aggressiveness=inputs.aggressiveness,
                replay_hash=replay_hash,
                target_model_id=inputs.target_model_id,
                verdict=None,
                engine="native",
                payload={
                    "session_uuid": session_uuid,
                    "technique": inputs.technique,
                    "turn": attempt.turn,
                    # Hash the prompt rather than store it raw — full prompts
                    # are recoverable from the (technique, seed, prompt_seed)
                    # tuple via replay, and storing them inflates the audit
                    # log. Operators who need the full prompt can replay.
                    "prompt_hash": _h(attempt.prompt),
                    "prompt_len": len(attempt.prompt),
                },
                created_by_user_id=inputs.created_by_user_id,
            )
            write_trace(
                session,
                tenant_id=inputs.tenant_id,
                session_id=inputs.session_id,
                kind=TraceKind.RESPONSE,
                target_class=inputs.target_class,
                aggressiveness=inputs.aggressiveness,
                replay_hash=replay_hash,
                target_model_id=inputs.target_model_id,
                verdict=None,
                engine="native",
                payload={
                    "session_uuid": session_uuid,
                    "technique": inputs.technique,
                    "turn": attempt.turn,
                    "response_hash": _h(attempt.response),
                    "response_len": len(attempt.response),
                },
                created_by_user_id=inputs.created_by_user_id,
            )

        # ── 5. Final summary trace ─────────────────────────────────────
        write_trace(
            session,
            tenant_id=inputs.tenant_id,
            session_id=inputs.session_id,
            kind=TraceKind.PROBE,
            target_class=inputs.target_class,
            aggressiveness=inputs.aggressiveness,
            replay_hash=replay_hash,
            target_model_id=inputs.target_model_id,
            verdict=(
                TraceVerdict.INCONCLUSIVE
                if result.aborted_reason
                else TraceVerdict.NEUTRAL
            ),
            engine="native",
            payload={
                "session_uuid": session_uuid,
                "technique": inputs.technique,
                "summary": True,
                "turns_executed": len(result.attempts),
                "duration_seconds": duration,
                "metadata": result.metadata,
                "aborted_reason": result.aborted_reason,
            },
            created_by_user_id=inputs.created_by_user_id,
        )
        session.commit()

        return RunOutput(
            decision=decision,
            result=result,
            duration_seconds=duration,
            session_uuid=session_uuid,
        )


# ────────────────────────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────────────────────────


def _int_to_aggressiveness(level: int):
    """Convert int to Aggressiveness enum, with a clear error."""
    from eval_engine.redroom.charter import Aggressiveness
    if level < 1 or level > 5:
        raise ValueError(f"aggressiveness must be 1..5, got {level}")
    return Aggressiveness(level)


def _h(s: str) -> str:
    """Stable short hash for trace payloads — first 16 chars of sha256 hex."""
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
