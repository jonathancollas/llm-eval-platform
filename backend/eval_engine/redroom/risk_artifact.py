"""
Risk Artifact generator — HTML.

Per the platform's scope decision: every Red Room session that produces
findings should generate a Risk Artifact for vendor disclosure. This
module produces a self-contained HTML document from the trace store
for a single session.

PDF rendering is deliberately deferred to a follow-up (operators can
always print-to-PDF the HTML or pipe it through ``pandoc``/``weasyprint``).

What's in the report:
  - Header: tenant + session UUID + generation time + charter status
  - Charter decision (from the AUTHORIZE trace)
  - Target metadata (model id + class + aggressiveness)
  - Timeline of every trace (kind, verdict, payload summary)
  - Breach summary (from FINDING/PROBE traces)
  - Chain integrity verdict (verify_chain result)
  - Replay instructions (technique + replay_hash)

What's NOT in the report (by design):
  - Raw prompts/responses — only their hashes. Operators who need raw
    text run a replay against the same (technique, seed, prompt_seed).
  - Other sessions' data (cross-session leak prevention).
  - Anything outside the requesting tenant's scope.
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import logging

from sqlmodel import Session, select

from eval_engine.redroom.trace_store import (
    ChainIntegrityError,
    RedRoomTrace,
    TraceKind,
    compute_replay_hash,
    verify_chain,
    write_trace,
)

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
#  Public entry point
# ────────────────────────────────────────────────────────────────────


def generate_html_report(
    session: Session,
    *,
    tenant_id: int,
    session_id: str,
    emit_export_trace: bool = True,
    artifact_id: str | None = None,
) -> str:
    """Build the HTML Risk Artifact for one session.

    Args:
        session:            DB session.
        tenant_id:          required — refuses to read traces outside
                            this tenant.
        session_id:         the Red Room session to report on.
        emit_export_trace:  when True, append an EXPORT trace to the
                            chain so the artifact's existence is itself
                            audit-evident.
        artifact_id:        caller-supplied id; defaults to "<session_id>-<ts>".

    Returns the HTML as a string. Empty trace lists produce a minimal
    "no data" report rather than raising — this keeps the API safe
    from operator typos.
    """
    if tenant_id <= 0:
        raise ValueError("tenant_id must be a positive integer")
    if not session_id or not isinstance(session_id, str):
        raise ValueError("session_id must be a non-empty string")

    rows = list(
        session.exec(
            select(RedRoomTrace)
            .where(
                RedRoomTrace.tenant_id == tenant_id,
                RedRoomTrace.session_id == session_id,
            )
            .order_by(RedRoomTrace.id.asc())  # type: ignore[union-attr]
        )
    )

    artifact_id = artifact_id or _default_artifact_id(session_id)
    chain_status, chain_detail = _verify_chain_safe(session, tenant_id)

    html_doc = _render(
        rows=rows,
        artifact_id=artifact_id,
        tenant_id=tenant_id,
        session_id=session_id,
        chain_status=chain_status,
        chain_detail=chain_detail,
    )

    if emit_export_trace:
        # Use the most recent row's context as the AUTHORIZE-equivalent
        # for the EXPORT trace. If there are zero rows we don't emit
        # anything — exporting an empty report shouldn't extend a chain.
        if rows:
            last = rows[-1]
            try:
                write_trace(
                    session,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    kind=TraceKind.EXPORT,
                    target_class=last.target_class,
                    aggressiveness=last.aggressiveness,
                    replay_hash=compute_replay_hash(
                        "risk_artifact", artifact_id, last.target_model_id
                    ),
                    target_model_id=last.target_model_id,
                    engine="risk_artifact",
                    payload={
                        "artifact_id": artifact_id,
                        "format": "html",
                        "n_rows_summarised": len(rows),
                        "chain_status": chain_status,
                    },
                )
                session.commit()
            except RuntimeError as exc:
                logger.warning(
                    "risk_artifact: chain broken, skipping EXPORT trace: %s",
                    exc,
                )

    return html_doc


# ────────────────────────────────────────────────────────────────────
#  Rendering
# ────────────────────────────────────────────────────────────────────


def _render(
    *,
    rows: list[RedRoomTrace],
    artifact_id: str,
    tenant_id: int,
    session_id: str,
    chain_status: str,
    chain_detail: str,
) -> str:
    e = html.escape  # local alias for terse templating
    now_iso = _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")

    # Pull out the AUTHORIZE row if present (always the first, by design).
    auth = next(
        (r for r in rows if r.kind == TraceKind.AUTHORIZE.value), None
    )
    findings = [r for r in rows if r.kind == TraceKind.FINDING.value]
    breached = sum(1 for r in rows if (r.verdict or "") == "leaked")

    # Components
    head = f"""
    <header class="rh">
      <h1>Mercury Retrograde — Risk Artifact</h1>
      <dl class="rh-meta">
        <dt>Artifact</dt><dd>{e(artifact_id)}</dd>
        <dt>Tenant</dt><dd>{tenant_id}</dd>
        <dt>Session</dt><dd>{e(session_id)}</dd>
        <dt>Generated</dt><dd>{e(now_iso)}</dd>
        <dt>Chain integrity</dt>
        <dd class="rh-chain rh-chain-{e(chain_status)}">{e(chain_status)}: {e(chain_detail)}</dd>
      </dl>
    </header>
    """

    summary = f"""
    <section class="rh-summary">
      <h2>Summary</h2>
      <ul>
        <li>Total traces: {len(rows)}</li>
        <li>Findings: {len(findings)}</li>
        <li>Verdicts marked &quot;leaked&quot;: {breached}</li>
      </ul>
    </section>
    """

    auth_block = _render_authorize(auth, e) if auth else (
        "<section class=\"rh-auth rh-auth-none\">"
        "<h2>Charter authorization</h2>"
        "<p>No AUTHORIZE trace recorded for this session.</p>"
        "</section>"
    )

    timeline = _render_timeline(rows, e) if rows else (
        "<section class=\"rh-timeline rh-timeline-empty\">"
        "<h2>Timeline</h2><p>No traces recorded.</p></section>"
    )

    body = head + summary + auth_block + timeline

    return _wrap_doc(body=body, title=f"Risk Artifact {artifact_id}")


def _render_authorize(row: RedRoomTrace, e) -> str:
    payload = _safe_load_json(row.payload_json)
    technique = payload.get("technique", "(unknown)")
    decision_reason = payload.get("decision_reason", "(unknown)")
    effective_disclosure = payload.get("effective_disclosure", "(unknown)")
    session_uuid = payload.get("session_uuid", "(unknown)")
    return f"""
    <section class="rh-auth">
      <h2>Charter authorization</h2>
      <dl>
        <dt>Technique</dt><dd>{e(str(technique))}</dd>
        <dt>Target class</dt><dd>{e(row.target_class)}</dd>
        <dt>Aggressiveness</dt><dd>L{row.aggressiveness}</dd>
        <dt>Decision reason</dt><dd>{e(str(decision_reason))}</dd>
        <dt>Disclosure track</dt><dd>{e(str(effective_disclosure))}</dd>
        <dt>Session UUID</dt><dd><code>{e(str(session_uuid))}</code></dd>
      </dl>
    </section>
    """


def _render_timeline(rows: list[RedRoomTrace], e) -> str:
    parts = ["<section class=\"rh-timeline\"><h2>Timeline</h2><ol>"]
    for r in rows:
        verdict_html = (
            f" <span class=\"rh-verdict rh-v-{e(r.verdict or 'none')}\">"
            f"{e(r.verdict)}</span>"
            if r.verdict
            else ""
        )
        engine_html = (
            f" <span class=\"rh-engine\">{e(r.engine)}</span>"
            if r.engine
            else ""
        )
        payload = _safe_load_json(r.payload_json)
        compact = _summarise_payload(payload)
        sig_short = (r.row_signature or "")[:12]
        parts.append(
            "<li>"
            f"<time datetime=\"{e(r.created_at.isoformat())}\">"
            f"{e(r.created_at.isoformat(timespec='seconds'))}</time>"
            f" <strong>{e(r.kind)}</strong>{verdict_html}{engine_html}"
            f" <span class=\"rh-sig\">{e(sig_short)}</span>"
            f"<pre class=\"rh-payload\">{e(compact)}</pre>"
            "</li>"
        )
    parts.append("</ol></section>")
    return "".join(parts)


def _summarise_payload(payload: dict) -> str:
    """Compact JSON dump of the payload — already hash-only thanks to E0."""
    if not payload:
        return "(empty)"
    try:
        return json.dumps(payload, sort_keys=True, indent=2, default=str)
    except (TypeError, ValueError):
        return "(unrenderable payload)"


def _wrap_doc(*, body: str, title: str) -> str:
    """Self-contained HTML document. No external assets — vendor can
    open it in any browser without network access."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --omni-ink: #1a0035;
      --omni-bone: #f5f2ea;
      --omni-rust: #b03a2e;
      --omni-sage: #6c8b76;
    }}
    body {{
      font-family: 'Geist', system-ui, sans-serif;
      background: var(--omni-bone);
      color: var(--omni-ink);
      margin: 0;
      padding: 2rem 3rem;
      line-height: 1.55;
    }}
    h1 {{ font-family: 'Fraunces', Georgia, serif; font-weight: 700; }}
    h2 {{ font-family: 'Fraunces', Georgia, serif; margin-top: 2rem; }}
    .rh-meta dt {{
      font-weight: 600;
      width: 12rem;
      float: left;
      clear: left;
    }}
    .rh-meta dd {{ margin: 0 0 .25rem 12rem; }}
    .rh-chain-OK {{ color: var(--omni-sage); }}
    .rh-chain-BROKEN {{ color: var(--omni-rust); font-weight: 700; }}
    .rh-summary ul {{ list-style: square; }}
    .rh-timeline ol {{ list-style: none; padding-left: 0; }}
    .rh-timeline li {{
      border-left: 3px solid var(--omni-ink);
      padding: .5rem 1rem;
      margin: .5rem 0;
      background: rgba(26, 0, 53, 0.03);
    }}
    .rh-payload {{
      font-family: 'JetBrains Mono', monospace;
      font-size: .85rem;
      background: rgba(26, 0, 53, 0.06);
      padding: .5rem .75rem;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .rh-sig {{
      font-family: 'JetBrains Mono', monospace;
      color: rgba(26, 0, 53, 0.55);
      font-size: .8rem;
    }}
    .rh-verdict {{
      font-weight: 600;
      padding: 0 .35rem;
      border-radius: 3px;
      background: rgba(26, 0, 53, 0.1);
    }}
    .rh-v-leaked {{ color: var(--omni-rust); }}
    .rh-v-refused {{ color: var(--omni-sage); }}
    .rh-engine {{ color: rgba(26, 0, 53, 0.7); }}
    time {{ color: rgba(26, 0, 53, 0.7); }}
    code {{ font-family: 'JetBrains Mono', monospace; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


# ────────────────────────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────────────────────────


def _safe_load_json(blob: str) -> dict:
    if not blob:
        return {}
    try:
        out = json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        return {}
    return out if isinstance(out, dict) else {}


def _verify_chain_safe(
    session: Session, tenant_id: int
) -> tuple[str, str]:
    """Wrap verify_chain into a status string — never raises."""
    try:
        n = verify_chain(session, tenant_id)
        return "OK", f"{n} rows verified"
    except ChainIntegrityError as exc:
        return "BROKEN", str(exc)
    except Exception as exc:  # noqa: BLE001
        return "ERROR", f"{type(exc).__name__}: {exc}"


def _default_artifact_id(session_id: str) -> str:
    ts = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{session_id}-{ts}"
