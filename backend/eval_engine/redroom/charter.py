"""
Mercury Retrograde — Red Room Charter.

This module is the single source of truth for "what kind of adversarial
work is allowed on this platform, by whom, against what, with what
disclosure". Every adversarial endpoint MUST consult this charter before
executing anything.

The charter is intentionally restrictive by default and scope-expanding
through explicit configuration, never through code paths that try to
"figure out if it's allowed". Implicit permission is unsafe permission.

Audit reference: P0-2 (stubbed adversarial engines), §7 (Red Room 2.0).

──────────────────────────────────────────────────────────────────────
  Vocabulary
──────────────────────────────────────────────────────────────────────
  Aggressiveness — integer 1..5, ordered by potential impact on the target:
    L1  inert probes (Garak in static mode, AIID replay against
        deterministic scenarios). No multi-turn, no learning attacker.
    L2  many-shot, Crescendo, prompt-template attacks. Multi-turn but
        no LLM-driven attacker.
    L3  PAIR / TAP / Crescendo-LLM. LLM-driven attacker against the
        target, no learning loop.
    L4  Coevolution (Attacker × Defender × Judge with memory and
        learning). The attacker accumulates strategy across runs.
    L5  Compositional attack on a deployed agentic stack (model +
        tools + memory + RAG). Tests the system, not the model.

  Target class:
    self        Models registered to the caller's own tenant.
    open_weight Public open-weight models running on infrastructure the
                caller has explicit authority over (their own Ollama,
                vLLM, etc.).
    public_api  Closed-weight commercial models accessed via the caller's
                own API key (OpenAI, Anthropic, etc.).
    third_party Anything not in the categories above. NEVER allowed.

  Disclosure track:
    internal    Findings stay within the caller's tenant.
    vendor      Findings auto-generate a Risk Artifact PDF for the
                model vendor (responsible disclosure).
    aiid        Findings are eligible for AIID submission after
                vendor-disclosure window expires.

──────────────────────────────────────────────────────────────────────
  How this interacts with auth
──────────────────────────────────────────────────────────────────────
  The charter sits ABOVE the role check. A user with role=evaluator can
  reach this module; the charter then decides whether their request is
  in scope. Both must pass.
"""
from __future__ import annotations

import dataclasses
import logging
import os
from enum import IntEnum
from typing import Literal

from fastapi import HTTPException

logger = logging.getLogger(__name__)


class Aggressiveness(IntEnum):
    """Ordered intensity. Use the enum, not raw ints, in the codebase."""

    INERT_PROBES = 1
    MULTI_TURN = 2
    LLM_ATTACKER = 3
    COEVOLUTION = 4
    COMPOSITIONAL = 5


TargetClass = Literal["self", "open_weight", "public_api", "third_party"]
DisclosureTrack = Literal["internal", "vendor", "aiid"]


@dataclasses.dataclass(frozen=True)
class CharterPolicy:
    """The current charter values. Frozen — pass copies, don't mutate."""

    # ── Target scope ──────────────────────────────────────────────
    # Which target classes are reachable at all.
    # Default reflects the operator's documented scope: own tenant + own
    # open-weight infrastructure. Closed-weight public APIs require explicit
    # opt-in via REDROOM_ALLOWED_TARGETS=self,open_weight,public_api.
    allowed_targets: frozenset[TargetClass] = frozenset({"self", "open_weight"})

    # ── Aggressiveness scope ──────────────────────────────────────
    # Maximum aggressiveness level that any user can request.
    max_aggressiveness: Aggressiveness = Aggressiveness.MULTI_TURN

    # ── Approval requirements ─────────────────────────────────────
    # Aggressiveness level above which an extra confirmation is required
    # beyond role=evaluator. None = role check is sufficient.
    #
    # Default per operator decision: role=evaluator alone is sufficient at
    # all levels. Operators who want a softer rollout can set
    # REDROOM_REQUIRE_CONSENT_ABOVE to require a UI consent banner above
    # the chosen level.
    require_signed_consent_above: Aggressiveness | None = None

    # Aggressiveness level above which TWO admin approvals are required.
    require_dual_approval_above: Aggressiveness | None = None

    # ── Disclosure ────────────────────────────────────────────────
    # The default disclosure track for findings produced under this charter.
    # Default per operator decision: every finding generates a Risk Artifact
    # PDF for the model vendor (responsible disclosure track).
    default_disclosure: DisclosureTrack = "vendor"

    # If true, findings against public_api targets are auto-routed to
    # vendor disclosure regardless of the requested track.
    force_vendor_disclosure_on_public_api: bool = True

    # ── Operational guards ────────────────────────────────────────
    # Hard ceilings for any single run, regardless of caller request.
    max_tokens_per_run: int = 100_000
    max_duration_seconds: int = 1800  # 30 min
    max_concurrent_runs_per_tenant: int = 2

    # ── Identity ──────────────────────────────────────────────────
    # When false, any attempt to load this module raises. Used to ensure
    # deployments must explicitly opt-in to having a Red Room at all.
    enabled: bool = False


# ────────────────────────────────────────────────────────────────────
#  Charter loading
# ────────────────────────────────────────────────────────────────────


_TARGET_CLASSES: frozenset[str] = frozenset({"self", "open_weight", "public_api"})
# Note: "third_party" is intentionally not a valid configurable value.
# Allowing arbitrary third-party endpoints from env var would let a
# misconfigured deployment attack production systems by accident.


def _parse_target_set(raw: str) -> frozenset[TargetClass]:
    """Parse comma-separated target classes. Reject unknown values."""
    if not raw or not raw.strip():
        return frozenset({"self"})
    parts = {p.strip().lower() for p in raw.split(",") if p.strip()}
    invalid = parts - _TARGET_CLASSES
    if invalid:
        raise ValueError(
            f"REDROOM_ALLOWED_TARGETS contains unknown target class(es): "
            f"{sorted(invalid)}. Allowed: {sorted(_TARGET_CLASSES)}."
        )
    return frozenset(parts)  # type: ignore[arg-type]


def _parse_aggressiveness(raw: str | None, default: Aggressiveness) -> Aggressiveness:
    if raw is None:
        return default
    try:
        n = int(raw)
    except ValueError:
        raise ValueError(f"aggressiveness must be 1..5, got {raw!r}") from None
    if n < 1 or n > 5:
        raise ValueError(f"aggressiveness must be 1..5, got {n}")
    return Aggressiveness(n)


def _parse_optional_aggressiveness(raw: str | None) -> Aggressiveness | None:
    if raw is None or raw.strip() == "" or raw.lower() == "none":
        return None
    return _parse_aggressiveness(raw, Aggressiveness.LLM_ATTACKER)


def _parse_disclosure(raw: str | None, default: DisclosureTrack) -> DisclosureTrack:
    if raw is None or not raw.strip():
        return default
    v = raw.strip().lower()
    if v not in ("internal", "vendor", "aiid"):
        raise ValueError(f"disclosure must be internal/vendor/aiid, got {raw!r}")
    return v  # type: ignore[return-value]


def load_charter() -> CharterPolicy:
    """Build the current policy from env vars. Re-read on each call (no cache)
    so configuration changes take effect on the next request, and so tests
    can monkeypatch.

    Env vars (all optional, restrictive defaults):
      REDROOM_ENABLED                       'true' | 'false' (default false)
      REDROOM_ALLOWED_TARGETS               'self' | 'self,open_weight' | …
      REDROOM_MAX_AGGRESSIVENESS            '1'..'5' (default 2)
      REDROOM_REQUIRE_CONSENT_ABOVE         '1'..'5' or 'none' (default 3)
      REDROOM_REQUIRE_DUAL_APPROVAL_ABOVE   '1'..'5' or 'none' (default none)
      REDROOM_DEFAULT_DISCLOSURE            'internal' | 'vendor' | 'aiid'
      REDROOM_FORCE_VENDOR_ON_PUBLIC_API    'true' | 'false' (default true)
      REDROOM_MAX_TOKENS_PER_RUN            integer (default 100000)
      REDROOM_MAX_DURATION_SECONDS          integer (default 1800)
      REDROOM_MAX_CONCURRENT_PER_TENANT     integer (default 2)
    """
    enabled = os.getenv("REDROOM_ENABLED", "false").lower() in ("true", "1", "yes")

    if not enabled:
        # Return a minimal locked-down policy. Module callers will see
        # enabled=False and refuse to operate.
        return CharterPolicy(enabled=False)

    return CharterPolicy(
        enabled=True,
        allowed_targets=_parse_target_set(
            os.getenv("REDROOM_ALLOWED_TARGETS", "self,open_weight")
        ),
        max_aggressiveness=_parse_aggressiveness(
            os.getenv("REDROOM_MAX_AGGRESSIVENESS"), Aggressiveness.MULTI_TURN
        ),
        require_signed_consent_above=_parse_optional_aggressiveness(
            os.getenv("REDROOM_REQUIRE_CONSENT_ABOVE", "none")
        ),
        require_dual_approval_above=_parse_optional_aggressiveness(
            os.getenv("REDROOM_REQUIRE_DUAL_APPROVAL_ABOVE")
        ),
        default_disclosure=_parse_disclosure(
            os.getenv("REDROOM_DEFAULT_DISCLOSURE"), "vendor"
        ),
        force_vendor_disclosure_on_public_api=os.getenv(
            "REDROOM_FORCE_VENDOR_ON_PUBLIC_API", "true"
        ).lower() in ("true", "1", "yes"),
        max_tokens_per_run=int(os.getenv("REDROOM_MAX_TOKENS_PER_RUN", "100000")),
        max_duration_seconds=int(os.getenv("REDROOM_MAX_DURATION_SECONDS", "1800")),
        max_concurrent_runs_per_tenant=int(
            os.getenv("REDROOM_MAX_CONCURRENT_PER_TENANT", "2")
        ),
    )


# ────────────────────────────────────────────────────────────────────
#  Authorization
# ────────────────────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class AttackRequest:
    """The minimum context needed for charter authorization."""

    target_class: TargetClass
    aggressiveness: Aggressiveness
    has_signed_consent: bool = False
    dual_approval_signers: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class CharterDecision:
    allowed: bool
    reason: str
    effective_disclosure: DisclosureTrack


def authorize(request: AttackRequest, policy: CharterPolicy | None = None) -> CharterDecision:
    """Decide whether this request is allowed under the charter.

    Returns a CharterDecision with allowed=False and a human-readable reason
    when refused. Callers should surface that reason to the user.

    Never raises — returning a clear refusal is preferable to an exception
    so callers handle uniformly.
    """
    p = policy if policy is not None else load_charter()

    if not p.enabled:
        return CharterDecision(
            allowed=False,
            reason=(
                "Red Room is disabled on this deployment. Set REDROOM_ENABLED=true "
                "and configure REDROOM_ALLOWED_TARGETS / REDROOM_MAX_AGGRESSIVENESS "
                "to enable."
            ),
            effective_disclosure="internal",
        )

    if request.target_class == "third_party":
        return CharterDecision(
            allowed=False,
            reason=(
                "Attacks against third-party systems are forbidden. The Red Room "
                "is for measuring robustness on systems the caller has explicit "
                "authority over (own tenant, own infra, own API keys)."
            ),
            effective_disclosure="internal",
        )

    if request.target_class not in p.allowed_targets:
        return CharterDecision(
            allowed=False,
            reason=(
                f"Target class {request.target_class!r} not in this deployment's "
                f"allowed set {sorted(p.allowed_targets)}. Configure "
                f"REDROOM_ALLOWED_TARGETS to expand scope."
            ),
            effective_disclosure="internal",
        )

    if request.aggressiveness > p.max_aggressiveness:
        return CharterDecision(
            allowed=False,
            reason=(
                f"Requested aggressiveness L{request.aggressiveness.value} exceeds "
                f"this deployment's maximum L{p.max_aggressiveness.value}. "
                f"Configure REDROOM_MAX_AGGRESSIVENESS to expand scope."
            ),
            effective_disclosure="internal",
        )

    if (
        p.require_signed_consent_above is not None
        and request.aggressiveness > p.require_signed_consent_above
        and not request.has_signed_consent
    ):
        return CharterDecision(
            allowed=False,
            reason=(
                f"Requested aggressiveness L{request.aggressiveness.value} requires "
                f"signed consent (no consent provided). The user-facing flow must "
                f"surface a confirmation banner before submitting at this level."
            ),
            effective_disclosure="internal",
        )

    if p.require_dual_approval_above is not None and request.aggressiveness > p.require_dual_approval_above:
        if len(request.dual_approval_signers) < 2:
            return CharterDecision(
                allowed=False,
                reason=(
                    f"Requested aggressiveness L{request.aggressiveness.value} requires "
                    f"dual approval (got {len(request.dual_approval_signers)} signers, "
                    f"need 2)."
                ),
                effective_disclosure="internal",
            )

    # Determine the effective disclosure track.
    disclosure = p.default_disclosure
    if request.target_class == "public_api" and p.force_vendor_disclosure_on_public_api:
        # Public API findings escalate to at least vendor disclosure.
        if disclosure == "internal":
            disclosure = "vendor"

    return CharterDecision(
        allowed=True,
        reason="OK",
        effective_disclosure=disclosure,
    )


def enforce(request: AttackRequest, policy: CharterPolicy | None = None) -> CharterDecision:
    """Authorize, raise HTTPException(403) on refusal. Convenience wrapper."""
    decision = authorize(request, policy)
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason)
    return decision


# ────────────────────────────────────────────────────────────────────
#  Startup announcement
# ────────────────────────────────────────────────────────────────────


def announce_charter_at_startup() -> None:
    """Log the current Red Room charter at boot. Called from main.py."""
    p = load_charter()
    if not p.enabled:
        logger.info(
            "[redroom] Charter: DISABLED. Adversarial endpoints will refuse all "
            "requests until REDROOM_ENABLED=true is set."
        )
        return

    logger.warning(
        "[redroom] Charter active: targets=%s, max_aggressiveness=L%d, "
        "consent_above=%s, dual_above=%s, default_disclosure=%s, "
        "max_tokens=%d, max_duration=%ds, max_concurrent=%d",
        sorted(p.allowed_targets),
        p.max_aggressiveness.value,
        f"L{p.require_signed_consent_above.value}" if p.require_signed_consent_above else "None",
        f"L{p.require_dual_approval_above.value}" if p.require_dual_approval_above else "None",
        p.default_disclosure,
        p.max_tokens_per_run,
        p.max_duration_seconds,
        p.max_concurrent_runs_per_tenant,
    )
