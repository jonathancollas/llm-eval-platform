"""
GarakProbe — a Probe that runs an allowlisted Garak probe through the
runner pattern (charter + trace).

The probe takes a Garak probe name in ``prompt_seed`` (e.g.
"dan.Dan_11_0"). Validation is delegated to GarakRunner; only names in
GARAK_ALLOWLIST are accepted.

Aggressiveness: L3. Garak's probes include LLM-driven attackers (Dan,
TAP equivalents). The runner's MAX_AGGRESSIVENESS check refuses any
Garak invocation above L3.

Execution mode is "static corpus" — we call target_invoke with each
prompt from the embedded corpus. The real Garak subprocess wrapper
(integrations.garak_runner.run_garak_subprocess) is available for
operators who want to invoke the full Garak scanner; that's a future
runner option, not the default.
"""
from __future__ import annotations

from typing import Optional

from eval_engine.redroom.integrations.garak_runner import (
    GARAK_ALLOWLIST,
    GarakAllowlistError,
    GarakRunner,
)
from eval_engine.redroom.probes.base import (
    Probe,
    ProbeAttempt,
    ProbeResult,
    TargetInvoke,
)


class GarakProbe(Probe):
    """Runs an allowlisted Garak probe via the static-corpus path."""

    TECHNIQUE = "garak"
    MAX_AGGRESSIVENESS = 3

    def __init__(self, runner: Optional[GarakRunner] = None):
        super().__init__()
        self._runner = runner or GarakRunner()

    async def run(
        self,
        *,
        target_invoke: TargetInvoke,
        seed: int,
        max_turns: int,
        prompt_seed: Optional[str] = None,
    ) -> ProbeResult:
        del seed  # static corpus — same prompts regardless of seed
        if not prompt_seed:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={
                    "error": "prompt_seed required (Garak probe name)",
                    "allowlist": sorted(GARAK_ALLOWLIST),
                },
                aborted_reason="missing_prompt_seed",
            )

        try:
            static = await self._runner.run_static(prompt_seed, target_invoke)
        except GarakAllowlistError as exc:
            return ProbeResult(
                technique=self.TECHNIQUE,
                attempts=(),
                metadata={"error": str(exc), "garak_probe": prompt_seed},
                aborted_reason="probe_not_allowlisted",
            )

        # Cap to max_turns — Garak corpora are short but the runner
        # contract honors the ceiling regardless.
        capped = static[: max(1, int(max_turns))]
        attempts = tuple(
            ProbeAttempt(turn=i, prompt=a.prompt, response=a.response)
            for i, a in enumerate(capped)
        )

        return ProbeResult(
            technique=self.TECHNIQUE,
            attempts=attempts,
            metadata={
                "garak_probe": prompt_seed,
                "n_prompts_run": len(attempts),
                "n_prompts_in_corpus": len(static),
                "execution_mode": "static",
            },
        )
