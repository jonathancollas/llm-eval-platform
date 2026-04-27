# Red Room — Operations Runbook

This runbook covers day-2 operations for the Red Room subsystem
(`backend/eval_engine/redroom/`). Read it end-to-end before enabling
the module in production.

## What the Red Room is

A charter-gated, append-only, HMAC-chain-audited adversarial
evaluation pipeline for AI systems. Every probe — from inert AIID
replays (D2 / L1) to compositional attacks on full agentic stacks
(D7 / L5) — runs through a single `run_probe()` entry point that:

1. Calls `charter.enforce()` (rejects anything outside policy with 403).
2. Writes an `AUTHORIZE` trace to `redroom_traces`.
3. Invokes the probe with a wall-clock timeout.
4. Writes `PROBE` / `RESPONSE` traces per turn (hash-only payloads).
5. Writes a summary `PROBE` trace at the end.

A separate `EXPORT` trace is written when a `Risk Artifact` HTML is
generated. Every row carries an HMAC `row_signature` and a
`prev_signature` linking back to the previous row in the tenant's
chain. `verify_chain()` walks the chain and reports `BROKEN` on the
first signature mismatch.

## Aggressiveness model

| Level | What runs at this level                                         |
|-------|-----------------------------------------------------------------|
| L1    | Inert probes: AIID replay against deterministic scenarios.      |
| L2    | Multi-turn templated: many-shot, Crescendo. No LLM attacker.    |
| L3    | LLM-driven attacker: Garak (D3), PyRIT PAIR/TAP (D4), sandbagging (D6). |
| L4    | Coevolution (D5) with persistent memory. IPI (D8).              |
| L5    | Compositional attacks against full agent stacks (D7).           |

Three independent ceilings enforce the policy:

1. `CharterPolicy.max_aggressiveness` (env, deployment-wide).
2. `Probe.MAX_AGGRESSIVENESS` (per-probe class attribute).
3. The runner's pre-call check `inputs.aggressiveness > probe.MAX_AGGRESSIVENESS`.

A request must pass all three.

## Enabling the Red Room in a deployment

The module is **OFF by default**. Set:

```bash
REDROOM_ENABLED=true
REDROOM_ALLOWED_TARGETS=self,open_weight     # add public_api only after legal sign-off
REDROOM_MAX_AGGRESSIVENESS=2                  # L2 = templated multi-turn; bump to 3 for LLM attackers
REDROOM_TRACE_SECRET=<32+ char secret>        # required, distinct from SECRET_KEY for clean rotation
```

Optional, with sensible defaults:

```bash
REDROOM_REQUIRE_CONSENT_ABOVE=none            # 1..5 or 'none'
REDROOM_REQUIRE_DUAL_APPROVAL_ABOVE=none
REDROOM_DEFAULT_DISCLOSURE=vendor             # internal | vendor | aiid
REDROOM_FORCE_VENDOR_ON_PUBLIC_API=true
REDROOM_MAX_TOKENS_PER_RUN=100000
REDROOM_MAX_DURATION_SECONDS=1800
REDROOM_MAX_CONCURRENT_PER_TENANT=2
```

Operators who want a softer rollout can require explicit user consent
above a chosen aggressiveness level via `REDROOM_REQUIRE_CONSENT_ABOVE`,
or require two admin signers for high-aggressiveness runs via
`REDROOM_REQUIRE_DUAL_APPROVAL_ABOVE`.

## Database migrations

Apply the relevant alembic migrations to a fresh deployment:

```bash
cd backend
PYTHONPATH=. alembic upgrade head
```

Red Room tables added in order:

| Revision        | Adds                                           |
|-----------------|------------------------------------------------|
| `20260427_0001` | `redroom_traces`                               |
| `20260427_0002` | `redroom_strategy_memory` (D5 persistence)     |
| `20260427_0003` | `redroom_systems` + `redroom_traces.system_id` |

All migrations are idempotent (`if_not_exists=True` everywhere) and
have working `downgrade()` paths.

## Rotating REDROOM_TRACE_SECRET

The HMAC secret is the integrity root. Rotating it invalidates every
existing `row_signature`, so it's a controlled operation:

1. **Snapshot** the current chain. Export every tenant's
   `Risk Artifact` HTML before rotating — those PDFs/HTMLs are the
   off-line audit record.
2. **Roll the secret**: set `REDROOM_TRACE_SECRET=<new>` and restart
   the workers. New rows are signed with the new secret; old rows
   become `BROKEN` under the new secret.
3. **Mark the boundary**: emit one `EXPORT` trace per tenant with
   payload `{"event": "secret_rotation", "rotated_at": ISO8601}`.
   Auditors then know to verify pre-rotation chains against the
   archived secret if needed.

We deliberately **do not** support multi-secret-aware verification —
a verifier that accepts multiple secrets is a softer integrity
property than a verifier that rejects post-rotation tampering.

## Auditing a chain

```python
from sqlmodel import Session
from eval_engine.redroom.trace_store import verify_chain, ChainIntegrityError

with Session(engine) as s:
    try:
        n = verify_chain(s, tenant_id=42)
        print(f"OK: {n} rows verified")
    except ChainIntegrityError as e:
        print(f"BROKEN at row {e.broken_at_id}: {e.reason}")
```

Or via HTTP:

```http
GET /api/redroom/v2/sessions/<session_id>/verify
```

```json
{
  "session_id": "sess-abc123",
  "tenant_id": 42,
  "status": "ok",
  "rows_verified": 17,
  "reason": ""
}
```

A `BROKEN` status means **someone tampered with a row in the database
directly** (the application layer never modifies signed rows). Investigate:

1. Pull the tenant's chain ordered by `id`.
2. Identify the broken row from `broken_at_row_id`.
3. Compare its signed fields to the application audit log (e.g.
   what the worker thought it wrote).
4. Roll the secret if you suspect compromise.

## What goes in the trace store

Every adversarial event lands as one row. The `payload_json` is
intentionally **hash-only** for prompt and response text — operators
who need raw text use the `replay_hash` to re-run the probe
deterministically.

The text-safety helpers in `redroom/_text_safety.py` enforce this:

- `hash_text(s)` → sha256[:16]
- `text_envelope(s, name=...)` → `{name_hash, name_len}`
- `truncate_error(s, max_chars=80)` for component error strings

If a new probe leaks raw text into payloads, that's a regression to
fix in the probe — not in the trace store.

## Risk Artifact

Every session that produced traces should generate a Risk Artifact:

```http
GET /api/redroom/v2/sessions/<session_id>/artifact.html
```

The artifact:

- Lists charter decision, target metadata, full timeline.
- Shows chain integrity status from `verify_chain()`.
- Embeds only signature hashes and structured payloads — never raw
  prompts/responses.
- Is self-contained HTML — no external assets, opens in any browser
  without network access.

Vendor disclosure track is the default; the artifact's
`effective_disclosure` field reflects what the charter decided for
this run.

A new `EXPORT` trace is appended when an artifact is generated, so
the artifact's existence is itself audit-evident.

## Failure modes

| Symptom                                    | Most likely cause                                   |
|--------------------------------------------|-----------------------------------------------------|
| Every probe returns 403                    | `REDROOM_ENABLED=false` or wrong target_class.      |
| L4+ refused with "above max"               | `REDROOM_MAX_AGGRESSIVENESS=2` (default), bump it.  |
| `verify_chain` reports BROKEN              | Direct DB write to `redroom_traces` (forbidden).    |
| Probe times out, summary trace says "inconclusive" | Target slow / network. Increase `timeout_seconds`. |
| `chain is broken at row id=X` raised       | Refusing to extend a tampered chain. Investigate.   |
| `Refusing to operate without integrity`    | `REDROOM_TRACE_SECRET` < 16 chars or unset.         |

## What's still in flight

Tracked separately as Phase E follow-ups:

- **D8 sandbox** (`E3`): the `IndirectInjectionProbe` currently uses
  pure-string framings (no real subprocess sandbox). Production
  deployment should use cgroups/Bubblewrap/Docker isolation. **Manual
  review of the sandbox required before push.**
- **Frontend UI** (`E6`): no `/redroom` page yet; the v2 HTTP API is
  callable but unsurfaced. The legacy `/redbox` page will be replaced
  progressively.
- **Wiring real model adapters** (`E5+`): the v2 HTTP router currently
  uses a deterministic stub for target invocations. Real LLM adapter
  wiring is a separate PR.
- **PDF Risk Artifact**: HTML only today. PDF via WeasyPrint /
  pandoc deferred.
