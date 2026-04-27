"""Tests for the Risk Artifact HTML generator."""
from __future__ import annotations

import os
import re
import secrets
import sys

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("REDROOM_TRACE_SECRET", "x" * 32 + "_test_secret")
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from eval_engine.redroom import (  # noqa: E402
    TraceKind,
    generate_html_report,
)
from eval_engine.redroom.trace_store import (  # noqa: E402
    RedRoomTrace,
    TraceVerdict,
    compute_replay_hash,
    write_trace,
)


@pytest.fixture
def session():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


def _seed_authorize_and_probe(session, *, tenant_id=1, session_id="s-1"):
    """Write a typical mini chain: AUTHORIZE → PROBE+RESPONSE → final PROBE."""
    rh = compute_replay_hash("native", "x", 1)
    write_trace(
        session,
        tenant_id=tenant_id,
        session_id=session_id,
        kind=TraceKind.AUTHORIZE,
        target_class="self",
        aggressiveness=2,
        replay_hash=rh,
        target_model_id=1,
        engine="native",
        payload={
            "session_uuid": "abc-123",
            "technique": "many_shot",
            "decision_reason": "ok",
            "effective_disclosure": "vendor",
            "max_turns": 4,
        },
    )
    write_trace(
        session,
        tenant_id=tenant_id,
        session_id=session_id,
        kind=TraceKind.PROBE,
        target_class="self",
        aggressiveness=2,
        replay_hash=rh,
        target_model_id=1,
        engine="native",
        verdict=TraceVerdict.NEUTRAL,
        payload={"turn": 0, "prompt_hash": "deadbeef", "prompt_len": 200},
    )
    write_trace(
        session,
        tenant_id=tenant_id,
        session_id=session_id,
        kind=TraceKind.RESPONSE,
        target_class="self",
        aggressiveness=2,
        replay_hash=rh,
        target_model_id=1,
        engine="native",
        verdict=TraceVerdict.LEAKED,
        payload={"turn": 0, "response_hash": "cafebabe", "response_len": 500},
    )
    session.commit()


# ════════════════════════════════════════════════════════════════════
#  Validation
# ════════════════════════════════════════════════════════════════════


class TestInputValidation:
    def test_invalid_tenant_id(self, session):
        with pytest.raises(ValueError):
            generate_html_report(
                session, tenant_id=0, session_id="x"
            )

    def test_empty_session_id(self, session):
        with pytest.raises(ValueError):
            generate_html_report(
                session, tenant_id=1, session_id=""
            )


# ════════════════════════════════════════════════════════════════════
#  Empty / missing data
# ════════════════════════════════════════════════════════════════════


class TestEmpty:
    def test_no_traces_returns_minimal_doc(self, session):
        out = generate_html_report(
            session, tenant_id=1, session_id="missing"
        )
        assert "<!DOCTYPE html>" in out
        assert "No traces recorded" in out
        # No EXPORT trace was emitted because there were no rows.
        rows = list(session.exec(select(RedRoomTrace)))
        assert len(rows) == 0

    def test_no_traces_ok_chain_status(self, session):
        out = generate_html_report(
            session, tenant_id=1, session_id="missing"
        )
        assert "Chain integrity" in out
        assert "OK" in out


# ════════════════════════════════════════════════════════════════════
#  Happy path
# ════════════════════════════════════════════════════════════════════


class TestHappyPath:
    def test_authorize_section_renders(self, session):
        _seed_authorize_and_probe(session)
        out = generate_html_report(session, tenant_id=1, session_id="s-1")
        assert "Charter authorization" in out
        assert "many_shot" in out
        assert "vendor" in out
        assert "abc-123" in out

    def test_timeline_lists_each_trace(self, session):
        _seed_authorize_and_probe(session)
        out = generate_html_report(session, tenant_id=1, session_id="s-1")
        assert out.count("<li>") >= 3  # AUTHORIZE + PROBE + RESPONSE

    def test_summary_counts_findings(self, session):
        _seed_authorize_and_probe(session)
        out = generate_html_report(session, tenant_id=1, session_id="s-1")
        m = re.search(r"Verdicts marked.*?(\d+)", out)
        assert m and int(m.group(1)) == 1  # one "leaked"

    def test_export_trace_appended(self, session):
        _seed_authorize_and_probe(session)
        before = len(list(session.exec(select(RedRoomTrace))))
        generate_html_report(session, tenant_id=1, session_id="s-1")
        after = list(session.exec(select(RedRoomTrace)))
        # one EXPORT row appended
        assert len(after) == before + 1
        assert after[-1].kind == TraceKind.EXPORT.value
        assert after[-1].engine == "risk_artifact"

    def test_emit_export_trace_off_does_not_extend_chain(self, session):
        _seed_authorize_and_probe(session)
        before = len(list(session.exec(select(RedRoomTrace))))
        generate_html_report(
            session, tenant_id=1, session_id="s-1", emit_export_trace=False
        )
        after = len(list(session.exec(select(RedRoomTrace))))
        assert after == before

    def test_custom_artifact_id_appears_in_output(self, session):
        _seed_authorize_and_probe(session)
        out = generate_html_report(
            session,
            tenant_id=1,
            session_id="s-1",
            artifact_id="MERC-1234",
        )
        assert "MERC-1234" in out


# ════════════════════════════════════════════════════════════════════
#  Tenant isolation
# ════════════════════════════════════════════════════════════════════


class TestTenantIsolation:
    def test_other_tenants_data_does_not_leak(self, session):
        _seed_authorize_and_probe(session, tenant_id=1, session_id="s-1")
        _seed_authorize_and_probe(session, tenant_id=2, session_id="s-1")

        out_tenant1 = generate_html_report(
            session, tenant_id=1, session_id="s-1", emit_export_trace=False
        )
        # Tenant 1's report references rows from tenant 1 only. Count
        # timeline entries by extracting the timeline <section> block —
        # the summary section also uses <li>, so a naive count is wrong.
        m = re.search(
            r'<section class="rh-timeline.*?>(.*?)</section>',
            out_tenant1,
            re.DOTALL,
        )
        assert m is not None
        timeline = m.group(1)
        n_timeline_items = timeline.count("<li>")
        assert n_timeline_items == 3  # AUTHORIZE + PROBE + RESPONSE


# ════════════════════════════════════════════════════════════════════
#  Chain status
# ════════════════════════════════════════════════════════════════════


class TestChainStatus:
    def test_broken_chain_marked_in_report(self, session):
        _seed_authorize_and_probe(session)
        # Tamper with a row's payload.
        rows = list(session.exec(select(RedRoomTrace)))
        rows[0].payload_json = '{"evil": true}'
        session.add(rows[0])
        session.commit()

        out = generate_html_report(
            session, tenant_id=1, session_id="s-1", emit_export_trace=False
        )
        # The chain should now show as BROKEN.
        assert "BROKEN" in out
