# Changelog

<!-- TODO: document version history -->

All notable changes to Mercury Retrograde will be documented here.
> TODO: detailed changelog

All notable changes to Mercury Retrograde will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Phase E — Red Room consolidation (April 2026)
- E0: text-safety helpers, ruff/mypy strict on the redroom/ package
- E1.a: alembic migration for `redroom_traces` (revision `20260427_0001`)
- E1.b: persistent strategy memory + alembic migration for
  `redroom_strategy_memory` (revision `20260427_0002`)
- E2: `RedRoomSystem` table + `AgentStack.fingerprint()` +
  `system_id` column on traces (revision `20260427_0003`)
- E4: HTML Risk Artifact generator at
  `eval_engine.redroom.generate_html_report`
- E5: HTTP API v2 at `/api/redroom/v2/sessions`,
  `/probe`, `/traces`, `/verify`, `/artifact.html`
- E7: operations runbook at [docs/redroom-operations.md](redroom-operations.md)
- E3: optional subprocess-isolated IPI channel framing (`REDROOM_IPI_SANDBOX`,
  `eval_engine.redroom.integrations.ipi_sandbox`)

### Phase D — Red Room (April 2026)
- D0: charter — single security gate (`REDROOM_*` env vars)
- D1: HMAC-signed chain-linked trace store
- D2: native engine — AIID replay, Many-shot, Crescendo
- D3: Garak integration with sandboxed subprocess + allowlist
- D4: PyRIT integration — PAIR + TAP LLM-driven attackers
- D5: coevolution engine — Attacker × Defender × Judge with persistent memory
- D6: sandbagging detection via paired-prompt comparison
- D7: compositional attack harness for agentic stacks
- D8: indirect prompt injection (HTML / email / RAG / plaintext channels)

### Initial public release
- Initial public release of the Mercury Retrograde evaluation platform
- Support for 300+ models via OpenRouter
- Local model evaluation via Ollama
- 128+ benchmarks
- Batch evaluation campaigns
- LLM judge scoring
- Adversarial red-teaming scenarios
- Multi-tenant support
- Docker deployment
