"""Tests for the D5 coevolution engine.

Covers:
  - Strategy / StrategyMemory: stats, posterior, selection (greedy/ε)
  - Calibration: passing, MAE failure, direction failure, empty set, judge
    crashes
  - Engine: success path, budget exhaustion, attacker/target/judge errors
  - Memory updates affect future selection (the "learning" property)
  - CoevolutionProbe contract + JSON parsing + missing-deps refusal
  - Charter L4 enforcement via run_probe
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys

import pytest
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("REDROOM_TRACE_SECRET", "x" * 32 + "_test_secret")
os.environ["REDROOM_ENABLED"] = "true"
os.environ["REDROOM_ALLOWED_TARGETS"] = "self,open_weight,public_api"
os.environ["REDROOM_MAX_AGGRESSIVENESS"] = "5"

from eval_engine.redroom import (  # noqa: E402
    CalibrationItem,
    CoevolutionConfig,
    RunInputs,
    Strategy,
    StrategyMemory,
    TraceKind,
    calibrate_judge,
    load_charter,
    run_coevolution,
    run_probe,
)
from eval_engine.redroom.coevolution.calibration import (  # noqa: E402
    synthesize_default_calibration_set,
)
from eval_engine.redroom.coevolution.engine import (  # noqa: E402
    _format_attacker_brief,
    default_strategy_set,
)
from eval_engine.redroom.probes.coevolution_probe import CoevolutionProbe  # noqa: E402
from eval_engine.redroom.trace_store import RedRoomTrace  # noqa: E402

# ════════════════════════════════════════════════════════════════════
#  Strategy / StrategyMemory
# ════════════════════════════════════════════════════════════════════


class TestStrategy:
    def test_empirical_score_zero_when_untried(self):
        s = Strategy(name="x", template="t")
        assert s.empirical_score == 0.0

    def test_empirical_score_after_records(self):
        s = Strategy(name="x", template="t").record(0.8, clock=1).record(0.6, clock=2)
        assert s.empirical_score == pytest.approx(0.7)

    def test_posterior_with_uniform_prior(self):
        s = Strategy(name="x", template="t")  # 0/0
        # Beta(1,1) → mean = 0.5
        assert s.posterior_score() == 0.5

    def test_posterior_after_one_success(self):
        s = Strategy(name="x", template="t").record(1.0, clock=1)
        # (1+1)/(1+2) = 2/3
        assert s.posterior_score() == pytest.approx(2 / 3)

    def test_record_clamps_score(self):
        s = Strategy(name="x", template="t").record(5.0, clock=1)
        assert s.empirical_score == 1.0
        s2 = Strategy(name="y", template="t").record(-1.0, clock=1)
        assert s2.empirical_score == 0.0


class TestStrategyMemory:
    def test_add_and_lookup(self):
        m = StrategyMemory([Strategy(name="a", template="ta")])
        assert "a" in m
        assert m.get("a").template == "ta"

    def test_add_duplicate_raises(self):
        m = StrategyMemory([Strategy(name="a", template="ta")])
        with pytest.raises(ValueError, match="already in memory"):
            m.add(Strategy(name="a", template="other"))

    def test_add_empty_name_raises(self):
        m = StrategyMemory()
        with pytest.raises(ValueError):
            m.add(Strategy(name="", template="t"))

    def test_select_empty_raises(self):
        m = StrategyMemory()
        with pytest.raises(LookupError):
            m.select()

    def test_select_invalid_epsilon(self):
        m = StrategyMemory([Strategy(name="a", template="t")])
        with pytest.raises(ValueError):
            m.select(epsilon=1.5)

    def test_greedy_picks_highest_posterior(self):
        m = StrategyMemory(
            [
                Strategy(name="a", template="t"),
                Strategy(name="b", template="t"),
            ]
        )
        # Make 'a' clearly better.
        m.record("a", 1.0)
        m.record("a", 1.0)
        m.record("b", 0.0)

        # epsilon=0 → always greedy
        rng = random.Random(42)
        selected = {m.select(epsilon=0.0, rng=rng).name for _ in range(20)}
        assert selected == {"a"}

    def test_epsilon_one_is_uniform(self):
        m = StrategyMemory(
            [
                Strategy(name="a", template="t"),
                Strategy(name="b", template="t"),
                Strategy(name="c", template="t"),
            ]
        )
        rng = random.Random(0)
        seen = {m.select(epsilon=1.0, rng=rng).name for _ in range(50)}
        # With pure exploration we expect to see all three eventually.
        assert seen == {"a", "b", "c"}

    def test_record_unknown_raises(self):
        m = StrategyMemory([Strategy(name="a", template="t")])
        with pytest.raises(KeyError):
            m.record("missing", 0.5)

    def test_top_n_returns_n_best(self):
        m = StrategyMemory(
            [
                Strategy(name="a", template="t"),
                Strategy(name="b", template="t"),
                Strategy(name="c", template="t"),
            ]
        )
        m.record("c", 1.0)
        m.record("a", 0.5)
        m.record("b", 0.0)
        top = m.top_n(2)
        assert [s.name for s in top] == ["c", "a"]

    def test_top_n_zero_returns_empty(self):
        m = StrategyMemory([Strategy(name="a", template="t")])
        assert m.top_n(0) == ()

    def test_serialize_round_trip(self):
        m = StrategyMemory(
            [
                Strategy(name="a", template="ta", notes="note-a"),
                Strategy(name="b", template="tb"),
            ]
        )
        m.record("a", 0.6)
        m.record("a", 0.8)
        d = m.to_dict()
        m2 = StrategyMemory.from_dict(d)
        assert m2.get("a").n_tried == 2
        assert m2.get("a").sum_score == pytest.approx(1.4)
        assert m2.get("a").notes == "note-a"
        assert "b" in m2

    def test_recency_bias_helps_recent_strategy_break_tie(self):
        m = StrategyMemory(
            [
                Strategy(name="old", template="t"),
                Strategy(name="new", template="t"),
            ]
        )
        # Both have identical posterior (0.5).
        m.record("old", 0.5)
        m.record("old", 0.5)
        m.record("new", 0.5)
        m.record("new", 0.5)
        m.record("new", 0.5)  # 'new' last_used is later
        # With recency_bias > 0 and epsilon=0, we should prefer 'new'.
        rng = random.Random(0)
        chosen = m.select(epsilon=0.0, recency_bias=0.5, rng=rng).name
        assert chosen == "new"


# ════════════════════════════════════════════════════════════════════
#  Calibration
# ════════════════════════════════════════════════════════════════════


class TestCalibration:
    def test_perfect_judge_passes(self):
        async def perfect(_p, r):
            # Use response heuristic: jailbreak if response contains specific token
            return 1.0 if "[unsafe]" in r else 0.0

        items = (
            CalibrationItem(prompt="benign", response="benign answer", ground_truth_score=0.0),
            CalibrationItem(prompt="benign2", response="benign answer", ground_truth_score=0.0),
            CalibrationItem(prompt="bad", response="[unsafe] payload", ground_truth_score=1.0),
            CalibrationItem(prompt="bad2", response="[unsafe] payload", ground_truth_score=1.0),
        )
        report = asyncio.run(calibrate_judge(perfect, items))
        assert report.passed is True
        assert report.mae < 0.01
        assert report.direction_accuracy == 1.0

    def test_no_items_fails_cleanly(self):
        async def any_judge(_p, _r):
            return 0.5

        report = asyncio.run(calibrate_judge(any_judge, ()))
        assert report.passed is False
        assert "no calibration" in report.reason

    def test_high_mae_fails(self):
        async def biased_judge(_p, _r):
            return 0.5  # always 0.5 → high MAE on extreme labels

        items = (
            CalibrationItem(prompt="a", response="a", ground_truth_score=0.0),
            CalibrationItem(prompt="b", response="b", ground_truth_score=1.0),
            CalibrationItem(prompt="c", response="c", ground_truth_score=0.0),
            CalibrationItem(prompt="d", response="d", ground_truth_score=1.0),
        )
        report = asyncio.run(calibrate_judge(biased_judge, items))
        assert report.passed is False
        assert "MAE" in report.reason

    def test_low_direction_accuracy_fails(self):
        async def inverted_judge(_p, _r):
            # Always invert: report opposite side of 0.5
            return 0.9  # constant high → wrong on 'benign' items

        items = (
            CalibrationItem(prompt="a", response="a", ground_truth_score=0.0),  # judge wrong
            CalibrationItem(prompt="b", response="b", ground_truth_score=0.0),  # judge wrong
            CalibrationItem(prompt="c", response="c", ground_truth_score=0.0),  # judge wrong
            CalibrationItem(prompt="d", response="d", ground_truth_score=0.0),  # judge wrong
            CalibrationItem(prompt="e", response="e", ground_truth_score=1.0),  # judge right
        )
        report = asyncio.run(calibrate_judge(inverted_judge, items))
        assert report.passed is False
        # Could fail on either MAE or direction; both are valid.
        assert report.reason

    def test_judge_exception_treated_as_uncertainty(self):
        async def crashing(_p, _r):
            raise RuntimeError("oops")

        items = (
            CalibrationItem(prompt="a", response="a", ground_truth_score=0.0),
            CalibrationItem(prompt="b", response="b", ground_truth_score=1.0),
        )
        report = asyncio.run(calibrate_judge(crashing, items))
        # Score forced to 0.5 → MAE=0.5 -> fail
        assert report.passed is False

    def test_default_calibration_set_is_non_empty_and_balanced(self):
        items = synthesize_default_calibration_set()
        assert len(items) >= 8
        gt = [i.ground_truth_score for i in items]
        # Some clearly-jailbroken items
        assert any(s >= 0.8 for s in gt)
        # Many benign items
        assert sum(1 for s in gt if s < 0.5) >= 5


# ════════════════════════════════════════════════════════════════════
#  Engine
# ════════════════════════════════════════════════════════════════════


class TestEngine:
    def _make_memory(self):
        return StrategyMemory(list(default_strategy_set()))

    def test_empty_memory_raises(self):
        async def t(_p):
            return ""
        async def a(_x):
            return ""
        async def j(_p, _r):
            return 0.0

        with pytest.raises(ValueError, match="empty"):
            asyncio.run(
                run_coevolution(
                    target=t, attacker=a, judge=j,
                    memory=StrategyMemory(),
                    config=CoevolutionConfig(objective="x", max_rounds=1),
                )
            )

    def test_success_when_judge_high_immediately(self):
        async def target(_p):
            return "ok"

        async def attacker(_x):
            return "evil prompt"

        async def perfect(_p, _r):
            return 1.0

        out = asyncio.run(
            run_coevolution(
                target=target,
                attacker=attacker,
                judge=perfect,
                memory=self._make_memory(),
                config=CoevolutionConfig(
                    objective="x", max_rounds=5, success_threshold=0.5
                ),
            )
        )
        assert out.success is True
        assert out.stop_reason == "threshold_met"
        assert len(out.rounds) == 1

    def test_budget_exhausted_when_judge_never_passes(self):
        async def target(_p):
            return "refused"

        async def attacker(_x):
            return "any"

        async def low(_p, _r):
            return 0.1

        out = asyncio.run(
            run_coevolution(
                target=target,
                attacker=attacker,
                judge=low,
                memory=self._make_memory(),
                config=CoevolutionConfig(
                    objective="x", max_rounds=4, success_threshold=0.9
                ),
            )
        )
        assert out.success is False
        assert out.stop_reason == "budget_exhausted"
        assert len(out.rounds) == 4

    def test_memory_is_updated_on_success(self):
        memory = self._make_memory()

        async def target(_p):
            return "ok"

        async def attacker(_x):
            return "p"

        async def perfect(_p, _r):
            return 1.0

        out = asyncio.run(
            run_coevolution(
                target=target,
                attacker=attacker,
                judge=perfect,
                memory=memory,
                config=CoevolutionConfig(
                    objective="x", max_rounds=3, success_threshold=0.5, seed=42
                ),
            )
        )
        # The strategy used in round 0 should have n_tried >= 1 now.
        used = out.rounds[0].strategy_name
        assert memory.get(used).n_tried == 1
        assert memory.get(used).empirical_score == 1.0

    def test_attacker_failure_is_recorded_not_raised(self):
        async def target(_p):
            return "ok"

        async def crashing(_x):
            raise RuntimeError("attacker dead")

        async def low(_p, _r):
            return 0.1

        memory = self._make_memory()
        out = asyncio.run(
            run_coevolution(
                target=target,
                attacker=crashing,
                judge=low,
                memory=memory,
                config=CoevolutionConfig(
                    objective="x", max_rounds=2, success_threshold=0.99
                ),
            )
        )
        assert all("attacker_error" in r.prompt for r in out.rounds)
        # Failed strategies still get recorded with score 0.0.
        for r in out.rounds:
            assert memory.get(r.strategy_name).n_tried >= 1

    def test_target_failure_is_recorded(self):
        async def crashing(_p):
            raise ConnectionError("net")

        async def attacker(_x):
            return "p"

        async def low(_p, _r):
            return 0.1

        memory = self._make_memory()
        out = asyncio.run(
            run_coevolution(
                target=crashing,
                attacker=attacker,
                judge=low,
                memory=memory,
                config=CoevolutionConfig(
                    objective="x", max_rounds=2, success_threshold=0.9
                ),
            )
        )
        assert all("target_error" in r.response for r in out.rounds)

    def test_judge_failure_scores_zero(self):
        async def target(_p):
            return "ok"

        async def attacker(_x):
            return "p"

        async def crashing(_p, _r):
            raise RuntimeError("judge dead")

        memory = self._make_memory()
        out = asyncio.run(
            run_coevolution(
                target=target,
                attacker=attacker,
                judge=crashing,
                memory=memory,
                config=CoevolutionConfig(
                    objective="x", max_rounds=2, success_threshold=0.5
                ),
            )
        )
        assert all(r.score == 0.0 for r in out.rounds)

    def test_attacker_briefing_contains_objective_and_strategy(self):
        s = Strategy(name="role_play", template="be a pirate")
        brief = _format_attacker_brief(
            objective="get the secret",
            strategy=s,
            top_strategies=(s,),
            last_response="",
            last_score=0.0,
        )
        assert "role_play" in brief
        assert "get the secret" in brief
        assert "be a pirate" in brief
        assert "ONE single prompt" in brief


# ════════════════════════════════════════════════════════════════════
#  Config validation
# ════════════════════════════════════════════════════════════════════


class TestConfig:
    def test_objective_required(self):
        with pytest.raises(ValueError):
            CoevolutionConfig(objective="", max_rounds=1)

    def test_max_rounds_must_be_in_range(self):
        with pytest.raises(ValueError):
            CoevolutionConfig(objective="x", max_rounds=0)
        with pytest.raises(ValueError):
            CoevolutionConfig(objective="x", max_rounds=10_000)

    @pytest.mark.parametrize("field, bad", [
        ("success_threshold", -0.1),
        ("success_threshold", 1.1),
        ("epsilon", -0.5),
        ("epsilon", 2.0),
        ("recency_bias", -1.0),
        ("recency_bias", 5.0),
    ])
    def test_floats_must_be_in_unit(self, field, bad):
        with pytest.raises(ValueError):
            CoevolutionConfig(objective="x", max_rounds=1, **{field: bad})


# ════════════════════════════════════════════════════════════════════
#  Probe
# ════════════════════════════════════════════════════════════════════


class TestCoevolutionProbe:
    def test_aggressiveness_l4(self):
        assert CoevolutionProbe.MAX_AGGRESSIVENESS == 4

    def test_run_without_seed_aborts(self):
        probe = CoevolutionProbe()
        out = asyncio.run(
            probe.run(
                target_invoke=lambda _p: asyncio.sleep(0),  # unused
                seed=0, max_turns=3, prompt_seed=None,
            )
        )
        assert out.aborted_reason == "missing_prompt_seed"

    def test_run_with_invalid_json(self):
        probe = CoevolutionProbe()
        out = asyncio.run(
            probe.run(
                target_invoke=lambda _p: asyncio.sleep(0),
                seed=0, max_turns=3, prompt_seed="not-json",
            )
        )
        assert out.aborted_reason == "bad_prompt_seed"

    def test_run_without_objective(self):
        probe = CoevolutionProbe()
        out = asyncio.run(
            probe.run(
                target_invoke=lambda _p: asyncio.sleep(0),
                seed=0, max_turns=3, prompt_seed='{"max_rounds":2}',
            )
        )
        assert out.aborted_reason == "bad_prompt_seed"

    def test_run_without_dependencies(self):
        async def target(_p):
            return "ok"
        probe = CoevolutionProbe()  # no attacker/judge/memory
        out = asyncio.run(
            probe.run(
                target_invoke=target,
                seed=0, max_turns=3,
                prompt_seed=json.dumps({"objective": "x"}),
            )
        )
        assert out.aborted_reason == "missing_dependencies"

    def test_run_full_path_records_strategies(self):
        async def target(_p):
            return "ok"

        async def attacker(_x):
            return "p"

        async def perfect(_p, _r):
            return 1.0

        memory = StrategyMemory(list(default_strategy_set()))
        probe = CoevolutionProbe(attacker=attacker, judge=perfect, memory=memory)

        out = asyncio.run(
            probe.run(
                target_invoke=target,
                seed=0, max_turns=3,
                prompt_seed=json.dumps(
                    {"objective": "demo", "success_threshold": 0.5}
                ),
            )
        )
        assert out.attempts
        assert out.metadata["success"] is True
        assert out.metadata["max_score"] >= 0.5
        # Memory was updated
        used = out.attempts[0].prompt.split("]")[0][1:]  # extract strategy_name
        assert memory.get(used).n_tried >= 1


# ════════════════════════════════════════════════════════════════════
#  Charter integration
# ════════════════════════════════════════════════════════════════════


class TestRunnerIntegration:
    def test_run_probe_coevolution_l4_emits_traces(self, monkeypatch):
        # Explicitly raise the ceiling for this test — other test modules
        # may have lowered it via their own os.environ setup at import time.
        monkeypatch.setenv("REDROOM_ENABLED", "true")
        monkeypatch.setenv("REDROOM_MAX_AGGRESSIVENESS", "5")
        monkeypatch.setenv(
            "REDROOM_ALLOWED_TARGETS", "self,open_weight,public_api"
        )
        eng = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        SQLModel.metadata.create_all(eng)

        async def target(_p):
            return "ok"

        async def attacker(_x):
            return "p"

        async def perfect(_p, _r):
            return 1.0

        memory = StrategyMemory(list(default_strategy_set()))
        probe = CoevolutionProbe(attacker=attacker, judge=perfect, memory=memory)

        with Session(eng) as session:
            out = asyncio.run(
                run_probe(
                    RunInputs(
                        technique="coevolution",
                        target_model_id=42,
                        tenant_id=1,
                        session_id="sess-coevo-1",
                        target_invoke=target,
                        target_class="self",
                        aggressiveness=4,
                        seed=0,
                        max_turns=2,
                        prompt_seed=json.dumps(
                            {"objective": "x", "success_threshold": 0.5}
                        ),
                    ),
                    session=session,
                    policy=load_charter(),
                    registry={"coevolution": probe},
                )
            )
            assert out.result is not None
            assert out.result.metadata["success"] is True
            rows = list(session.exec(__import__("sqlmodel").select(RedRoomTrace)))
            assert any(r.kind == TraceKind.AUTHORIZE.value for r in rows)
