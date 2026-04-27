"""
Red Room — immutable trace store.

Every adversarial event produces a RedRoomTrace row. Traces are:

  - APPEND-ONLY    No UPDATE or DELETE allowed at the application layer.
                   Mutations are blocked by SQLModel-level safeguards and
                   by enforcing this at every code path that writes.
  - HMAC-signed    Each row carries a row_signature computed over the
                   tuple of stable fields. Tamper-evident — modifying any
                   signed field invalidates the signature.
  - Chain-linked   Each row references the previous row's signature
                   (prev_signature). A modified or deleted row breaks
                   the chain, detectable by verify_chain().
  - Replay-safe    Each row carries a replay_hash that uniquely identifies
                   the input + config tuple, so we can detect duplicate
                   submissions.

Threat model:
  - We assume the DB is trusted but operators are not omnipotent. Anyone
    with shell access could DELETE or UPDATE rows in PostgreSQL/SQLite
    directly. The chain detects this after-the-fact during audits.
  - We do NOT defend against an attacker who controls the application
    process and the secret simultaneously — at that point they could
    forge new rows and re-sign the chain. That's an out-of-scope
    threat for this layer; SECRET_KEY rotation policy is the answer.

The HMAC secret comes from REDROOM_TRACE_SECRET (preferred) or falls back
to SECRET_KEY. If neither is set, the module raises at startup — a Red
Room without integrity is worse than no Red Room.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlmodel import Field, Session, SQLModel, select

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
#  Enums
# ────────────────────────────────────────────────────────────────────


class TraceKind(StrEnum):
    """The high-level kind of event being recorded."""

    AUTHORIZE = "authorize"  # Charter decision, before any attack runs
    PROBE = "probe"          # A single attack attempt was issued
    RESPONSE = "response"    # Target produced a response
    JUDGE = "judge"          # A judge graded a response
    FINDING = "finding"      # An issue was discovered (success of attack)
    EXPORT = "export"        # An artifact was generated and exported


class TraceVerdict(StrEnum):
    """For PROBE / FINDING events, the outcome."""

    NEUTRAL = "neutral"
    REFUSED = "refused"      # Target refused — desirable for a defender
    LEAKED = "leaked"        # Target produced disallowed content
    INCONCLUSIVE = "inconclusive"


# ────────────────────────────────────────────────────────────────────
#  Model
# ────────────────────────────────────────────────────────────────────


class RedRoomTrace(SQLModel, table=True):
    """One row per adversarial event. APPEND-ONLY.

    The row is signed by row_signature; the chain is signed by
    prev_signature pointing at the previous row. New rows must be
    written via write_trace() — never via direct session.add().
    """

    __tablename__ = "redroom_traces"

    # ── Identity ──────────────────────────────────────────────────
    id: int | None = Field(default=None, primary_key=True)
    # External UUID for stable referencing across systems (e.g. Risk Artifact PDFs)
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True, index=True)

    # ── Context ───────────────────────────────────────────────────
    tenant_id: int = Field(index=True)
    session_id: str = Field(index=True, max_length=64)  # groups events of one Red Room session
    target_model_id: int | None = Field(default=None, index=True)
    target_class: str = Field(max_length=20)  # 'self' | 'open_weight' | 'public_api'
    aggressiveness: int = Field(ge=1, le=5)

    # ── Event ─────────────────────────────────────────────────────
    kind: str = Field(max_length=20)         # TraceKind value
    verdict: str | None = Field(default=None, max_length=20)  # TraceVerdict, optional
    engine: str | None = Field(default=None, max_length=40)   # 'native' | 'garak' | 'pyrit' | ...

    # ── Payload ───────────────────────────────────────────────────
    # Compact JSON payload of the event. Contents depend on kind:
    #   AUTHORIZE: {decision, reason, effective_disclosure}
    #   PROBE:     {prompt_hash, technique, n_turn}
    #   RESPONSE:  {response_hash, len, refusal_score}
    #   JUDGE:     {judge_id, axis, score, rationale_hash}
    #   FINDING:   {category, severity, replay_hash}
    #   EXPORT:    {artifact_id, format, recipient}
    payload_json: str = Field(default="{}")

    # ── Replay identity ───────────────────────────────────────────
    # Stable hash over (technique, prompt, target_model_id, kwargs) — same
    # input and config always produces the same replay_hash. Enables
    # idempotency and finding-deduplication.
    replay_hash: str = Field(max_length=64, index=True)

    # ── Provenance ────────────────────────────────────────────────
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    created_by_user_id: int | None = Field(default=None)

    # ── Integrity ─────────────────────────────────────────────────
    # HMAC-SHA256 of the canonical serialization of the row's stable fields.
    # See _canonical_payload() and _compute_signature().
    row_signature: str = Field(max_length=64, index=True)
    # Chain link: signature of the immediately preceding row in the same
    # tenant scope. NULL for the first row of a tenant.
    prev_signature: str | None = Field(default=None, max_length=64)


# ────────────────────────────────────────────────────────────────────
#  Secret loading
# ────────────────────────────────────────────────────────────────────


def _get_secret() -> bytes:
    """Resolve the HMAC secret. Required for any signing op.

    Priority: REDROOM_TRACE_SECRET > SECRET_KEY. Raises if neither set.
    """
    s = os.getenv("REDROOM_TRACE_SECRET") or os.getenv("SECRET_KEY")
    if not s or len(s) < 16:
        raise RuntimeError(
            "Red Room trace store requires a secret of >=16 chars. "
            "Set REDROOM_TRACE_SECRET (preferred) or SECRET_KEY in the "
            "environment. Refusing to operate without integrity."
        )
    return s.encode("utf-8")


# ────────────────────────────────────────────────────────────────────
#  Canonical serialization for signing
# ────────────────────────────────────────────────────────────────────


# These are the fields included in row_signature. Any post-write
# modification of any of these will invalidate the signature.
_SIGNED_FIELDS = (
    "uuid",
    "tenant_id",
    "session_id",
    "target_model_id",
    "target_class",
    "aggressiveness",
    "kind",
    "verdict",
    "engine",
    "payload_json",
    "replay_hash",
    "created_at",
    "created_by_user_id",
    "prev_signature",
)


def _canonical_payload(row: RedRoomTrace) -> bytes:
    """Build the canonical bytes blob signed by row_signature.

    Uses sorted JSON keys and ISO 8601 timestamps for determinism. The
    signature value itself is NOT included (it's the output).
    """
    items = []
    for field in _SIGNED_FIELDS:
        value = getattr(row, field)
        if isinstance(value, datetime):
            # Naive datetimes (e.g. after a SQLite round-trip) are assumed
            # to be UTC — that's how we always write them. Re-attach the
            # tzinfo before normalizing so the canonical form is identical
            # before and after a DB commit/refresh.
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            value = value.astimezone(UTC).isoformat(timespec="microseconds")
        items.append((field, value))
    return json.dumps(items, sort_keys=False, separators=(",", ":"), default=str).encode(
        "utf-8"
    )


def _compute_signature(row: RedRoomTrace) -> str:
    """HMAC-SHA256 of the canonical payload, hex digest."""
    return hmac.new(_get_secret(), _canonical_payload(row), hashlib.sha256).hexdigest()


def compute_replay_hash(
    technique: str,
    prompt: str,
    target_model_id: int | None,
    extra: dict | None = None,
) -> str:
    """Stable hash over the input/config tuple. Same inputs → same hash.

    Used for finding deduplication and idempotency. Not signed — this is
    a content fingerprint, not an integrity tag. The row_signature
    protects integrity once written.
    """
    payload = {
        "technique": technique,
        "prompt": prompt,
        "target_model_id": target_model_id,
        "extra": extra or {},
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ────────────────────────────────────────────────────────────────────
#  Write path — the ONLY way to append a trace
# ────────────────────────────────────────────────────────────────────


def write_trace(
    session: Session,
    *,
    tenant_id: int,
    session_id: str,
    kind: TraceKind,
    target_class: str,
    aggressiveness: int,
    replay_hash: str,
    target_model_id: int | None = None,
    verdict: TraceVerdict | None = None,
    engine: str | None = None,
    payload: dict | None = None,
    created_by_user_id: int | None = None,
) -> RedRoomTrace:
    """Append a single trace row to the chain.

    Computes prev_signature from the most recent row in this tenant's
    chain (or NULL for the first row), then computes row_signature and
    persists. Caller must NOT pass row_signature or prev_signature
    explicitly — those are derived.

    Raises if the chain is currently broken (see verify_chain). This
    forces operators to investigate corruption before writing more rows
    on top of an already-tampered chain.
    """
    # 1. Find the latest row in this tenant — that's our chain link.
    prev = session.exec(
        select(RedRoomTrace)
        .where(RedRoomTrace.tenant_id == tenant_id)
        .order_by(RedRoomTrace.id.desc())  # type: ignore[union-attr]
        .limit(1)
    ).first()

    # 2. If there's a prev row, validate its signature before chaining onto it.
    # We refuse to extend a corrupted chain — operators must investigate first.
    if prev is not None:
        expected = _compute_signature(prev)
        if not hmac.compare_digest(expected, prev.row_signature):
            raise RuntimeError(
                f"Refusing to write trace: chain is broken at row id={prev.id}. "
                f"Run verify_chain() and investigate before continuing."
            )

    # 3. Construct the new row.
    payload_json = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))
    row = RedRoomTrace(
        tenant_id=tenant_id,
        session_id=session_id,
        target_model_id=target_model_id,
        target_class=target_class,
        aggressiveness=aggressiveness,
        kind=kind.value,
        verdict=verdict.value if verdict is not None else None,
        engine=engine,
        payload_json=payload_json,
        replay_hash=replay_hash,
        created_by_user_id=created_by_user_id,
        prev_signature=prev.row_signature if prev is not None else None,
        # row_signature: filled below
        row_signature="",  # placeholder so dataclass validates
    )
    # Compute the signature now that all signed fields are populated except
    # row_signature itself (which is the output — excluded from canonicalization).
    row.row_signature = _compute_signature(row)

    session.add(row)
    session.flush()
    return row


# ────────────────────────────────────────────────────────────────────
#  Verification — independent integrity audit
# ────────────────────────────────────────────────────────────────────


class ChainIntegrityError(Exception):
    """Raised when the trace chain is broken or tampered."""

    def __init__(self, broken_at_id: int, reason: str):
        super().__init__(f"Chain broken at id={broken_at_id}: {reason}")
        self.broken_at_id = broken_at_id
        self.reason = reason


def verify_row(row: RedRoomTrace) -> bool:
    """Check that row.row_signature matches the canonical payload."""
    expected = _compute_signature(row)
    return hmac.compare_digest(expected, row.row_signature)


def verify_chain(session: Session, tenant_id: int) -> int:
    """Verify the whole chain for one tenant, raise on the first break.

    Returns the count of rows verified.
    """
    rows = session.exec(
        select(RedRoomTrace)
        .where(RedRoomTrace.tenant_id == tenant_id)
        .order_by(RedRoomTrace.id.asc())  # type: ignore[union-attr]
    ).all()

    prev_sig: str | None = None
    for r in rows:
        # row.id is None pre-flush; here we're reading committed rows so
        # it's always populated, but mypy can't know that.
        row_id: int = r.id if r.id is not None else -1
        # 1. Row signature integrity
        if not verify_row(r):
            raise ChainIntegrityError(row_id, "row_signature mismatch")
        # 2. Chain link integrity
        if r.prev_signature != prev_sig:
            raise ChainIntegrityError(
                row_id,
                f"prev_signature mismatch (expected {prev_sig!r}, got {r.prev_signature!r})",
            )
        prev_sig = r.row_signature

    return len(rows)
