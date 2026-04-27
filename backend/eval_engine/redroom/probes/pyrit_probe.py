"""
PyRITProbe — runs PAIR or TAP through the runner pattern.

The probe takes ``prompt_seed`` as a JSON object encoding:
  {
    "technique":          "pair" | "tap",   # required
    "objective":          "<plain text>",   # required
    "initial_prompt":     "<optional>",
    "max_rounds":         <int, default depends on technique>,
    "success_threshold":  <float, default 0.8>,
    "branching_factor":   <int, TAP only>,
    "beam_width":         <int, TAP only>
  }

Attacker and judge callables are NOT taken from prompt_seed — they're
provided to the probe constructor so the runner controls which LLMs
play those roles. The probe itself never instantiates LLM clients.

For tests, callers inject deterministic mock attackers and judges; in
production the wiring layer plugs in the platform's chosen attacker
and judge models (which still go through the regular inference path,
respecting tenant quotas).

Aggressiveness: L3 — LLM-driven attacker tier.
"""
from __future__ import annotations

import json
from typing import Awaitable, Callable, Optional

from eval_engine.redroom.integrations.pyrit_runner import (
    PYRIT_ALLOWLIST,
    PyRITAllowlistError,
    PyRITRunner,
)
from eval_engine.redroom.probes.base import (
    Probe,
    ProbeAttempt,
    ProbeResult,
    TargetInvoke,
)


AttackerCallable = Callable[[str], Awaitable[str]]
JudgeCallable = Callable[[str, str], Awaitable[float]]


class PyRITProbe(Probe):
    """LLM-driven attacker probe (PAIR or TAP)."""

    TECHNIQUE = "pyrit"
    MAX_AGGRESSIVENESS = 3

    def __init__(
        self,
        *,
        attacker: Optional[AttackerCallable] = None,
        judge: Optional[JudgeCallable] = None,
        runner: Optional[PyRITRunner] = None,
    ):
        super().__init__()
        self._attacker = attacker
        self._judge = judge
        self._runner = runner or PyRITRunner()

    async def run(
        self,
        *,
        target_invoke: TargetInvoke,
        seed: int,
        max_turns: int,
        prompt_seed: Optional[str] = None,
    ) -> ProbeResult:
        del seed  # algorithms are stateless w.r.t. seed in our impl
        if not prompt_seed:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={
                    "error": "prompt_seed required (JSON config object)",
                    "allowlist": sorted(PYRIT_ALLOWLIST),
                },
                aborted_reason="missing_prompt_seed",
            )

        try:
            cfg = json.loads(prompt_seed)
        except json.JSONDecodeError as exc:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": f"invalid JSON in prompt_seed: {exc}"},
                aborted_reason="bad_prompt_seed",
            )

        if not isinstance(cfg, dict):
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": "prompt_seed JSON must be an object"},
                aborted_reason="bad_prompt_seed",
            )

        technique = str(cfg.get("technique", "")).lower()
        objective = cfg.get("objective")
        if not objective or not isinstance(objective, str):
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": "objective is required and must be a string"},
                aborted_reason="bad_prompt_seed",
            )

        if self._attacker is None or self._judge is None:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={
                    "error": (
                        "PyRITProbe requires attacker and judge callables; "
                        "construct with attacker=, judge=."
                    )
                },
                aborted_reason="missing_callables",
            )

        try:
            algo_kwargs = {
                "technique": technique,
                "target": target_invoke,
                "attacker": self._attacker,
                "judge": self._judge,
                "objective": objective,
                "max_rounds": min(int(cfg.get("max_rounds", max_turns)), int(max_turns)),
                "success_threshold": float(cfg.get("success_threshold", 0.8)),
                "initial_prompt": cfg.get("initial_prompt"),
            }
            if technique == "tap":
                algo_kwargs["branching_factor"] = int(cfg.get("branching_factor", 2))
                algo_kwargs["beam_width"] = int(cfg.get("beam_width", 2))

            result = await self._runner.run(**algo_kwargs)
        except PyRITAllowlistError as exc:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": str(exc), "technique": technique},
                aborted_reason="technique_not_allowlisted",
            )
        except (TypeError, ValueError) as exc:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": f"{type(exc).__name__}: {exc}"},
                aborted_reason="bad_prompt_seed",
            )

        attempts = tuple(
            ProbeAttempt(turn=r.turn, prompt=r.prompt, response=r.response)
            for r in result.rounds
        )

        meta = {
            **result.metadata,
            "n_rounds": len(result.rounds),
            "success": result.success,
            "success_threshold": result.success_threshold,
            "max_score": max((r.score for r in result.rounds), default=0.0),
        }

        return ProbeResult(
            technique=self.TECHNIQUE,
            attempts=attempts,
            metadata=meta,
            aborted_reason=None if result.success else None,
        )
