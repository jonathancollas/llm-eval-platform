"""Tests for the Red Room trace store.

Covers:
  - Single-row signing and verification
  - Chain linkage across multiple writes
  - Tamper detection on every signed field
  - Replay hash determinism
  - Refusal to write on top of a broken chain
  - Tenant isolation of chains
  - Secret rotation invalidates signatures (audit trail discipline)
"""
from __future__ import annotations

import json
import os
import sys

import pytest
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set the trace secret BEFORE importing the module so it's stable.
os.environ.setdefault("REDROOM_TRACE_SECRET", "x" * 32 + "_test_secret")

from eval_engine.redroom.trace_store import (  # noqa: E402
    ChainIntegrityError,
    RedRoomTrace,
    TraceKind,
    TraceVerdict,
    compute_replay_hash,
    verify_chain,
    verify_row,
    write_trace,
    _compute_signature,
)


# ════════════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════════════


@pytest.fixture
def session():
    """In-memory SQLite session with the schema created."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _write(session, **overrides):
    """Convenience wrapper for write_trace with sensible defaults."""
    base = dict(
        tenant_id=1,
        session_id="sess-A",
        kind=TraceKind.PROBE,
        target_class="self",
        aggressiveness=2,
        replay_hash=compute_replay_hash("crescendo", "test-prompt", 42),
        target_model_id=42,
        verdict=TraceVerdict.NEUTRAL,
        engine="native",
        payload={"technique": "crescendo", "n_turn": 1},
        created_by_user_id=99,
    )
    base.update(overrides)
    row = write_trace(session, **base)
    session.commit()
    return row


# ════════════════════════════════════════════════════════════════════════
#  Single-row signing
# ════════════════════════════════════════════════════════════════════════


class TestRowSigning:
    def test_fresh_row_verifies(self, session):
        row = _write(session)
        assert verify_row(row) is True

    def test_signature_is_64_hex_chars(self, session):
        row = _write(session)
        assert len(row.row_signature) == 64
        # SHA-256 hex digest
        int(row.row_signature, 16)  # raises if not hex

    def test_uuid_is_unique(self, session):
        r1 = _write(session)
        r2 = _write(session)
        assert r1.uuid != r2.uuid

    def test_tampered_payload_invalidates_signature(self, session):
        row = _write(session)
        # Mutate a signed field WITHOUT updating the signature.
        row.payload_json = json.dumps({"technique": "different"})
        assert verify_row(row) is False

    def test_tampered_aggressiveness_invalidates_signature(self, session):
        row = _write(session)
        row.aggressiveness = 5  # was 2
        assert verify_row(row) is False

    def test_tampered_tenant_invalidates_signature(self, session):
        row = _write(session)
        row.tenant_id = 999  # was 1
        assert verify_row(row) is False

    def test_tampered_verdict_invalidates_signature(self, session):
        row = _write(session)
        row.verdict = TraceVerdict.LEAKED.value  # was NEUTRAL
        assert verify_row(row) is False


# ════════════════════════════════════════════════════════════════════════
#  Chain linkage
# ════════════════════════════════════════════════════════════════════════


class TestChain:
    def test_first_row_has_null_prev(self, session):
        row = _write(session)
        assert row.prev_signature is None

    def test_subsequent_rows_link_to_previous(self, session):
        r1 = _write(session)
        r2 = _write(session)
        r3 = _write(session)
        assert r2.prev_signature == r1.row_signature
        assert r3.prev_signature == r2.row_signature

    def test_verify_chain_passes_clean_chain(self, session):
        for _ in range(5):
            _write(session)
        count = verify_chain(session, tenant_id=1)
        assert count == 5

    def test_verify_chain_empty_returns_zero(self, session):
        count = verify_chain(session, tenant_id=1)
        assert count == 0

    def test_verify_chain_detects_signature_tamper(self, session):
        r1 = _write(session)
        r2 = _write(session)
        # Tamper with r1's payload — signature now mismatches
        r1.payload_json = json.dumps({"evil": True})
        session.add(r1)
        session.commit()

        with pytest.raises(ChainIntegrityError) as exc:
            verify_chain(session, tenant_id=1)
        assert exc.value.broken_at_id == r1.id
        assert "row_signature mismatch" in exc.value.reason

    def test_verify_chain_detects_chain_link_tamper(self, session):
        r1 = _write(session)
        r2 = _write(session)
        r3 = _write(session)
        # Tamper with r2's prev_signature — chain link to r1 broken
        # Recompute r2's row signature so the row itself looks valid.
        r2.prev_signature = "0" * 64
        r2.row_signature = _compute_signature(r2)
        session.add(r2)
        session.commit()

        with pytest.raises(ChainIntegrityError) as exc:
            verify_chain(session, tenant_id=1)
        # The chain link mismatch is what breaks first
        assert exc.value.broken_at_id == r2.id
        assert "prev_signature mismatch" in exc.value.reason

    def test_verify_chain_detects_deleted_middle_row(self, session):
        r1 = _write(session)
        r2 = _write(session)
        r3 = _write(session)
        # Delete r2 — r3 still points at r2's signature, which no longer
        # follows from r1 directly. The chain link check on r3 fires.
        session.delete(r2)
        session.commit()

        with pytest.raises(ChainIntegrityError) as exc:
            verify_chain(session, tenant_id=1)
        assert exc.value.broken_at_id == r3.id

    def test_write_refuses_when_chain_is_broken(self, session):
        r1 = _write(session)
        r2 = _write(session)
        # Corrupt r2 (the latest row)
        r2.payload_json = json.dumps({"evil": True})
        session.add(r2)
        session.commit()

        # Next write must refuse rather than chain on top of a broken row
        with pytest.raises(RuntimeError, match="chain is broken"):
            _write(session)


# ════════════════════════════════════════════════════════════════════════
#  Tenant isolation
# ════════════════════════════════════════════════════════════════════════


class TestTenantIsolation:
    def test_chains_are_per_tenant(self, session):
        # Tenant 1 chain
        a1 = _write(session, tenant_id=1, session_id="sess-T1")
        a2 = _write(session, tenant_id=1, session_id="sess-T1")
        # Tenant 2 chain — independent
        b1 = _write(session, tenant_id=2, session_id="sess-T2")
        b2 = _write(session, tenant_id=2, session_id="sess-T2")

        # Each tenant's chain is internally consistent
        assert a2.prev_signature == a1.row_signature
        assert b2.prev_signature == b1.row_signature
        # And independent of the other tenant
        assert b1.prev_signature is None
        assert a1.row_signature != b1.row_signature

    def test_verify_chain_passes_tenant_independently(self, session):
        for _ in range(3):
            _write(session, tenant_id=1)
        for _ in range(2):
            _write(session, tenant_id=2)
        assert verify_chain(session, tenant_id=1) == 3
        assert verify_chain(session, tenant_id=2) == 2


# ════════════════════════════════════════════════════════════════════════
#  Replay hash
# ════════════════════════════════════════════════════════════════════════


class TestReplayHash:
    def test_same_inputs_same_hash(self):
        h1 = compute_replay_hash("crescendo", "Tell me a secret.", 42)
        h2 = compute_replay_hash("crescendo", "Tell me a secret.", 42)
        assert h1 == h2

    def test_different_technique_different_hash(self):
        h1 = compute_replay_hash("crescendo", "Tell me.", 42)
        h2 = compute_replay_hash("many_shot", "Tell me.", 42)
        assert h1 != h2

    def test_different_prompt_different_hash(self):
        h1 = compute_replay_hash("crescendo", "Prompt A", 42)
        h2 = compute_replay_hash("crescendo", "Prompt B", 42)
        assert h1 != h2

    def test_different_target_different_hash(self):
        h1 = compute_replay_hash("crescendo", "P", 42)
        h2 = compute_replay_hash("crescendo", "P", 99)
        assert h1 != h2

    def test_extra_dict_affects_hash(self):
        h1 = compute_replay_hash("crescendo", "P", 42, {"a": 1})
        h2 = compute_replay_hash("crescendo", "P", 42, {"a": 2})
        assert h1 != h2

    def test_extra_dict_order_independent(self):
        h1 = compute_replay_hash("c", "P", 1, {"a": 1, "b": 2})
        h2 = compute_replay_hash("c", "P", 1, {"b": 2, "a": 1})
        assert h1 == h2


# ════════════════════════════════════════════════════════════════════════
#  Secret rotation
# ════════════════════════════════════════════════════════════════════════


class TestSecretRotation:
    def test_changing_secret_invalidates_existing_signatures(self, session, monkeypatch):
        row = _write(session)
        original_sig = row.row_signature
        assert verify_row(row) is True

        # Rotate the secret. Signatures previously written are no longer valid
        # under the new secret — this is intentional and gives operators an
        # audit signal: any chain that doesn't verify after rotation must
        # have been signed under a different key, which they need to track.
        monkeypatch.setenv("REDROOM_TRACE_SECRET", "y" * 40 + "_rotated")
        assert verify_row(row) is False, (
            "Rotating the secret must invalidate prior signatures. "
            "Operators handle this by re-signing or archiving the old chain."
        )


# ════════════════════════════════════════════════════════════════════════
#  Missing secret
# ════════════════════════════════════════════════════════════════════════


class TestMissingSecret:
    def test_no_secret_refuses_to_sign(self, session, monkeypatch):
        monkeypatch.delenv("REDROOM_TRACE_SECRET", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError, match="requires a secret"):
            _write(session)

    def test_short_secret_refused(self, session, monkeypatch):
        monkeypatch.setenv("REDROOM_TRACE_SECRET", "short")
        monkeypatch.delenv("SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError, match="requires a secret"):
            _write(session)
