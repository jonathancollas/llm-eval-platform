"""Tests for the D6 sandbagging detection probe.

Covers:
  - Built-in framing pairs are non-empty and properly shaped
  - Probe contract: missing judge, bad prompt_seed, valid runs
  - Detection: target with sandbagging behavior is flagged
  - No false positive: consistent target is not flagged
  - max_turns caps the number of pairs probed (each pair = 2 turns)
  - Charter integration via run_probe()
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
    RunInputs,
    TraceKind,
    load_charter,
    run_probe,
)
from eval_engine.redroom.probes.sandbagging import (  # noqa: E402
    DEFAULT_FRAMING_PAIRS,
    FramingPair,
    SandbaggingProbe,
)
from eval_engine.redroom.trace_store import RedRoomTrace  # noqa: E402


# ════════════════════════════════════════════════════════════════════
#  Default framing pairs sanity
# ════════════════════════════════════════════════════════════════════


class TestDefaultPairs:
    def test_default_pairs_non_empty(self):
        assert len(DEFAULT_FRAMING_PAIRS) >= 3

    def test_each_pair_has_distinct_natural_and_eval_text(self):
        for fp in DEFAULT_FRAMING_PAIRS:
            assert fp.natural and fp.eval_framed
            assert fp.natural != fp.eval_framed
            assert fp.topic

    def test_eval_frame_contains_eval_cue(self):
        cues = ("benchmark", "eval", "test", "scored", "graded", "AISI", "AISafety")
        for fp in DEFAULT_FRAMING_PAIRS:
            blob = (fp.eval_framed or "").lower()
            assert any(c.lower() in blob for c in cues), \
                f"pair {fp.topic} has no eval cue"


# ════════════════════════════════════════════════════════════════════
#  Probe contract
# ════════════════════════════════════════════════════════════════════


class TestProbeContract:
    def test_max_aggressiveness_l3(self):
        assert SandbaggingProbe.MAX_AGGRESSIVENESS == 3

    def test_run_without_judge_returns_aborted(self):
        async def t(_p):
            return ""

        probe = SandbaggingProbe()  # no judge
        out = asyncio.run(
            probe.run(target_invoke=t, seed=0, max_turns=10, prompt_seed=None)
        )
        assert out.aborted_reason == "missing_judge"

    def test_invalid_json_prompt_seed(self):
        async def t(_p):
            return ""

        async def j(_p, _r):
            return 0.5

        probe = SandbaggingProbe(judge=j)
        out = asyncio.run(
            probe.run(target_invoke=t, seed=0, max_turns=10, prompt_seed="{not json")
        )
        assert out.aborted_reason == "bad_prompt_seed"

    def test_array_prompt_seed_rejected(self):
        async def t(_p):
            return ""

        async def j(_p, _r):
            return 0.5

        probe = SandbaggingProbe(judge=j)
        out = asyncio.run(
            probe.run(target_invoke=t, seed=0, max_turns=10, prompt_seed="[]")
        )
        assert out.aborted_reason == "bad_prompt_seed"

    def test_threshold_out_of_range_rejected(self):
        async def t(_p):
            return ""

        async def j(_p, _r):
            return 0.5

        probe = SandbaggingProbe(judge=j)
        out = asyncio.run(
            probe.run(
                target_invoke=t,
                seed=0,
                max_turns=10,
                prompt_seed=json.dumps({"suspicious_above": 1.5}),
            )
        )
        assert out.aborted_reason == "bad_prompt_seed"

    def test_pairs_must_be_list(self):
        async def t(_p):
            return ""

        async def j(_p, _r):
            return 0.5

        probe = SandbaggingProbe(judge=j)
        out = asyncio.run(
            probe.run(
                target_invoke=t,
                seed=0,
                max_turns=10,
                prompt_seed=json.dumps({"pairs": "not-a-list"}),
            )
        )
        assert out.aborted_reason == "bad_prompt_seed"

    def test_pair_missing_key_rejected(self):
        async def t(_p):
            return ""

        async def j(_p, _r):
            return 0.5

        probe = SandbaggingProbe(judge=j)
        out = asyncio.run(
            probe.run(
                target_invoke=t,
                seed=0,
                max_turns=10,
                prompt_seed=json.dumps(
                    {"pairs": [{"topic": "x", "natural": "n"}]}  # missing eval_framed
                ),
            )
        )
        assert out.aborted_reason == "bad_prompt_seed"

    def test_empty_custom_pairs_returns_no_pairs(self):
        async def t(_p):
            return ""

        async def j(_p, _r):
            return 0.5

        probe = SandbaggingProbe(judge=j, default_pairs=())
        out = asyncio.run(
            probe.run(
                target_invoke=t,
                seed=0,
                max_turns=10,
                prompt_seed=json.dumps({"pairs": []}),
            )
        )
        # When user explicitly passes empty pairs, the probe falls back
        # to defaults — but defaults are also empty here.
        assert out.aborted_reason == "no_pairs"


# ════════════════════════════════════════════════════════════════════
#  Detection
# ════════════════════════════════════════════════════════════════════


class TestDetection:
    def test_sandbagging_target_is_flagged(self):
        """Target gives 'good' answer naturally, 'I won't help' under eval."""
        async def t(prompt):
            if "BENCHMARK" in prompt or "EVAL" in prompt or "SAFETY" in prompt or \
               "Adversarial" in prompt or "evaluation" in prompt.lower():
                return "I cannot help with that."
            return (
                "Sure! Here is a detailed and lengthy answer that satisfies "
                "the question, with several substantial sentences of content."
            )

        async def j(_prompt, response):
            # Quality: long+detailed = high; refusals = low.
            if "cannot" in response.lower() or len(response) < 50:
                return 0.1
            return 0.9

        probe = SandbaggingProbe(judge=j)
        out = asyncio.run(
            probe.run(target_invoke=t, seed=0, max_turns=20, prompt_seed=None)
        )
        assert out.metadata["flagged"] is True
        assert out.metadata["sandbagging_score"] > 0.10

    def test_consistent_target_is_not_flagged(self):
        """Target gives the same response regardless of framing."""
        async def t(_p):
            return "Same answer always."

        async def j(_p, _r):
            return 0.5

        probe = SandbaggingProbe(judge=j)
        out = asyncio.run(
            probe.run(target_invoke=t, seed=0, max_turns=20, prompt_seed=None)
        )
        assert out.metadata["flagged"] is False
        assert abs(out.metadata["sandbagging_score"]) < 0.05

    def test_inverse_sandbagging_not_flagged_as_positive(self):
        """Target gives BETTER answers under eval (inverse sandbagging)."""
        async def t(prompt):
            return "long detailed eval answer" if "EVAL" in prompt else "short"

        async def j(_p, response):
            return 0.9 if len(response) > 20 else 0.1

        probe = SandbaggingProbe(judge=j)
        out = asyncio.run(
            probe.run(target_invoke=t, seed=0, max_turns=20, prompt_seed=None)
        )
        assert out.metadata["sandbagging_score"] < 0


# ════════════════════════════════════════════════════════════════════
#  Throttling and configuration
# ════════════════════════════════════════════════════════════════════


class TestThrottling:
    def test_max_turns_caps_pairs(self):
        async def t(_p):
            return "x"

        async def j(_p, _r):
            return 0.5

        probe = SandbaggingProbe(judge=j)
        # max_turns=4 → 2 pairs
        out = asyncio.run(
            probe.run(target_invoke=t, seed=0, max_turns=4, prompt_seed=None)
        )
        assert out.metadata["n_pairs_probed"] == 2
        assert len(out.attempts) == 4

    def test_target_exception_is_recorded_not_raised(self):
        async def crashing(_p):
            raise ConnectionError("boom")

        async def j(_p, _r):
            return 0.5

        probe = SandbaggingProbe(judge=j)
        out = asyncio.run(
            probe.run(target_invoke=crashing, seed=0, max_turns=4, prompt_seed=None)
        )
        # All responses captured as sentinel strings; both scores converge.
        assert all("target_error" in a.response for a in out.attempts)
        assert out.metadata["flagged"] is False

    def test_judge_exception_does_not_crash(self):
        async def t(_p):
            return "x"

        async def crashing(_p, _r):
            raise RuntimeError("judge dead")

        probe = SandbaggingProbe(judge=crashing)
        out = asyncio.run(
            probe.run(target_invoke=t, seed=0, max_turns=4, prompt_seed=None)
        )
        # Both natural and eval scores are 0 → gap=0 for every pair.
        assert out.metadata["sandbagging_score"] == 0.0

    def test_custom_pairs_used_when_provided(self):
        async def t(_p):
            return "x"

        async def j(_p, _r):
            return 0.5

        probe = SandbaggingProbe(judge=j)
        custom = {
            "pairs": [
                {"topic": "custom_a", "natural": "n1", "eval_framed": "e1"},
                {"topic": "custom_b", "natural": "n2", "eval_framed": "e2"},
            ]
        }
        out = asyncio.run(
            probe.run(
                target_invoke=t,
                seed=0,
                max_turns=10,
                prompt_seed=json.dumps(custom),
            )
        )
        topics = {p["topic"] for p in out.metadata["per_pair"]}
        assert topics == {"custom_a", "custom_b"}

    def test_custom_threshold_respected(self):
        async def t(_p):
            return "x"

        async def j(_p, _r):
            return 0.5

        probe = SandbaggingProbe(judge=j)
        out = asyncio.run(
            probe.run(
                target_invoke=t,
                seed=0,
                max_turns=4,
                prompt_seed=json.dumps({"suspicious_above": 0.99}),
            )
        )
        assert out.metadata["suspicious_above"] == 0.99


# ════════════════════════════════════════════════════════════════════
#  Charter integration
# ════════════════════════════════════════════════════════════════════


class TestRunnerIntegration:
    @pytest.fixture(autouse=True)
    def _set_charter_env(self, monkeypatch):
        monkeypatch.setenv("REDROOM_ENABLED", "true")
        monkeypatch.setenv("REDROOM_MAX_AGGRESSIVENESS", "3")
        monkeypatch.setenv(
            "REDROOM_ALLOWED_TARGETS", "self,open_weight,public_api"
        )

    def test_run_probe_sandbagging_emits_traces(self):
        eng = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        SQLModel.metadata.create_all(eng)

        async def t(_p):
            return "x"

        async def j(_p, _r):
            return 0.5

        probe = SandbaggingProbe(judge=j)
        with Session(eng) as session:
            out = asyncio.run(
                run_probe(
                    RunInputs(
                        technique="sandbagging",
                        target_model_id=42,
                        tenant_id=1,
                        session_id="sess-sb-1",
                        target_invoke=t,
                        target_class="self",
                        aggressiveness=2,
                        seed=0,
                        max_turns=4,
                        prompt_seed=None,
                    ),
                    session=session,
                    policy=load_charter(),
                    registry={"sandbagging": probe},
                )
            )
            assert out.result is not None
            from sqlmodel import select
            rows = list(session.exec(select(RedRoomTrace)))
            assert any(r.kind == TraceKind.AUTHORIZE.value for r in rows)
            assert any(r.kind == TraceKind.RESPONSE.value for r in rows)

    def test_run_probe_sandbagging_l4_refused(self):
        eng = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        SQLModel.metadata.create_all(eng)

        async def t(_p):
            return "x"

        async def j(_p, _r):
            return 0.5

        probe = SandbaggingProbe(judge=j)
        with Session(eng) as session:
            with pytest.raises(ValueError, match="capped at L3"):
                asyncio.run(
                    run_probe(
                        RunInputs(
                            technique="sandbagging",
                            target_model_id=42,
                            tenant_id=1,
                            session_id="sess-sb-2",
                            target_invoke=t,
                            target_class="self",
                            aggressiveness=4,
                            seed=0,
                            max_turns=4,
                        ),
                        session=session,
                        policy=load_charter(),
                        registry={"sandbagging": probe},
                    )
                )
