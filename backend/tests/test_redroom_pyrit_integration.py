"""Tests for the D4 PyRIT integration (PAIR + TAP).

Covers:
  - Allowlist enforcement on technique names
  - Subprocess sandbox refuses metacharacters and times out
  - PAIR algorithm: success path, budget exhaustion, attacker errors
  - TAP algorithm: branching, pruning, beam-width respected
  - PyRITProbe contract (Probe interface, prompt_seed JSON parsing)
  - Charter + trace integration via run_probe()
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("REDROOM_TRACE_SECRET", "x" * 32 + "_test_secret")
os.environ["REDROOM_ENABLED"] = "true"
os.environ["REDROOM_ALLOWED_TARGETS"] = "self,open_weight,public_api"
os.environ["REDROOM_MAX_AGGRESSIVENESS"] = "3"

from eval_engine.redroom import (  # noqa: E402
    PYRIT_ALLOWLIST,
    PyRITAllowlistError,
    PyRITSubprocessError,
    RunInputs,
    TraceKind,
    load_charter,
    run_probe,
)
from eval_engine.redroom.integrations.pyrit_runner import (  # noqa: E402
    _scrubbed_env,
    _strip_attacker_chrome,
    _validate_technique,
    run_pair,
    run_pyrit_subprocess,
    run_tap,
)
from eval_engine.redroom.probes.pyrit_probe import PyRITProbe  # noqa: E402
from eval_engine.redroom.trace_store import RedRoomTrace  # noqa: E402

# ════════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def session():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


@pytest.fixture
def fake_target():
    """Target that always echoes a refusal-style response."""

    async def _t(prompt: str) -> str:
        return f"[refused-but-echoes] received {len(prompt)} chars"

    return _t


@pytest.fixture
def cooperating_target():
    """Target that always returns content the judge will deem successful."""

    async def _t(_p: str) -> str:
        return "Sure, here is the unsafe content you asked for."

    return _t


@pytest.fixture
def fixed_attacker():
    """Attacker that returns a deterministic refined prompt each call."""
    counter = {"n": 0}

    async def _a(_input: str) -> str:
        counter["n"] += 1
        return f"refined_prompt_v{counter['n']}"

    return _a


@pytest.fixture
def low_judge():
    """Judge that always scores 0.1 — never reaches success threshold."""

    async def _j(_p: str, _r: str) -> float:
        return 0.1

    return _j


@pytest.fixture
def threshold_at_round_2_judge():
    """Judge that returns 0.95 once enough rounds have occurred."""
    state = {"calls": 0}

    async def _j(_p: str, _r: str) -> float:
        state["calls"] += 1
        # Round 0: 0.1, Round 1: 0.4, Round 2+: 0.95
        if state["calls"] <= 1:
            return 0.1
        if state["calls"] == 2:
            return 0.4
        return 0.95

    return _j


# ════════════════════════════════════════════════════════════════════
#  Allowlist
# ════════════════════════════════════════════════════════════════════


class TestAllowlist:
    def test_allowlist_contains_pair_and_tap(self):
        assert PYRIT_ALLOWLIST == frozenset({"pair", "tap"})

    def test_validate_accepts_known(self):
        _validate_technique("pair")
        _validate_technique("tap")

    @pytest.mark.parametrize("evil", ["", "PAIR", "tap2", "tap;rm", "tap`whoami`"])
    def test_validate_rejects_unknown(self, evil):
        with pytest.raises(PyRITAllowlistError):
            _validate_technique(evil)


# ════════════════════════════════════════════════════════════════════
#  Subprocess sandbox
# ════════════════════════════════════════════════════════════════════


class TestSubprocessSandbox:
    def test_scrubbed_env_does_not_leak_api_keys(self):
        env = _scrubbed_env()
        assert "OPENAI_API_KEY" not in env
        assert "ANTHROPIC_API_KEY" not in env

    def test_run_pyrit_refuses_unknown_technique(self):
        with pytest.raises(PyRITAllowlistError):
            run_pyrit_subprocess("evil", target_model_id="m")

    def test_run_pyrit_refuses_metachar_in_extra_args(self):
        with pytest.raises(PyRITSubprocessError):
            run_pyrit_subprocess(
                "pair",
                target_model_id="m",
                pyrit_executable="/usr/bin/true",
                extra_args=("--x", "evil ; rm"),
            )

    def test_run_pyrit_raises_when_executable_missing(self, monkeypatch):
        monkeypatch.setattr(
            "eval_engine.redroom.integrations.pyrit_runner.shutil.which",
            lambda _: None,
        )
        with pytest.raises(PyRITSubprocessError, match="not found"):
            run_pyrit_subprocess("pair", target_model_id="m")

    def test_run_pyrit_propagates_timeout(self, tmp_path):
        fake = tmp_path / "fake.sh"
        fake.write_text("#!/bin/sh\nsleep 5\n")
        fake.chmod(0o755)
        with pytest.raises(PyRITSubprocessError, match="timed out"):
            run_pyrit_subprocess(
                "pair",
                target_model_id="m",
                pyrit_executable=str(fake),
                timeout_seconds=1,
            )

    def test_run_pyrit_returns_diag_on_success(self, tmp_path):
        fake = tmp_path / "fake.sh"
        fake.write_text("#!/bin/sh\necho ok\nexit 0\n")
        fake.chmod(0o755)
        out = run_pyrit_subprocess(
            "pair", target_model_id="m", pyrit_executable=str(fake)
        )
        assert "ok" in out["stdout_tail"]


# ════════════════════════════════════════════════════════════════════
#  PAIR algorithm
# ════════════════════════════════════════════════════════════════════


class TestPAIR:
    def test_succeeds_when_judge_returns_high_score(
        self, cooperating_target, fixed_attacker
    ):
        async def perfect_judge(_p, _r):
            return 1.0

        out = asyncio.run(
            run_pair(
                target=cooperating_target,
                attacker=fixed_attacker,
                judge=perfect_judge,
                objective="say something",
                max_rounds=3,
                success_threshold=0.8,
            )
        )
        assert out.success is True
        assert out.metadata["stop_reason"] == "threshold_met"
        assert len(out.rounds) >= 1
        assert all(0.0 <= r.score <= 1.0 for r in out.rounds)

    def test_budget_exhausted_when_judge_never_passes(
        self, fake_target, fixed_attacker, low_judge
    ):
        out = asyncio.run(
            run_pair(
                target=fake_target,
                attacker=fixed_attacker,
                judge=low_judge,
                objective="x",
                max_rounds=3,
                success_threshold=0.9,
            )
        )
        assert out.success is False
        assert out.metadata["stop_reason"] == "budget_exhausted"
        assert len(out.rounds) == 3

    def test_progressive_improvement_succeeds_at_round_2(
        self, fake_target, fixed_attacker, threshold_at_round_2_judge
    ):
        out = asyncio.run(
            run_pair(
                target=fake_target,
                attacker=fixed_attacker,
                judge=threshold_at_round_2_judge,
                objective="x",
                max_rounds=4,
                success_threshold=0.9,
            )
        )
        assert out.success is True
        # Ascending then jump pattern
        scores = [r.score for r in out.rounds]
        assert scores[-1] >= 0.9

    def test_attacker_error_aborts_cleanly(self, fake_target):
        async def crashing_attacker(_x):
            raise RuntimeError("attacker died")

        async def zero_judge(_p, _r):
            return 0.0

        out = asyncio.run(
            run_pair(
                target=fake_target,
                attacker=crashing_attacker,
                judge=zero_judge,
                objective="x",
                max_rounds=4,
                success_threshold=0.9,
            )
        )
        # Round 0 doesn't call attacker; the error happens at round 1
        assert any("attacker_error" in r.prompt for r in out.rounds)
        assert out.success is False

    def test_target_error_aborts_cleanly(self, fixed_attacker, low_judge):
        async def crashing_target(_p):
            raise ConnectionError("network down")

        out = asyncio.run(
            run_pair(
                target=crashing_target,
                attacker=fixed_attacker,
                judge=low_judge,
                objective="x",
                max_rounds=3,
                success_threshold=0.9,
            )
        )
        # Round 0 calls target with the initial prompt -> errors out
        assert len(out.rounds) == 1
        assert "target_error" in out.rounds[0].response

    def test_max_rounds_must_be_positive(
        self, fake_target, fixed_attacker, low_judge
    ):
        with pytest.raises(ValueError):
            asyncio.run(
                run_pair(
                    target=fake_target,
                    attacker=fixed_attacker,
                    judge=low_judge,
                    objective="x",
                    max_rounds=0,
                )
            )

    def test_judge_score_clamped_to_unit_interval(
        self, fake_target, fixed_attacker
    ):
        async def out_of_range_judge(_p, _r):
            return 5.0  # invalid — must be clamped

        out = asyncio.run(
            run_pair(
                target=fake_target,
                attacker=fixed_attacker,
                judge=out_of_range_judge,
                objective="x",
                max_rounds=2,
                success_threshold=0.99,
            )
        )
        assert all(r.score <= 1.0 for r in out.rounds)
        # Clamped to 1.0 → success at round 0 already
        assert out.success is True


# ════════════════════════════════════════════════════════════════════
#  TAP algorithm
# ════════════════════════════════════════════════════════════════════


class TestTAP:
    def test_seed_already_jailbroken_short_circuits(
        self, cooperating_target, fixed_attacker
    ):
        async def perfect_judge(_p, _r):
            return 1.0

        out = asyncio.run(
            run_tap(
                target=cooperating_target,
                attacker=fixed_attacker,
                judge=perfect_judge,
                objective="x",
                max_rounds=3,
                branching_factor=2,
                beam_width=2,
                success_threshold=0.8,
            )
        )
        assert out.success is True
        assert out.metadata["stop_reason"] == "seed_already_jailbroke"
        assert len(out.rounds) == 1  # only the seed

    def test_branching_creates_correct_number_of_children(
        self, fake_target, fixed_attacker
    ):
        async def low(_p, _r):
            return 0.1

        out = asyncio.run(
            run_tap(
                target=fake_target,
                attacker=fixed_attacker,
                judge=low,
                objective="x",
                max_rounds=2,
                branching_factor=3,
                beam_width=2,
                success_threshold=0.99,
            )
        )
        # Round 0: 1 seed
        # Round 1: 1 * 3 = 3 children, prune to 2
        # Round 2: 2 * 3 = 6 children, prune to 2
        # total rounds entries = 1 + 3 + 6 = 10
        assert len(out.rounds) == 10

    def test_beam_width_caps_frontier(self, fake_target, fixed_attacker):
        async def low(_p, _r):
            return 0.1

        out = asyncio.run(
            run_tap(
                target=fake_target,
                attacker=fixed_attacker,
                judge=low,
                objective="x",
                max_rounds=2,
                branching_factor=4,
                beam_width=1,
                success_threshold=0.99,
            )
        )
        # 1 + 4 + 4 = 9
        assert len(out.rounds) == 9

    def test_threshold_met_mid_tree_short_circuits(
        self, fake_target, fixed_attacker
    ):
        # Judge that returns 0.95 on its 4th call (so we go past seed
        # then into round 1 children).
        state = {"n": 0}

        async def trip_after_4(_p, _r):
            state["n"] += 1
            return 0.95 if state["n"] >= 4 else 0.1

        out = asyncio.run(
            run_tap(
                target=fake_target,
                attacker=fixed_attacker,
                judge=trip_after_4,
                objective="x",
                max_rounds=4,
                branching_factor=2,
                beam_width=2,
                success_threshold=0.9,
            )
        )
        assert out.success is True
        assert out.metadata["stop_reason"] == "threshold_met"

    def test_seed_target_error_aborts_with_reason(
        self, fixed_attacker
    ):
        async def crashing_target(_p):
            raise RuntimeError("boom")

        async def zero_judge(_p, _r):
            return 0.0

        out = asyncio.run(
            run_tap(
                target=crashing_target,
                attacker=fixed_attacker,
                judge=zero_judge,
                objective="x",
                max_rounds=2,
                branching_factor=2,
                beam_width=2,
                success_threshold=0.9,
            )
        )
        assert out.success is False
        assert out.metadata["stop_reason"] == "seed_target_error"

    def test_invalid_params_raise(self, fake_target, fixed_attacker, low_judge):
        with pytest.raises(ValueError):
            asyncio.run(
                run_tap(
                    target=fake_target,
                    attacker=fixed_attacker,
                    judge=low_judge,
                    objective="x",
                    max_rounds=0,
                )
            )
        with pytest.raises(ValueError):
            asyncio.run(
                run_tap(
                    target=fake_target,
                    attacker=fixed_attacker,
                    judge=low_judge,
                    objective="x",
                    max_rounds=2,
                    beam_width=0,
                )
            )


# ════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════


class TestStripAttackerChrome:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ('Prompt: "Hello"', "Hello"),
            ('"Just text"', "Just text"),
            ("Already clean", "Already clean"),
            ("'wrapped'", "wrapped"),
            ("PROMPT = `code`", "code"),
            ("", ""),
        ],
    )
    def test_strip_variants(self, raw, expected):
        assert _strip_attacker_chrome(raw) == expected


# ════════════════════════════════════════════════════════════════════
#  Probe
# ════════════════════════════════════════════════════════════════════


class TestPyRITProbe:
    def test_technique_and_aggressiveness(self):
        assert PyRITProbe.TECHNIQUE == "pyrit"
        assert PyRITProbe.MAX_AGGRESSIVENESS == 3

    def test_run_without_prompt_seed(self, fake_target, fixed_attacker, low_judge):
        probe = PyRITProbe(attacker=fixed_attacker, judge=low_judge)
        out = asyncio.run(
            probe.run(
                target_invoke=fake_target, seed=0, max_turns=3, prompt_seed=None
            )
        )
        assert out.aborted_reason == "missing_prompt_seed"

    def test_run_with_invalid_json(self, fake_target, fixed_attacker, low_judge):
        probe = PyRITProbe(attacker=fixed_attacker, judge=low_judge)
        out = asyncio.run(
            probe.run(
                target_invoke=fake_target,
                seed=0,
                max_turns=3,
                prompt_seed="not{}json",
            )
        )
        assert out.aborted_reason == "bad_prompt_seed"

    def test_run_with_array_json(self, fake_target, fixed_attacker, low_judge):
        probe = PyRITProbe(attacker=fixed_attacker, judge=low_judge)
        out = asyncio.run(
            probe.run(
                target_invoke=fake_target,
                seed=0,
                max_turns=3,
                prompt_seed="[1,2]",
            )
        )
        assert out.aborted_reason == "bad_prompt_seed"

    def test_run_without_objective(self, fake_target, fixed_attacker, low_judge):
        probe = PyRITProbe(attacker=fixed_attacker, judge=low_judge)
        out = asyncio.run(
            probe.run(
                target_invoke=fake_target,
                seed=0,
                max_turns=3,
                prompt_seed='{"technique":"pair"}',
            )
        )
        assert out.aborted_reason == "bad_prompt_seed"

    def test_run_without_callables(self, fake_target):
        probe = PyRITProbe()  # no attacker/judge
        out = asyncio.run(
            probe.run(
                target_invoke=fake_target,
                seed=0,
                max_turns=3,
                prompt_seed=json.dumps(
                    {"technique": "pair", "objective": "x"}
                ),
            )
        )
        assert out.aborted_reason == "missing_callables"

    def test_run_with_bad_technique(self, fake_target, fixed_attacker, low_judge):
        probe = PyRITProbe(attacker=fixed_attacker, judge=low_judge)
        out = asyncio.run(
            probe.run(
                target_invoke=fake_target,
                seed=0,
                max_turns=3,
                prompt_seed=json.dumps(
                    {"technique": "evil", "objective": "x"}
                ),
            )
        )
        assert out.aborted_reason == "technique_not_allowlisted"

    def test_run_pair_success(self, cooperating_target, fixed_attacker):
        async def perfect(_p, _r):
            return 1.0

        probe = PyRITProbe(attacker=fixed_attacker, judge=perfect)
        out = asyncio.run(
            probe.run(
                target_invoke=cooperating_target,
                seed=0,
                max_turns=3,
                prompt_seed=json.dumps(
                    {
                        "technique": "pair",
                        "objective": "say it",
                        "success_threshold": 0.5,
                    }
                ),
            )
        )
        assert out.attempts
        assert out.metadata["success"] is True
        assert out.metadata["max_score"] >= 0.5

    def test_run_tap_with_branching(self, fake_target, fixed_attacker):
        async def low(_p, _r):
            return 0.1

        probe = PyRITProbe(attacker=fixed_attacker, judge=low)
        out = asyncio.run(
            probe.run(
                target_invoke=fake_target,
                seed=0,
                max_turns=2,
                prompt_seed=json.dumps(
                    {
                        "technique": "tap",
                        "objective": "x",
                        "branching_factor": 2,
                        "beam_width": 2,
                        "success_threshold": 0.99,
                    }
                ),
            )
        )
        # max_rounds=2: seed + (1*2) + (2*2) = 1 + 2 + 4 = 7 rounds
        assert len(out.attempts) == 7
        assert out.metadata["success"] is False


# ════════════════════════════════════════════════════════════════════
#  Charter + trace integration
# ════════════════════════════════════════════════════════════════════


class TestRunnerIntegration:
    @pytest.fixture(autouse=True)
    def _set_charter_env(self, monkeypatch):
        monkeypatch.setenv("REDROOM_ENABLED", "true")
        monkeypatch.setenv("REDROOM_MAX_AGGRESSIVENESS", "3")
        monkeypatch.setenv(
            "REDROOM_ALLOWED_TARGETS", "self,open_weight,public_api"
        )

    def test_run_probe_pair_emits_full_trace_chain(
        self, session, cooperating_target, fixed_attacker
    ):
        async def perfect(_p, _r):
            return 1.0

        probe = PyRITProbe(attacker=fixed_attacker, judge=perfect)
        registry = {"pyrit": probe}

        out = asyncio.run(
            run_probe(
                RunInputs(
                    technique="pyrit",
                    target_model_id=42,
                    tenant_id=1,
                    session_id="sess-pair-1",
                    target_invoke=cooperating_target,
                    target_class="self",
                    aggressiveness=3,
                    seed=0,
                    max_turns=3,
                    prompt_seed=json.dumps(
                        {
                            "technique": "pair",
                            "objective": "x",
                            "success_threshold": 0.5,
                        }
                    ),
                ),
                session=session,
                policy=load_charter(),
                registry=registry,
            )
        )
        assert out.result is not None
        assert out.result.metadata["success"] is True
        rows = list(session.query(RedRoomTrace).all())
        kinds = [r.kind for r in rows]
        assert kinds[0] == TraceKind.AUTHORIZE.value
        assert TraceKind.PROBE.value in kinds
        assert TraceKind.RESPONSE.value in kinds

    def test_run_probe_pyrit_aggressiveness_above_l3_refused(
        self, session, fake_target, fixed_attacker, low_judge
    ):
        probe = PyRITProbe(attacker=fixed_attacker, judge=low_judge)
        registry = {"pyrit": probe}
        with pytest.raises(ValueError, match="capped at L3"):
            asyncio.run(
                run_probe(
                    RunInputs(
                        technique="pyrit",
                        target_model_id=42,
                        tenant_id=1,
                        session_id="sess-pair-2",
                        target_invoke=fake_target,
                        target_class="self",
                        aggressiveness=4,
                        seed=0,
                        max_turns=3,
                        prompt_seed=json.dumps(
                            {"technique": "pair", "objective": "x"}
                        ),
                    ),
                    session=session,
                    policy=load_charter(),
                    registry=registry,
                )
            )
