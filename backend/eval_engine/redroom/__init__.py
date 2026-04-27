"""Red Room — adversarial evaluation subsystem.

See charter.py for the rules of engagement. No code outside this package
runs adversarial workloads; charter.enforce() is the single gate.

trace_store.py provides the immutable, HMAC-signed record of every event.
Every adversarial code path MUST write to it via write_trace().

runner.py provides run_probe() — the single sanctioned entry point for
the native engine. It wires charter.enforce() + write_trace() + a probe
together so callers cannot accidentally skip authorization or auditing.
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
from eval_engine.redroom.runner import (
    RunInputs,
    RunOutput,
    run_probe,
    build_default_registry,
)
from eval_engine.redroom.integrations.garak_runner import (
    GARAK_ALLOWLIST,
    GarakAllowlistError,
    GarakSubprocessError,
    GarakRunner,
)
from eval_engine.redroom.integrations.pyrit_runner import (
    PYRIT_ALLOWLIST,
    PyRITAllowlistError,
    PyRITSubprocessError,
    PyRITRunner,
)
from eval_engine.redroom.coevolution import (
    CalibrationItem,
    CalibrationReport,
    CoevolutionConfig,
    CoevolutionResult,
    CoevolutionRound,
    Strategy,
    StrategyMemory,
    calibrate_judge,
    run_coevolution,
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
    # runner
    "RunInputs",
    "RunOutput",
    "run_probe",
    "build_default_registry",
    # integrations
    "GARAK_ALLOWLIST",
    "GarakAllowlistError",
    "GarakSubprocessError",
    "GarakRunner",
    "PYRIT_ALLOWLIST",
    "PyRITAllowlistError",
    "PyRITSubprocessError",
    "PyRITRunner",
    # coevolution (D5)
    "Strategy",
    "StrategyMemory",
    "CoevolutionConfig",
    "CoevolutionResult",
    "CoevolutionRound",
    "run_coevolution",
    "CalibrationItem",
    "CalibrationReport",
    "calibrate_judge",
]
