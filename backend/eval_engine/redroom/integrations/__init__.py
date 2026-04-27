"""External adversarial framework integrations.

Each integration lives in its own submodule and exposes a Probe subclass
that the runner can register. The integration is responsible for:

  - Allowlisting which probes from the external tool are usable.
  - Sandboxing any subprocess invocation (timeout, env scrub, no shell).
  - Translating the tool's output into ProbeAttempt records.

The runner remains the only sanctioned entry point — integrations never
write to the trace store directly; they return ProbeResult and the
runner emits the traces.

Phase D mapping:
  D3 -> garak_runner.py
  D4 -> pyrit_runner.py
"""
from eval_engine.redroom.integrations.garak_runner import (
    GARAK_ALLOWLIST,
    GarakAllowlistError,
    GarakSubprocessError,
    GarakRunner,
    run_garak_subprocess,
)

__all__ = [
    "GARAK_ALLOWLIST",
    "GarakAllowlistError",
    "GarakSubprocessError",
    "GarakRunner",
    "run_garak_subprocess",
]
