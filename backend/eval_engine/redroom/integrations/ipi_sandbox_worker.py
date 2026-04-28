"""Stdin/stdout JSON worker for :mod:`ipi_sandbox` (runs in a subprocess).

Expected stdin: JSON object ``{"channel", "injection", "benign_paragraph"}``.
Stdout: JSON ``{"wrapped": "<framed document>"}`` or ``{"error": "..."}``.
"""
from __future__ import annotations

import json
import sys

from eval_engine.redroom.probes.indirect_injection import (
    VALID_CHANNELS,
    channel_wrappers,
)


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid JSON: {exc}"}))
        sys.exit(1)

    channel = data.get("channel")
    injection = data.get("injection")
    benign = data.get("benign_paragraph")

    if not isinstance(channel, str) or channel not in VALID_CHANNELS:
        print(json.dumps({"error": "bad or missing channel"}))
        sys.exit(2)
    if not isinstance(injection, str) or not isinstance(benign, str):
        print(json.dumps({"error": "injection and benign_paragraph must be strings"}))
        sys.exit(2)

    wrap = channel_wrappers[channel]
    wrapped = wrap(injection, benign)
    print(json.dumps({"wrapped": wrapped}, ensure_ascii=False))


if __name__ == "__main__":
    main()
