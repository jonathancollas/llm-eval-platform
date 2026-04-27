"""Coevolution — Attacker × Defender × Judge with persistent memory.

Phase D / D5. Where D3/D4 use one-shot / iterative attackers, D5 maintains
a memory of strategies across runs and lets the attacker prefer
strategies that have historically scored well, while penalising those
that consistently failed. The defender is the target model; the judge
scores each round.

Aggressiveness: L4 — by definition.

The memory is opaque to the LLMs themselves: it lives in StrategyMemory,
which is updated by the engine after each round based on judge scores.
"""
from eval_engine.redroom.coevolution.calibration import (
    CalibrationItem,
    CalibrationReport,
    calibrate_judge,
)
from eval_engine.redroom.coevolution.engine import (
    CoevolutionConfig,
    CoevolutionResult,
    CoevolutionRound,
    run_coevolution,
)
from eval_engine.redroom.coevolution.persistent_memory import (
    PersistentStrategyMemory,
)
from eval_engine.redroom.coevolution.strategy_memory import (
    Strategy,
    StrategyMemory,
)

__all__ = [
    "Strategy",
    "StrategyMemory",
    "PersistentStrategyMemory",
    "CoevolutionConfig",
    "CoevolutionResult",
    "CoevolutionRound",
    "run_coevolution",
    "CalibrationItem",
    "CalibrationReport",
    "calibrate_judge",
]
