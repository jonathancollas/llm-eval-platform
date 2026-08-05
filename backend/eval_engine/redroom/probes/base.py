"""
Probe interface — every attack technique implements this.

A Probe is a deterministic, replayable adversarial procedure:

  - Given a target callable (target_invoke), an ATTACK_REQUEST_CONTEXT
    (charter-authorized request metadata), and a seed, the probe issues
    ONE OR MORE prompts and returns ONE OR MORE ProbeResult.

  - The probe MUST NOT do its own authorization. The runner does that
    via charter.enforce() before calling probe.run().

  - The probe MUST NOT do its own logging. The runner emits the
    PROBE / RESPONSE / JUDGE / FINDING traces around probe.run().

  - The probe SHOULD be deterministic given the same seed: replay must
    produce the same prompt sequence. If the technique is intrinsically
    non-deterministic (e.g. samples from an LLM), the probe must record
    enough state in ProbeResult.metadata to allow replay.

This split keeps probes pure (input → prompts/results), which makes
them trivially testable, reusable across the runner / Garak adapter /
PyRIT adapter, and easy to swap.
"""
from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

# ────────────────────────────────────────────────────────────────────
#  Types
# ────────────────────────────────────────────────────────────────────


# A target invocation: take a string prompt, return the target's response
# string. Async because all real targets are network-bound. The runner
# wraps this with timeout, retry, and trace emission — the probe just
# treats it as a black-box callable.
TargetInvoke = Callable[[str], Awaitable[str]]


@dataclasses.dataclass(frozen=True)
class ProbeAttempt:
    """One round-trip of a probe: a single prompt sent + response received.

    Multi-turn techniques produce multiple ProbeAttempts in sequence.
    """

    turn: int                   # 0-indexed turn number within the probe run
    prompt: str
    response: str
    # Per-attempt judge verdict (set by the runner after JUDGE pass)
    refusal_score: float | None = None
    leaked: bool | None = None


@dataclasses.dataclass(frozen=True)
class ProbeResult:
    """Output of one probe.run() call.

    The probe DOES NOT decide whether the run was a "finding" — the
    runner / judge does. The probe just returns the raw record of what
    happened.
    """

    technique: str              # e.g. "many_shot", "crescendo", "aiid_replay"
    attempts: tuple[ProbeAttempt, ...]
    # Free-form per-technique metadata used for replay reconstruction.
    # Examples:
    #   many_shot:    {"shot_count": 64, "shot_set_id": "harmful-qa-v1"}
    #   crescendo:    {"escalation_path": ["A", "B", "C"], "stop_reason": "refused"}
    #   aiid_replay:  {"incident_id": "AIID-1234"}
    metadata: dict = dataclasses.field(default_factory=dict)
    # If the probe ran to completion, this is None. If it bailed early
    # (timeout, target error, target refused too many times in a row),
    # this is the reason — useful for telemetry and retry decisions.
    aborted_reason: str | None = None


# ────────────────────────────────────────────────────────────────────
#  Base class
# ────────────────────────────────────────────────────────────────────


class Probe(ABC):
    """Base class for every attack technique.

    Subclasses must:
      - Set TECHNIQUE to a stable identifier (used in replay_hash).
      - Set MAX_AGGRESSIVENESS to the inherent risk level of this probe
        (also the highest level it may be requested at). The runner uses
        this as both a request ceiling and a charter authorization floor.
      - Implement run() as an async coroutine returning ProbeResult.

    Subclasses must NOT:
      - Make their own decisions about whether to attack — that's
        the charter's job, enforced by the runner.
      - Catch every exception and silently swallow — the runner needs
        to see exceptions to decide whether to retry or abort.
    """

    TECHNIQUE: str = ""
    # Highest aggressiveness level at which this probe is appropriate —
    # also the inherent risk floor used for charter authorization.
    # The native probes here are all L1 (inert / templated) or L2
    # (multi-turn templated). LLM-driven attackers (PAIR/TAP — D3/D4)
    # would be L3, coevolution L4, compositional L5.
    MAX_AGGRESSIVENESS: int = 1

    def __init__(self):
        if not self.TECHNIQUE:
            raise NotImplementedError(
                f"{type(self).__name__} must set TECHNIQUE class attribute"
            )

    @abstractmethod
    async def run(
        self,
        *,
        target_invoke: TargetInvoke,
        seed: int,
        max_turns: int,
        prompt_seed: str | None = None,
    ) -> ProbeResult:
        """Run the probe once.

        Args:
            target_invoke: Async callable: prompt -> response.
            seed: Deterministic seed. Same seed + same prompt_seed must
                reproduce the same prompt sequence.
            max_turns: Hard ceiling on number of turns. Probes that hit
                this should set ProbeResult.aborted_reason.
            prompt_seed: Optional extra input that parametrizes the
                attack (e.g. the AIID incident text for aiid_replay).
        """
        raise NotImplementedError

    def describe(self) -> dict:
        """Static metadata about the technique, for traces and audits."""
        return {
            "technique": self.TECHNIQUE,
            "class": type(self).__name__,
            "max_aggressiveness": self.MAX_AGGRESSIVENESS,
        }
