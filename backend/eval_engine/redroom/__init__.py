"""Red Room — adversarial evaluation subsystem.

See charter.py for the rules of engagement. No code outside this package
runs adversarial workloads; charter.enforce() is the single gate.

trace_store.py provides the immutable, HMAC-signed record of every event.
Every adversarial code path MUST write to it via write_trace().
"""
from eval_engine.redroom.charter import (
    Aggressiveness,
    AttackRequest,
    CharterDecision,
    CharterPolicy,
    TargetClass,
    DisclosureTrack,
    authorize,
    enforce,
    load_charter,
    announce_charter_at_startup,
)
from eval_engine.redroom.trace_store import (
    RedRoomTrace,
    TraceKind,
    TraceVerdict,
    ChainIntegrityError,
    write_trace,
    verify_row,
    verify_chain,
    compute_replay_hash,
)

__all__ = [
    # charter
    "Aggressiveness",
    "AttackRequest",
    "CharterDecision",
    "CharterPolicy",
    "TargetClass",
    "DisclosureTrack",
    "authorize",
    "enforce",
    "load_charter",
    "announce_charter_at_startup",
    # trace_store
    "RedRoomTrace",
    "TraceKind",
    "TraceVerdict",
    "ChainIntegrityError",
    "write_trace",
    "verify_row",
    "verify_chain",
    "compute_replay_hash",
]
