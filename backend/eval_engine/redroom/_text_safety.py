"""Audit-friendly text helpers for the Red Room.

The trace store is append-only and tamper-evident — but it's also
intended to be auditable. Storing user-controlled raw text (objectives,
prompts, error messages from external tools) inflates the audit log,
leaks sensitive content, and makes export to vendors harder.

These helpers give every probe a uniform way to record "I saw this
text" without storing the text itself.

Convention used across the codebase:
  - prompt_hash:        sha256 hex, first 16 chars
  - <field>_hash:       sha256 hex, first 16 chars
  - <field>_len:        original byte length
  - <field>_redacted:   first 32 chars + "..." (only when explicitly
                        labelled redacted; never the default)
"""
from __future__ import annotations

import hashlib

_HASH_PREFIX_CHARS = 16


def hash_text(s: object) -> str:
    """Stable short hash. Coerces to str; treats None as empty.

    ``hash_text("hello") == hash_text("hello")`` is guaranteed across
    runs and machines.
    """
    blob = ("" if s is None else str(s)).encode("utf-8", errors="replace")
    return hashlib.sha256(blob).hexdigest()[:_HASH_PREFIX_CHARS]


def text_envelope(s: object, *, name: str) -> dict:
    """Return a 2-key envelope ``{<name>_hash, <name>_len}`` for the trace.

    Use everywhere that you'd otherwise have shoved raw text into a
    payload dict.
    """
    text = "" if s is None else str(s)
    return {
        f"{name}_hash": hash_text(text),
        f"{name}_len": len(text),
    }


def truncate_error(s: object, *, max_chars: int = 80) -> str:
    """Trim a Python-level error message for inclusion in a trace.

    Long stack-traces, multi-line subprocess stderr, etc. inflate the
    audit log and may contain paths / tokens / tenant data. Truncate to
    the first ``max_chars`` chars.
    """
    if s is None:
        return ""
    body = str(s)
    if len(body) <= max_chars:
        return body
    return body[: max_chars - 1] + "…"
