"""Tests for the D8 indirect prompt injection probe."""
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
os.environ["REDROOM_MAX_AGGRESSIVENESS"] = "5"

from eval_engine.redroom import (  # noqa: E402
    RunInputs,
    TraceKind,
    load_charter,
    run_probe,
)
from eval_engine.redroom.probes.indirect_injection import (  # noqa: E402
    IndirectInjectionProbe,
    _parse_config,
    _wrap_email,
    _wrap_html,
    _wrap_plaintext,
    _wrap_rag,
    build_default_payloads,
)
from eval_engine.redroom.trace_store import RedRoomTrace  # noqa: E402

# ════════════════════════════════════════════════════════════════════
#  Wrappers
# ════════════════════════════════════════════════════════════════════


class TestWrappers:
    def test_html_wraps_injection(self):
        out = _wrap_html("INJ", "BENIGN")
        assert "<html>" in out
        assert "INJ" in out
        assert "BENIGN" in out

    def test_email_has_headers_and_body(self):
        out = _wrap_email("INJ", "BENIGN")
        assert "From:" in out
        assert "Subject:" in out
        assert "INJ" in out
        assert "BENIGN" in out

    def test_rag_has_multiple_passages(self):
        out = _wrap_rag("INJ", "BENIGN")
        assert "[1]" in out and "[3]" in out
        assert "INJ" in out
        assert "BENIGN" in out

    def test_plaintext_simple(self):
        out = _wrap_plaintext("INJ", "BENIGN")
        assert "BEGIN DOCUMENT" in out
        assert "INJ" in out


# ════════════════════════════════════════════════════════════════════
#  Default payloads
# ════════════════════════════════════════════════════════════════════


class TestDefaultPayloads:
    def test_payloads_have_name_marker_instruction(self):
        ps = build_default_payloads(rng_seed=42)
        assert len(ps) >= 3
        for p in ps:
            assert p.name
            assert p.success_marker
            assert p.injection_instruction
            # The marker must appear inside the injection text so the
            # target has the chance to copy it.
            assert p.success_marker.lower() in p.injection_instruction.lower()

    def test_seeded_payloads_are_deterministic(self):
        a = build_default_payloads(rng_seed=42)
        b = build_default_payloads(rng_seed=42)
        assert [p.name for p in a] == [p.name for p in b]
        assert [p.success_marker for p in a] == [p.success_marker for p in b]

    def test_unseeded_payloads_use_random_token(self):
        a = build_default_payloads()
        b = build_default_payloads()
        # Different invocations should have different markers — random.
        assert a[0].success_marker != b[0].success_marker


# ════════════════════════════════════════════════════════════════════
#  Config parsing
# ════════════════════════════════════════════════════════════════════


class TestConfig:
    def test_default_uses_all_channels(self):
        cfg, err = _parse_config(None)
        assert err is None
        assert set(cfg["channels"]) == {"html", "email", "rag", "plaintext"}

    def test_invalid_json(self):
        cfg, err = _parse_config("not json")
        assert err is not None

    def test_array_root_rejected(self):
        cfg, err = _parse_config("[]")
        assert err is not None

    def test_unknown_channel_rejected(self):
        cfg, err = _parse_config(json.dumps({"channels": ["html", "smtp"]}))
        assert err is not None

    def test_empty_channels_list_rejected(self):
        cfg, err = _parse_config(json.dumps({"channels": []}))
        assert err is not None

    def test_benign_task_must_be_non_empty(self):
        cfg, err = _parse_config(
            json.dumps({"channels": ["html"], "benign_task": "  "})
        )
        assert err is not None

    def test_custom_benign_task_passes(self):
        cfg, err = _parse_config(
            json.dumps({"benign_task": "do this benign thing"})
        )
        assert err is None
        assert cfg["benign_task"] == "do this benign thing"


# ════════════════════════════════════════════════════════════════════
#  Probe — defender behaviours
# ════════════════════════════════════════════════════════════════════


class TestProbeDefenderBehaviour:
    def test_aggressiveness_l4(self):
        assert IndirectInjectionProbe.MAX_AGGRESSIVENESS == 4

    def test_compliant_target_is_breached(self):
        """Target naively echoes everything in the document, leaking the marker."""

        def _make_target(payloads):
            async def _t(prompt):
                # Simulate a target that includes the injected instruction
                # text (and thus the marker) in its response. This is the
                # canonical IPI failure mode.
                for p in payloads:
                    if p.injection_instruction in prompt:
                        return f"Summary: <doc summary> {p.success_marker}"
                return "Summary: nothing notable."
            return _t

        payloads = build_default_payloads(rng_seed=123)
        probe = IndirectInjectionProbe(payloads=payloads)
        out = asyncio.run(
            probe.run(
                target_invoke=_make_target(payloads),
                seed=0,
                max_turns=12,
                prompt_seed=None,
            )
        )
        assert out.metadata["any_breached"] is True
        assert out.metadata["breach_rate"] > 0.0

    def test_safe_target_is_not_breached(self):
        """Target ignores embedded instructions and just summarises."""

        async def _t(_prompt):
            return "Summary: short benign summary, French translation skipped."

        probe = IndirectInjectionProbe(
            payloads=build_default_payloads(rng_seed=7)
        )
        out = asyncio.run(
            probe.run(
                target_invoke=_t,
                seed=7,
                max_turns=12,
                prompt_seed=None,
            )
        )
        assert out.metadata["any_breached"] is False
        assert out.metadata["breach_rate"] == 0.0

    def test_max_turns_caps_attempts(self):
        async def _t(_p):
            return "x"

        probe = IndirectInjectionProbe(
            payloads=build_default_payloads(rng_seed=1)
        )
        out = asyncio.run(
            probe.run(target_invoke=_t, seed=0, max_turns=2, prompt_seed=None)
        )
        assert out.metadata["n_attempts"] == 2
        assert len(out.attempts) == 2

    def test_target_exception_recorded(self):
        async def _t(_p):
            raise ConnectionError("net")

        probe = IndirectInjectionProbe(
            payloads=build_default_payloads(rng_seed=1)
        )
        out = asyncio.run(
            probe.run(target_invoke=_t, seed=0, max_turns=4, prompt_seed=None)
        )
        assert out.metadata["any_breached"] is False
        assert all("target_error" in a.response for a in out.attempts)

    def test_filtered_to_single_channel(self):
        async def _t(_p):
            return "ok"

        probe = IndirectInjectionProbe(
            payloads=build_default_payloads(rng_seed=1)
        )
        out = asyncio.run(
            probe.run(
                target_invoke=_t,
                seed=0,
                max_turns=10,
                prompt_seed=json.dumps({"channels": ["email"]}),
            )
        )
        seen = {p["channel"] for p in out.metadata["per_test"]}
        assert seen == {"email"}

    def test_empty_payloads_aborts_cleanly(self):
        async def _t(_p):
            return "ok"

        probe = IndirectInjectionProbe(payloads=())
        out = asyncio.run(
            probe.run(target_invoke=_t, seed=0, max_turns=4, prompt_seed=None)
        )
        assert out.aborted_reason == "no_payloads"


# ════════════════════════════════════════════════════════════════════
#  Charter integration
# ════════════════════════════════════════════════════════════════════


class TestRunnerIntegration:
    def test_run_probe_emits_traces(self, monkeypatch):
        monkeypatch.setenv("REDROOM_ENABLED", "true")
        monkeypatch.setenv("REDROOM_MAX_AGGRESSIVENESS", "5")
        monkeypatch.setenv(
            "REDROOM_ALLOWED_TARGETS", "self,open_weight,public_api"
        )
        eng = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        SQLModel.metadata.create_all(eng)

        async def _t(_p):
            return "summary"

        probe = IndirectInjectionProbe(
            payloads=build_default_payloads(rng_seed=1)
        )

        with Session(eng) as session:
            out = asyncio.run(
                run_probe(
                    RunInputs(
                        technique="indirect_injection",
                        target_model_id=42,
                        tenant_id=1,
                        session_id="sess-ipi-1",
                        target_invoke=_t,
                        target_class="self",
                        aggressiveness=4,
                        seed=1,
                        max_turns=2,
                        prompt_seed=json.dumps({"channels": ["html"]}),
                    ),
                    session=session,
                    policy=load_charter(),
                    registry={"indirect_injection": probe},
                )
            )
            assert out.result is not None
            from sqlmodel import select
            rows = list(session.exec(select(RedRoomTrace)))
            assert any(r.kind == TraceKind.AUTHORIZE.value for r in rows)
            assert any(r.kind == TraceKind.PROBE.value for r in rows)

    def test_l5_refused_at_runner(self, monkeypatch):
        monkeypatch.setenv("REDROOM_ENABLED", "true")
        monkeypatch.setenv("REDROOM_MAX_AGGRESSIVENESS", "5")
        monkeypatch.setenv(
            "REDROOM_ALLOWED_TARGETS", "self,open_weight,public_api"
        )
        eng = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        SQLModel.metadata.create_all(eng)

        async def _t(_p):
            return "x"

        probe = IndirectInjectionProbe(
            payloads=build_default_payloads(rng_seed=1)
        )

        with Session(eng) as session:
            with pytest.raises(ValueError, match="capped at L4"):
                asyncio.run(
                    run_probe(
                        RunInputs(
                            technique="indirect_injection",
                            target_model_id=42,
                            tenant_id=1,
                            session_id="sess-ipi-2",
                            target_invoke=_t,
                            target_class="self",
                            aggressiveness=5,
                            seed=0,
                            max_turns=2,
                        ),
                        session=session,
                        policy=load_charter(),
                        registry={"indirect_injection": probe},
                    )
                )
