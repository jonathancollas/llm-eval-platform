"""Tests for the Red Room charter authorization logic.

Every branch of the authorization decision tree must be exercised. The
charter is the single security gate for the entire adversarial subsystem,
so the test suite is intentionally exhaustive.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval_engine.redroom.charter import (  # noqa: E402
    Aggressiveness,
    AttackRequest,
    CharterPolicy,
    authorize,
    enforce,
    load_charter,
    _parse_target_set,
    _parse_aggressiveness,
    _parse_optional_aggressiveness,
)
from fastapi import HTTPException  # noqa: E402


# ════════════════════════════════════════════════════════════════════════
#  load_charter — env var parsing
# ════════════════════════════════════════════════════════════════════════


class TestEnvLoading:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("REDROOM_ENABLED", raising=False)
        p = load_charter()
        assert p.enabled is False

    def test_explicit_disable_returns_locked_policy(self, monkeypatch):
        monkeypatch.setenv("REDROOM_ENABLED", "false")
        p = load_charter()
        assert p.enabled is False

    def test_enable_with_defaults(self, monkeypatch):
        monkeypatch.setenv("REDROOM_ENABLED", "true")
        for k in (
            "REDROOM_ALLOWED_TARGETS",
            "REDROOM_MAX_AGGRESSIVENESS",
            "REDROOM_REQUIRE_CONSENT_ABOVE",
            "REDROOM_REQUIRE_DUAL_APPROVAL_ABOVE",
            "REDROOM_DEFAULT_DISCLOSURE",
        ):
            monkeypatch.delenv(k, raising=False)
        p = load_charter()
        assert p.enabled is True
        # Operator-decided defaults: self + own open-weight infra,
        # role-only gating, vendor disclosure track for every finding.
        assert p.allowed_targets == frozenset({"self", "open_weight"})
        assert p.max_aggressiveness == Aggressiveness.MULTI_TURN
        assert p.require_signed_consent_above is None
        assert p.require_dual_approval_above is None
        assert p.default_disclosure == "vendor"

    def test_enable_with_full_config(self, monkeypatch):
        monkeypatch.setenv("REDROOM_ENABLED", "true")
        monkeypatch.setenv("REDROOM_ALLOWED_TARGETS", "self,open_weight,public_api")
        monkeypatch.setenv("REDROOM_MAX_AGGRESSIVENESS", "5")
        monkeypatch.setenv("REDROOM_REQUIRE_CONSENT_ABOVE", "2")
        monkeypatch.setenv("REDROOM_REQUIRE_DUAL_APPROVAL_ABOVE", "4")
        monkeypatch.setenv("REDROOM_DEFAULT_DISCLOSURE", "vendor")
        monkeypatch.setenv("REDROOM_FORCE_VENDOR_ON_PUBLIC_API", "false")
        monkeypatch.setenv("REDROOM_MAX_TOKENS_PER_RUN", "50000")
        monkeypatch.setenv("REDROOM_MAX_DURATION_SECONDS", "600")
        monkeypatch.setenv("REDROOM_MAX_CONCURRENT_PER_TENANT", "1")

        p = load_charter()
        assert p.enabled is True
        assert p.allowed_targets == frozenset({"self", "open_weight", "public_api"})
        assert p.max_aggressiveness == Aggressiveness.COMPOSITIONAL
        assert p.require_signed_consent_above == Aggressiveness.MULTI_TURN
        assert p.require_dual_approval_above == Aggressiveness.COEVOLUTION
        assert p.default_disclosure == "vendor"
        assert p.force_vendor_disclosure_on_public_api is False
        assert p.max_tokens_per_run == 50_000
        assert p.max_duration_seconds == 600
        assert p.max_concurrent_runs_per_tenant == 1


class TestParsing:
    def test_target_set_default(self):
        assert _parse_target_set("") == frozenset({"self"})
        assert _parse_target_set("   ") == frozenset({"self"})

    def test_target_set_single(self):
        assert _parse_target_set("self") == frozenset({"self"})

    def test_target_set_multi(self):
        assert _parse_target_set("self, open_weight ") == frozenset(
            {"self", "open_weight"}
        )

    def test_target_set_rejects_unknown(self):
        with pytest.raises(ValueError, match="unknown target class"):
            _parse_target_set("self,evil_systems")

    def test_target_set_rejects_third_party(self):
        # "third_party" must NEVER be configurable from env, even by mistake.
        with pytest.raises(ValueError, match="unknown target class"):
            _parse_target_set("third_party")

    def test_aggressiveness_clamped(self):
        with pytest.raises(ValueError):
            _parse_aggressiveness("0", Aggressiveness.MULTI_TURN)
        with pytest.raises(ValueError):
            _parse_aggressiveness("6", Aggressiveness.MULTI_TURN)
        with pytest.raises(ValueError):
            _parse_aggressiveness("foo", Aggressiveness.MULTI_TURN)

    def test_optional_aggressiveness_none(self):
        assert _parse_optional_aggressiveness(None) is None
        assert _parse_optional_aggressiveness("") is None
        assert _parse_optional_aggressiveness("none") is None
        assert _parse_optional_aggressiveness("None") is None


# ════════════════════════════════════════════════════════════════════════
#  authorize() — the security-critical decision tree
# ════════════════════════════════════════════════════════════════════════


def _enabled_policy(**overrides) -> CharterPolicy:
    """Build an enabled CharterPolicy with overrides."""
    base = dict(
        enabled=True,
        allowed_targets=frozenset({"self"}),
        max_aggressiveness=Aggressiveness.MULTI_TURN,
        require_signed_consent_above=None,
        require_dual_approval_above=None,
        default_disclosure="internal",
        force_vendor_disclosure_on_public_api=True,
    )
    base.update(overrides)
    return CharterPolicy(**base)


class TestDisabled:
    def test_disabled_charter_refuses_everything(self):
        p = CharterPolicy(enabled=False)
        d = authorize(
            AttackRequest(
                target_class="self",
                aggressiveness=Aggressiveness.INERT_PROBES,
            ),
            p,
        )
        assert d.allowed is False
        assert "disabled" in d.reason.lower()


class TestThirdParty:
    @pytest.mark.parametrize(
        "agg",
        [Aggressiveness.INERT_PROBES, Aggressiveness.COMPOSITIONAL],
    )
    def test_third_party_always_refused(self, agg):
        # Even with a fully-permissive charter, third_party is hardcoded refused.
        p = _enabled_policy(
            allowed_targets=frozenset({"self", "open_weight", "public_api"}),
            max_aggressiveness=Aggressiveness.COMPOSITIONAL,
        )
        d = authorize(
            AttackRequest(target_class="third_party", aggressiveness=agg),
            p,
        )
        assert d.allowed is False
        assert "third-party" in d.reason.lower() or "third_party" in d.reason.lower()


class TestTargetClass:
    def test_self_default_works(self):
        p = _enabled_policy()
        d = authorize(
            AttackRequest(
                target_class="self",
                aggressiveness=Aggressiveness.INERT_PROBES,
            ),
            p,
        )
        assert d.allowed is True

    def test_open_weight_refused_when_not_allowed(self):
        p = _enabled_policy(allowed_targets=frozenset({"self"}))
        d = authorize(
            AttackRequest(
                target_class="open_weight",
                aggressiveness=Aggressiveness.INERT_PROBES,
            ),
            p,
        )
        assert d.allowed is False
        assert "not in this deployment" in d.reason

    def test_open_weight_allowed_when_configured(self):
        p = _enabled_policy(allowed_targets=frozenset({"self", "open_weight"}))
        d = authorize(
            AttackRequest(
                target_class="open_weight",
                aggressiveness=Aggressiveness.INERT_PROBES,
            ),
            p,
        )
        assert d.allowed is True


class TestAggressiveness:
    def test_at_or_below_max_allowed(self):
        p = _enabled_policy(max_aggressiveness=Aggressiveness.LLM_ATTACKER)
        for level in (
            Aggressiveness.INERT_PROBES,
            Aggressiveness.MULTI_TURN,
            Aggressiveness.LLM_ATTACKER,
        ):
            d = authorize(
                AttackRequest(target_class="self", aggressiveness=level),
                p,
            )
            assert d.allowed is True, f"L{level.value} should be allowed"

    def test_above_max_refused(self):
        p = _enabled_policy(max_aggressiveness=Aggressiveness.LLM_ATTACKER)
        d = authorize(
            AttackRequest(
                target_class="self",
                aggressiveness=Aggressiveness.COEVOLUTION,
            ),
            p,
        )
        assert d.allowed is False
        assert "exceeds" in d.reason


class TestSignedConsent:
    def test_required_above_threshold_blocks_without(self):
        p = _enabled_policy(
            max_aggressiveness=Aggressiveness.COEVOLUTION,
            require_signed_consent_above=Aggressiveness.MULTI_TURN,
        )
        d = authorize(
            AttackRequest(
                target_class="self",
                aggressiveness=Aggressiveness.LLM_ATTACKER,
                has_signed_consent=False,
            ),
            p,
        )
        assert d.allowed is False
        assert "consent" in d.reason.lower()

    def test_required_above_threshold_allowed_with(self):
        p = _enabled_policy(
            max_aggressiveness=Aggressiveness.COEVOLUTION,
            require_signed_consent_above=Aggressiveness.MULTI_TURN,
        )
        d = authorize(
            AttackRequest(
                target_class="self",
                aggressiveness=Aggressiveness.LLM_ATTACKER,
                has_signed_consent=True,
            ),
            p,
        )
        assert d.allowed is True

    def test_at_or_below_threshold_no_consent_needed(self):
        p = _enabled_policy(
            max_aggressiveness=Aggressiveness.COEVOLUTION,
            require_signed_consent_above=Aggressiveness.MULTI_TURN,
        )
        d = authorize(
            AttackRequest(
                target_class="self",
                aggressiveness=Aggressiveness.MULTI_TURN,
                has_signed_consent=False,
            ),
            p,
        )
        assert d.allowed is True


class TestDualApproval:
    def test_required_blocks_with_zero_signers(self):
        p = _enabled_policy(
            max_aggressiveness=Aggressiveness.COMPOSITIONAL,
            require_dual_approval_above=Aggressiveness.LLM_ATTACKER,
        )
        d = authorize(
            AttackRequest(
                target_class="self",
                aggressiveness=Aggressiveness.COEVOLUTION,
                dual_approval_signers=(),
            ),
            p,
        )
        assert d.allowed is False
        assert "dual approval" in d.reason.lower()

    def test_required_blocks_with_one_signer(self):
        p = _enabled_policy(
            max_aggressiveness=Aggressiveness.COMPOSITIONAL,
            require_dual_approval_above=Aggressiveness.LLM_ATTACKER,
        )
        d = authorize(
            AttackRequest(
                target_class="self",
                aggressiveness=Aggressiveness.COEVOLUTION,
                dual_approval_signers=("alice@example.com",),
            ),
            p,
        )
        assert d.allowed is False

    def test_passes_with_two_signers(self):
        p = _enabled_policy(
            max_aggressiveness=Aggressiveness.COMPOSITIONAL,
            require_dual_approval_above=Aggressiveness.LLM_ATTACKER,
        )
        d = authorize(
            AttackRequest(
                target_class="self",
                aggressiveness=Aggressiveness.COEVOLUTION,
                dual_approval_signers=("alice@example.com", "bob@example.com"),
            ),
            p,
        )
        assert d.allowed is True


class TestDisclosure:
    def test_default_track_used(self):
        p = _enabled_policy(default_disclosure="vendor")
        d = authorize(
            AttackRequest(
                target_class="self",
                aggressiveness=Aggressiveness.INERT_PROBES,
            ),
            p,
        )
        assert d.allowed is True
        assert d.effective_disclosure == "vendor"

    def test_public_api_force_vendor_disclosure(self):
        p = _enabled_policy(
            allowed_targets=frozenset({"self", "public_api"}),
            default_disclosure="internal",
            force_vendor_disclosure_on_public_api=True,
        )
        d = authorize(
            AttackRequest(
                target_class="public_api",
                aggressiveness=Aggressiveness.INERT_PROBES,
            ),
            p,
        )
        assert d.allowed is True
        # internal got upgraded to vendor for public_api targets
        assert d.effective_disclosure == "vendor"

    def test_public_api_no_force_keeps_internal(self):
        p = _enabled_policy(
            allowed_targets=frozenset({"self", "public_api"}),
            default_disclosure="internal",
            force_vendor_disclosure_on_public_api=False,
        )
        d = authorize(
            AttackRequest(
                target_class="public_api",
                aggressiveness=Aggressiveness.INERT_PROBES,
            ),
            p,
        )
        assert d.allowed is True
        assert d.effective_disclosure == "internal"

    def test_public_api_force_does_not_downgrade_aiid(self):
        # aiid is stronger than vendor, must not be downgraded.
        p = _enabled_policy(
            allowed_targets=frozenset({"self", "public_api"}),
            default_disclosure="aiid",
            force_vendor_disclosure_on_public_api=True,
        )
        d = authorize(
            AttackRequest(
                target_class="public_api",
                aggressiveness=Aggressiveness.INERT_PROBES,
            ),
            p,
        )
        assert d.allowed is True
        assert d.effective_disclosure == "aiid"


# ════════════════════════════════════════════════════════════════════════
#  enforce() — the FastAPI integration helper
# ════════════════════════════════════════════════════════════════════════


class TestEnforceWrapper:
    def test_allowed_returns_decision(self):
        p = _enabled_policy()
        d = enforce(
            AttackRequest(
                target_class="self",
                aggressiveness=Aggressiveness.INERT_PROBES,
            ),
            p,
        )
        assert d.allowed is True

    def test_refused_raises_403(self):
        p = _enabled_policy()
        with pytest.raises(HTTPException) as exc_info:
            enforce(
                AttackRequest(
                    target_class="self",
                    aggressiveness=Aggressiveness.COMPOSITIONAL,
                ),
                p,
            )
        assert exc_info.value.status_code == 403
        assert "exceeds" in exc_info.value.detail


# ════════════════════════════════════════════════════════════════════════
#  Defense-in-depth: ordering of checks
# ════════════════════════════════════════════════════════════════════════


class TestCheckOrdering:
    """The order in which the charter checks rules matters for clear UX
    error messages. Verify the order: enabled > target > aggressiveness >
    consent > dual approval.
    """

    def test_disabled_beats_target(self):
        p = CharterPolicy(enabled=False)
        d = authorize(
            AttackRequest(
                target_class="third_party",
                aggressiveness=Aggressiveness.COMPOSITIONAL,
            ),
            p,
        )
        assert "disabled" in d.reason.lower()

    def test_target_beats_aggressiveness(self):
        p = _enabled_policy(
            max_aggressiveness=Aggressiveness.INERT_PROBES,
            allowed_targets=frozenset({"self"}),
        )
        d = authorize(
            AttackRequest(
                target_class="open_weight",
                aggressiveness=Aggressiveness.COMPOSITIONAL,
            ),
            p,
        )
        # Target refusal should win over aggressiveness refusal
        assert "not in this deployment" in d.reason

    def test_aggressiveness_beats_consent(self):
        p = _enabled_policy(
            max_aggressiveness=Aggressiveness.MULTI_TURN,
            require_signed_consent_above=Aggressiveness.INERT_PROBES,
        )
        d = authorize(
            AttackRequest(
                target_class="self",
                aggressiveness=Aggressiveness.COMPOSITIONAL,
                has_signed_consent=False,
            ),
            p,
        )
        # Hitting the max ceiling is reported, not the consent gap
        assert "exceeds" in d.reason
