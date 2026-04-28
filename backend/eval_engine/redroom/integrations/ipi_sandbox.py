"""
E3 — Sandboxed framing for D8 indirect prompt injection channels.

When ``REDROOM_IPI_SANDBOX`` is truthy, each channel wrapper (HTML / email /
RAG / plaintext) runs in a short-lived subprocess with:

  - ``shell=False`` and a fixed ``python -m`` argv (no user-controlled tokens).
  - A fresh temporary working directory.
  - Environment scrubbed to the same minimal allowlist as Garak/PyRIT
    integrations (no API keys forwarded).
  - Bounded stdin size and wall-clock timeout.

The worker process only executes the bundled string wrappers from
``indirect_injection`` — identical output to in-process framing. This adds
process isolation so a future buggy or malicious extension to channel logic
cannot directly access the API process memory (defense-in-depth).

This is **not** a container escape hatch or network egress filter; operators
who need OS-level isolation should wrap the whole worker in Docker/bubblewrap
via deployment policy (see runbook).
"""
from __future__ import annotations

import json
import os
import subprocess  # noqa: S404 — sandboxed via no-shell + fixed argv
import sys
import tempfile
from pathlib import Path

# Same minimal env keys as garak_runner / pyrit_runner.
_SCRUBBED_ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR")

# Hard cap for JSON payload on stdin (injection + benign text + channel name).
_MAX_STDIN_BYTES = 512 * 1024

# Wall-clock cap for the helper process (framing is trivial; keep tight).
_DEFAULT_TIMEOUT_SECONDS = 30
_MAX_TIMEOUT_SECONDS = 120

# backend/ — must be on PYTHONPATH for `python -m eval_engine...`.
_BACKEND_ROOT = Path(__file__).resolve().parents[3]


class IpiSandboxError(RuntimeError):
    """Subprocess framing failed, timed out, or returned invalid output."""


def _scrubbed_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _SCRUBBED_ENV_KEEP if k in os.environ}
    env["PYTHONPATH"] = str(_BACKEND_ROOT)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _timeout_seconds() -> int:
    raw = os.environ.get("REDROOM_IPI_SANDBOX_TIMEOUT", "")
    if not raw.strip():
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        return max(1, min(int(raw), _MAX_TIMEOUT_SECONDS))
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS


def wrap_channel_subprocess(
    channel: str,
    injection: str,
    benign_paragraph: str,
) -> str:
    """Run the IPI channel wrapper in an isolated subprocess; return framed text."""
    # Import inside function to avoid cycles at module load.
    from eval_engine.redroom.probes.indirect_injection import (  # noqa: PLC0415
        VALID_CHANNELS,
    )

    if channel not in VALID_CHANNELS:
        raise IpiSandboxError(
            f"channel {channel!r} not in allowlist {sorted(VALID_CHANNELS)}"
        )
    payload = json.dumps(
        {
            "channel": channel,
            "injection": injection,
            "benign_paragraph": benign_paragraph,
        },
        ensure_ascii=False,
    )
    if len(payload.encode("utf-8")) > _MAX_STDIN_BYTES:
        raise IpiSandboxError(
            f"IPI framing payload exceeds {_MAX_STDIN_BYTES} bytes"
        )

    argv = [
        sys.executable,
        "-m",
        "eval_engine.redroom.integrations.ipi_sandbox_worker",
    ]
    timeout = _timeout_seconds()

    with tempfile.TemporaryDirectory(prefix="ipi_sandbox_") as workdir:
        try:
            proc = subprocess.run(  # noqa: S603 — argv fixed; no shell
                argv,
                input=payload,
                text=True,
                capture_output=True,
                timeout=timeout,
                cwd=workdir,
                env=_scrubbed_env(),
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise IpiSandboxError(
                f"IPI sandbox subprocess exceeded {timeout}s"
            ) from exc

    if proc.returncode != 0:
        err_hint = (proc.stderr or proc.stdout or "").strip()[:2000]
        raise IpiSandboxError(
            f"IPI sandbox worker exited {proc.returncode}: {err_hint}"
        )

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise IpiSandboxError(
            f"IPI sandbox returned non-JSON stdout: {proc.stdout[:500]!r}"
        ) from exc

    if "error" in data:
        raise IpiSandboxError(str(data["error"]))
    wrapped = data.get("wrapped")
    if not isinstance(wrapped, str):
        raise IpiSandboxError("IPI sandbox response missing wrapped string")

    return wrapped
