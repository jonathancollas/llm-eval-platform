"""Red Room — adversarial evaluation subsystem.

See charter.py for the rules of engagement. No code outside this package
runs adversarial workloads; charter.enforce() is the single gate.
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

__all__ = [
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
]
