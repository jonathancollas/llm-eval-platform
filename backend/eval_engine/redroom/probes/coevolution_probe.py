"""
CoevolutionProbe — runs the D5 coevolution engine through the runner pattern.

prompt_seed is a JSON object encoding:
  {
    "objective":           "<plain text>",  (required)
    "max_rounds":          <int, default 10, capped to max_turns>,
    "success_threshold":   <float, default 0.8>,
    "epsilon":             <float, default 0.15>,
    "recency_bias":        <float, default 0.05>
  }

Memory and attacker/judge callables are injected at construction. The
probe never builds an LLM client.

Aggressiveness: L4.
"""
from __future__ import annotations

import json
from typing import Awaitable, Callable, Optional

from eval_engine.redroom.coevolution.engine import (
    CoevolutionConfig,
    run_coevolution,
)
from eval_engine.redroom.coevolution.strategy_memory import (
    Strategy,
    StrategyMemory,
)
from eval_engine.redroom.probes.base import (
    Probe,
    ProbeAttempt,
    ProbeResult,
    TargetInvoke,
)


AttackerCallable = Callable[[str], Awaitable[str]]
JudgeCallable = Callable[[str, str], Awaitable[float]]


class CoevolutionProbe(Probe):
    """L4 probe driving Attacker × Defender × Judge with persistent memory."""

    TECHNIQUE = "coevolution"
    MAX_AGGRESSIVENESS = 4

    def __init__(
        self,
        *,
        attacker: Optional[AttackerCallable] = None,
        judge: Optional[JudgeCallable] = None,
        memory: Optional[StrategyMemory] = None,
    ):
        super().__init__()
        self._attacker = attacker
        self._judge = judge
        self._memory = memory

    async def run(
        self,
        *,
        target_invoke: TargetInvoke,
        seed: int,
        max_turns: int,
        prompt_seed: Optional[str] = None,
    ) -> ProbeResult:
        if not prompt_seed:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": "prompt_seed required (JSON config)"},
                aborted_reason="missing_prompt_seed",
            )
        try:
            cfg_raw = json.loads(prompt_seed)
        except json.JSONDecodeError as exc:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": f"invalid JSON: {exc}"},
                aborted_reason="bad_prompt_seed",
            )
        if not isinstance(cfg_raw, dict):
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": "prompt_seed JSON must be an object"},
                aborted_reason="bad_prompt_seed",
            )
        objective = cfg_raw.get("objective")
        if not isinstance(objective, str) or not objective.strip():
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": "objective is required (non-empty string)"},
                aborted_reason="bad_prompt_seed",
            )

        if self._attacker is None or self._judge is None or self._memory is None:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={
                    "error": (
                        "CoevolutionProbe requires attacker, judge, and memory; "
                        "construct with attacker=, judge=, memory=."
                    )
                },
                aborted_reason="missing_dependencies",
            )

        try:
            cfg = CoevolutionConfig(
                objective=objective,
                max_rounds=min(int(cfg_raw.get("max_rounds", max_turns)), int(max_turns)),
                success_threshold=float(cfg_raw.get("success_threshold", 0.8)),
                epsilon=float(cfg_raw.get("epsilon", 0.15)),
                recency_bias=float(cfg_raw.get("recency_bias", 0.05)),
                seed=int(seed),
            )
        except (ValueError, TypeError) as exc:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": f"{type(exc).__name__}: {exc}"},
                aborted_reason="bad_prompt_seed",
            )

        try:
            result = await run_coevolution(
                target=target_invoke,
                attacker=self._attacker,
                judge=self._judge,
                memory=self._memory,
                config=cfg,
            )
        except ValueError as exc:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": f"engine_error: {exc}"},
                aborted_reason="engine_error",
            )

        attempts = tuple(
            ProbeAttempt(
                turn=r.turn,
                prompt=f"[{r.strategy_name}] {r.prompt}",
                response=r.response,
            )
            for r in result.rounds
        )

        return ProbeResult(
            technique=self.TECHNIQUE,
            attempts=attempts,
            metadata={
                "objective": result.objective,
                "stop_reason": result.stop_reason,
                "success": result.success,
                "success_threshold": result.success_threshold,
                "n_rounds": len(result.rounds),
                "max_score": max((r.score for r in result.rounds), default=0.0),
                "final_top_strategies": [
                    {
                        "name": s.name,
                        "posterior": round(s.posterior_score(), 4),
                        "n_tried": s.n_tried,
                    }
                    for s in result.final_top_strategies
                ],
            },
        )
