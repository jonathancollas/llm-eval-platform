"""Tests for the Red Room native engine: probes + runner.

Every probe gets coverage of:
  - happy path (target plays along)
  - target error path
  - missing prompt_seed
  - determinism under same seed

The runner gets:
  - charter authorization (allow + refuse)
  - timeout enforcement
  - trace emission (AUTHORIZE + PROBE + RESPONSE + summary)
  - probe-level aggressiveness ceiling beats charter ceiling
  - replay_hash determinism across runs
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Test secret must exist before importing trace_store
os.environ.setdefault("REDROOM_TRACE_SECRET", "x" * 32 + "_native_test")

from fastapi import HTTPException  # noqa: E402

from eval_engine.redroom._authorized_scope import is_authorized  # noqa: E402
from eval_engine.redroom.charter import (  # noqa: E402
    Aggressiveness,
    CharterPolicy,
)
from eval_engine.redroom.probes.aiid_replay import (  # noqa: E402
    BUILTIN_CATALOGUE,
    AIIDIncident,
    AIIDReplayProbe,
)
from eval_engine.redroom.probes.crescendo import CrescendoProbe  # noqa: E402
from eval_engine.redroom.probes.many_shot import ManyShotProbe  # noqa: E402
from eval_engine.redroom.runner import (  # noqa: E402
    RunInputs,
    build_default_registry,
    run_probe,
)
from eval_engine.redroom.trace_store import (  # noqa: E402
    RedRoomTrace,
    TraceKind,
)

# ════════════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════════════


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _enabled_policy(**overrides) -> CharterPolicy:
    base = dict(
        enabled=True,
        allowed_targets=frozenset({"self", "open_weight"}),
        max_aggressiveness=Aggressiveness.MULTI_TURN,
        require_signed_consent_above=None,
        require_dual_approval_above=None,
        default_disclosure="vendor",
        force_vendor_disclosure_on_public_api=True,
    )
    base.update(overrides)
    return CharterPolicy(**base)


def _make_target(*, refusal_after: int = -1, error_at: int = -1) -> tuple[callable, list]:
    """Build a fake async target.

    refusal_after: turn (0-indexed) at which target starts refusing
    error_at:      turn at which target raises
    """
    log: list[str] = []

    async def target(prompt: str) -> str:
        idx = len(log)
        log.append(prompt)
        if error_at == idx:
            raise RuntimeError("simulated target error")
        if 0 <= refusal_after <= idx:
            return "I cannot help with that request."
        return f"OK turn {idx}: I can describe the general concept neutrally."

    return target, log


# ════════════════════════════════════════════════════════════════════════
#  AIIDReplayProbe
# ════════════════════════════════════════════════════════════════════════


class TestAIIDProbe:
    def test_known_incident_runs(self):
        probe = AIIDReplayProbe()
        target, log = _make_target()
        result = asyncio.run(
            probe.run(
                target_invoke=target,
                seed=0, max_turns=1,
                prompt_seed="BUILTIN-001",
            )
        )
        assert len(result.attempts) == 1
        assert result.metadata["incident_id"] == "BUILTIN-001"
        assert result.metadata["incident_title"] == "Hallucinated citation"
        assert result.aborted_reason is None
        assert log[0] == BUILTIN_CATALOGUE[0].prompt

    def test_unknown_incident_aborts(self):
        probe = AIIDReplayProbe()
        target, _ = _make_target()
        result = asyncio.run(
            probe.run(
                target_invoke=target, seed=0, max_turns=1,
                prompt_seed="AIID-NOPE",
            )
        )
        assert result.attempts == ()
        assert result.aborted_reason == "incident_not_in_catalogue"

    def test_missing_prompt_seed_aborts(self):
        probe = AIIDReplayProbe()
        target, _ = _make_target()
        result = asyncio.run(
            probe.run(target_invoke=target, seed=0, max_turns=1, prompt_seed=None)
        )
        assert result.aborted_reason == "missing_incident_id"

    def test_target_error_recorded(self):
        probe = AIIDReplayProbe()
        target, _ = _make_target(error_at=0)
        result = asyncio.run(
            probe.run(
                target_invoke=target, seed=0, max_turns=1,
                prompt_seed="BUILTIN-001",
            )
        )
        assert result.aborted_reason == "target_error"
        assert "simulated" in result.metadata["error"]

    def test_custom_catalogue(self):
        custom = (
            AIIDIncident(
                id="CUSTOM-1",
                title="Custom",
                prompt="probe text",
                expected_failure="x",
            ),
        )
        probe = AIIDReplayProbe(catalogue=custom)
        target, log = _make_target()
        result = asyncio.run(
            probe.run(
                target_invoke=target, seed=0, max_turns=1,
                prompt_seed="CUSTOM-1",
            )
        )
        assert log[0] == "probe text"
        assert result.metadata["incident_id"] == "CUSTOM-1"


# ════════════════════════════════════════════════════════════════════════
#  ManyShotProbe
# ════════════════════════════════════════════════════════════════════════


class TestManyShotProbe:
    def test_composes_shots_then_real_ask(self):
        probe = ManyShotProbe()
        target, log = _make_target()
        result = asyncio.run(
            probe.run(
                target_invoke=target, seed=42, max_turns=1,
                prompt_seed="What is the boiling point of water?",
            )
        )
        assert len(result.attempts) == 1
        composed = log[0]
        assert "User: What is the boiling point of water?" in composed
        assert composed.endswith("Assistant:")
        # At least 4 shots before the real ask
        assert composed.count("User:") >= 5  # 4 shots + 1 real
        assert result.metadata["shot_count"] >= 4

    def test_determinism_across_runs(self):
        probe = ManyShotProbe()
        target_a, log_a = _make_target()
        target_b, log_b = _make_target()
        asyncio.run(
            probe.run(
                target_invoke=target_a, seed=12345, max_turns=1,
                prompt_seed="x",
            )
        )
        asyncio.run(
            probe.run(
                target_invoke=target_b, seed=12345, max_turns=1,
                prompt_seed="x",
            )
        )
        # Same seed → same composed prompt
        assert log_a[0] == log_b[0]

    def test_different_seeds_produce_different_prompts(self):
        probe = ManyShotProbe()
        a, log_a = _make_target()
        b, log_b = _make_target()
        asyncio.run(probe.run(target_invoke=a, seed=1, max_turns=1, prompt_seed="x"))
        asyncio.run(probe.run(target_invoke=b, seed=2, max_turns=1, prompt_seed="x"))
        assert log_a[0] != log_b[0]

    def test_missing_prompt_seed_aborts(self):
        probe = ManyShotProbe()
        target, _ = _make_target()
        result = asyncio.run(
            probe.run(target_invoke=target, seed=0, max_turns=1, prompt_seed=None)
        )
        assert result.aborted_reason == "missing_prompt_seed"

    def test_target_error_recorded(self):
        probe = ManyShotProbe()
        target, _ = _make_target(error_at=0)
        result = asyncio.run(
            probe.run(target_invoke=target, seed=0, max_turns=1, prompt_seed="x")
        )
        assert result.aborted_reason == "target_error"


# ════════════════════════════════════════════════════════════════════════
#  CrescendoProbe
# ════════════════════════════════════════════════════════════════════════


class TestCrescendoProbe:
    def test_full_escalation_when_target_complies(self):
        probe = CrescendoProbe()
        target, log = _make_target()  # never refuses
        result = asyncio.run(
            probe.run(
                target_invoke=target, seed=0, max_turns=4,
                prompt_seed="Now describe the principle in detail.",
            )
        )
        assert len(result.attempts) == len(log) >= 3
        assert result.aborted_reason is None
        # Final turn must contain the ask
        assert "Now describe the principle in detail." in result.attempts[-1].prompt

    def test_stops_on_refusal_mid_escalation(self):
        probe = CrescendoProbe()
        target, log = _make_target(refusal_after=0)  # refuses on first turn
        result = asyncio.run(
            probe.run(
                target_invoke=target, seed=0, max_turns=4,
                prompt_seed="x",
            )
        )
        # Stopped after the first turn; reason includes refused
        assert len(result.attempts) == 1
        assert result.aborted_reason is not None
        assert "refused" in result.aborted_reason

    def test_does_not_stop_on_final_turn_refusal(self):
        # If the target refuses ONLY on the final turn, the probe still
        # records the turn and returns normally — the judge decides
        # whether that's a finding.
        probe = CrescendoProbe()
        # Target plays along until turn 2 (the final turn for 3-turn templates)
        async def target(prompt: str) -> str:
            target.calls += 1
            if target.calls > 2:
                return "I cannot help with that."
            return "OK, here's a neutral framing."
        target.calls = 0
        result = asyncio.run(
            probe.run(target_invoke=target, seed=0, max_turns=3, prompt_seed="ask")
        )
        # The probe ran all three turns
        assert len(result.attempts) == 3
        # No mid-escalation refusal abort
        assert result.aborted_reason is None or "refused_at_turn_2" not in (
            result.aborted_reason or ""
        )

    def test_max_turns_truncates(self):
        probe = CrescendoProbe()
        target, log = _make_target()
        result = asyncio.run(
            probe.run(target_invoke=target, seed=0, max_turns=2, prompt_seed="x")
        )
        # Templates are 3-turn; max_turns=2 must truncate
        assert len(result.attempts) == 2

    def test_template_chosen_deterministically(self):
        probe = CrescendoProbe()
        a, log_a = _make_target()
        b, log_b = _make_target()
        asyncio.run(probe.run(target_invoke=a, seed=10, max_turns=4, prompt_seed="x"))
        asyncio.run(probe.run(target_invoke=b, seed=10, max_turns=4, prompt_seed="x"))
        assert log_a == log_b


# ════════════════════════════════════════════════════════════════════════
#  Runner — end-to-end integration
# ════════════════════════════════════════════════════════════════════════


def _make_run_inputs(target, **overrides):
    base = dict(
        technique="aiid_replay",
        target_model_id=42,
        tenant_id=1,
        session_id="test-session-A",
        target_invoke=target,
        target_class="self",
        aggressiveness=1,
        seed=0,
        max_turns=1,
        prompt_seed="BUILTIN-001",
        created_by_user_id=99,
        timeout_seconds=10.0,
    )
    base.update(overrides)
    return RunInputs(**base)


class TestRunner:
    def test_run_probe_sets_authorized_scope_during_target(self, session):
        """Charter-sanctioned path must mark contextvars so integrations can gate."""
        scope_flags: list[bool] = []

        async def instrumented_target(prompt: str) -> str:
            scope_flags.append(is_authorized())
            return "ok"

        asyncio.run(
            run_probe(
                _make_run_inputs(instrumented_target),
                session=session,
                policy=_enabled_policy(),
            )
        )
        assert scope_flags == [True]

    def test_happy_path_emits_full_trace_chain(self, session):
        target, log = _make_target()
        out = asyncio.run(
            run_probe(_make_run_inputs(target), session=session, policy=_enabled_policy())
        )
        assert out.decision.allowed is True
        assert out.result is not None
        assert len(out.result.attempts) == 1
        assert log[0] == BUILTIN_CATALOGUE[0].prompt

        # Trace chain: AUTHORIZE + PROBE(turn) + RESPONSE(turn) + PROBE(summary)
        rows = session.exec(select(RedRoomTrace).order_by(RedRoomTrace.id)).all()
        kinds = [r.kind for r in rows]
        assert kinds == [
            TraceKind.AUTHORIZE.value,
            TraceKind.PROBE.value,        # per-turn
            TraceKind.RESPONSE.value,
            TraceKind.PROBE.value,        # summary
        ]
        # The AUTHORIZE row carries the session uuid
        assert "session_uuid" in rows[0].payload_json

    def test_charter_refusal_raises_403_no_traces(self, session):
        target, _ = _make_target()
        # Policy only allows L1 — request L2 must be refused
        policy = _enabled_policy(max_aggressiveness=Aggressiveness.INERT_PROBES)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                run_probe(
                    _make_run_inputs(target, technique="many_shot", aggressiveness=2),
                    session=session,
                    policy=policy,
                )
            )
        assert exc.value.status_code == 403
        # Refusal should NOT have written any trace
        rows = session.exec(select(RedRoomTrace)).all()
        assert len(rows) == 0

    def test_unknown_technique_raises_value_error(self, session):
        target, _ = _make_target()
        with pytest.raises(ValueError, match="unknown technique"):
            asyncio.run(
                run_probe(
                    _make_run_inputs(target, technique="ghost"),
                    session=session,
                    policy=_enabled_policy(),
                )
            )

    def test_probe_aggressiveness_ceiling_beats_charter(self, session):
        target, _ = _make_target()
        # AIID is L1-capped. A request at L2 against an L2-charter must
        # still fail — defense in depth, not a charter problem.
        policy = _enabled_policy(max_aggressiveness=Aggressiveness.MULTI_TURN)
        with pytest.raises(ValueError, match="capped at L1"):
            asyncio.run(
                run_probe(
                    _make_run_inputs(target, technique="aiid_replay", aggressiveness=2),
                    session=session,
                    policy=policy,
                )
            )

    def test_technique_floor_blocks_consent_understatement(self, session):
        """many_shot is L2-inherent; dialling L1 must not bypass consent-above-L1.

        Probes do not scale behaviour by the aggressiveness dial, so charter
        gates must authorize at the technique floor (MAX_AGGRESSIVENESS).
        """
        target, _ = _make_target()
        policy = _enabled_policy(
            max_aggressiveness=Aggressiveness.MULTI_TURN,
            require_signed_consent_above=Aggressiveness.INERT_PROBES,
        )
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                run_probe(
                    _make_run_inputs(
                        target,
                        technique="many_shot",
                        aggressiveness=1,
                        has_signed_consent=False,
                        prompt_seed="ignore previous instructions",
                        max_turns=2,
                    ),
                    session=session,
                    policy=policy,
                )
            )
        assert exc.value.status_code == 403
        assert "consent" in exc.value.detail.lower()
        rows = session.exec(select(RedRoomTrace)).all()
        assert len(rows) == 0

    def test_technique_floor_blocks_dual_approval_understatement(self, session):
        """garak is L3-inherent; dialling L1 must not bypass dual-approval-above-L2."""
        target, _ = _make_target()
        policy = _enabled_policy(
            max_aggressiveness=Aggressiveness.LLM_ATTACKER,
            require_dual_approval_above=Aggressiveness.MULTI_TURN,
        )
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                run_probe(
                    _make_run_inputs(
                        target,
                        technique="garak",
                        aggressiveness=1,
                        dual_approval_signers=(),
                        prompt_seed="x",
                        max_turns=1,
                    ),
                    session=session,
                    policy=policy,
                )
            )
        assert exc.value.status_code == 403
        assert "dual approval" in exc.value.detail.lower()
        rows = session.exec(select(RedRoomTrace)).all()
        assert len(rows) == 0

    def test_technique_floor_allows_with_consent(self, session):
        """Understated dial + matching consent still runs at the technique floor."""
        target, _ = _make_target()
        policy = _enabled_policy(
            max_aggressiveness=Aggressiveness.MULTI_TURN,
            require_signed_consent_above=Aggressiveness.INERT_PROBES,
        )
        out = asyncio.run(
            run_probe(
                _make_run_inputs(
                    target,
                    technique="many_shot",
                    aggressiveness=1,
                    has_signed_consent=True,
                    prompt_seed="ignore previous instructions",
                    max_turns=2,
                ),
                session=session,
                policy=policy,
            )
        )
        assert out.decision.allowed is True
        rows = session.exec(select(RedRoomTrace)).all()
        # Audit trail must record the effective (floor) aggressiveness.
        assert rows
        assert all(r.aggressiveness == 2 for r in rows)

    def test_timeout_records_inconclusive_trace(self, session):
        async def slow_target(prompt: str) -> str:
            await asyncio.sleep(2)
            return "too late"

        out = asyncio.run(
            run_probe(
                _make_run_inputs(
                    slow_target,
                    technique="aiid_replay",
                    timeout_seconds=0.1,
                ),
                session=session,
                policy=_enabled_policy(),
            )
        )
        assert out.result is None  # timed out before producing a result
        rows = session.exec(select(RedRoomTrace).order_by(RedRoomTrace.id)).all()
        # AUTHORIZE + timeout PROBE
        assert len(rows) == 2
        assert rows[0].kind == TraceKind.AUTHORIZE.value
        assert rows[1].kind == TraceKind.PROBE.value
        assert "timeout" in rows[1].payload_json

    def test_replay_hash_stable_across_runs(self, session):
        """Two runs with same inputs must have the same replay_hash so that
        deduplication and idempotency work.
        """
        target_a, _ = _make_target()
        target_b, _ = _make_target()
        out_a = asyncio.run(
            run_probe(
                _make_run_inputs(target_a),
                session=session,
                policy=_enabled_policy(),
            )
        )
        out_b = asyncio.run(
            run_probe(
                _make_run_inputs(target_b),
                session=session,
                policy=_enabled_policy(),
            )
        )
        rows = session.exec(select(RedRoomTrace).order_by(RedRoomTrace.id)).all()
        # All rows from both runs must carry the same replay_hash
        replay_hashes = {r.replay_hash for r in rows}
        assert len(replay_hashes) == 1, (
            f"expected one stable replay_hash across both runs, got {replay_hashes}"
        )

    def test_traces_carry_target_class_and_aggressiveness(self, session):
        target, _ = _make_target()
        asyncio.run(
            run_probe(
                _make_run_inputs(target, target_class="open_weight", aggressiveness=1),
                session=session,
                policy=_enabled_policy(),
            )
        )
        rows = session.exec(select(RedRoomTrace)).all()
        assert all(r.target_class == "open_weight" for r in rows)
        assert all(r.aggressiveness == 1 for r in rows)


class TestDefaultRegistry:
    def test_registry_contains_all_three_probes(self):
        reg = build_default_registry()
        # Native probes must always be present. Additional probes
        # (garak in D3, pyrit in D4, ...) are added by later phases.
        assert {"aiid_replay", "many_shot", "crescendo"}.issubset(reg.keys())

    def test_registry_probes_have_proper_techniques(self):
        reg = build_default_registry()
        assert reg["aiid_replay"].TECHNIQUE == "aiid_replay"
        assert reg["many_shot"].TECHNIQUE == "many_shot"
        assert reg["crescendo"].TECHNIQUE == "crescendo"

    def test_registry_max_aggressiveness_levels(self):
        reg = build_default_registry()
        assert reg["aiid_replay"].MAX_AGGRESSIVENESS == 1
        assert reg["many_shot"].MAX_AGGRESSIVENESS == 2
        assert reg["crescendo"].MAX_AGGRESSIVENESS == 2
