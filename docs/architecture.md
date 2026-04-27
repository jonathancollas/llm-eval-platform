# Architecture

<!-- TODO: document the platform architecture -->

Mercury Retrograde follows a modular architecture built around:

- **FastAPI** backend
- **Next.js** frontend
- **SQLite / PostgreSQL** for persistence
- **Redis + Celery** for async task execution
- **Docker** for deployment
- Multi-tenant support
> TODO: detailed architecture documentation

## Overview

Mercury Retrograde is composed of the following layers:

- **Frontend** — Next.js application for evaluation dashboards, campaigns, and leaderboards
- **Backend** — FastAPI service exposing the evaluation engine, benchmark management, and multi-tenant APIs
- **Eval Engine** — Core evaluation logic with support for LLM judges, harness runners, and agent trajectory evaluation
- **Storage** — SQLite (development) / PostgreSQL (production) with Alembic migrations
- **Task Queue** — Redis + Celery for asynchronous evaluation runs
- **Deployment** — Docker Compose for local and self-hosted deployments

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.11+ |
| Database | SQLite / PostgreSQL |
| Queue | Redis, Celery |
| AI Integrations | OpenRouter, Ollama, Anthropic |
| Deployment | Docker, Docker Compose |

## Red Room — adversarial subsystem

The `backend/eval_engine/redroom/` package implements Phase D of the
platform: a charter-gated, audit-evident adversarial pipeline. It sits
above the evaluation layer and is invoked through a single sanctioned
entry point so no probe can run outside the policy.

```
backend/eval_engine/redroom/
├── charter.py             D0 — single security gate
├── trace_store.py         D1 — HMAC-signed chain
├── runner.py              D2 — wires charter + trace + probe
├── probes/                native + Garak + PyRIT + sandbagging + IPI + composition
├── coevolution/           D5 — Attacker × Defender × Judge with memory
├── composition/           D7 — system-level attacks (RedRoomSystem)
├── integrations/          subprocess wrappers (Garak, PyRIT)
├── risk_artifact.py       E4 — HTML report
└── _text_safety.py        E0 — hash-only payload helpers
```

HTTP surface: `/api/redroom/v2/*` (see
[redroom-operations.md](redroom-operations.md)).

Every adversarial event lands as a row in `redroom_traces`. Each row
carries a `row_signature` (HMAC-SHA256) and a `prev_signature`
linking back to the previous row in the tenant's chain — modifying
or deleting any row breaks the chain and is detected by
`verify_chain()`. Operators audit chains via the v2 API or by
running `verify_chain()` directly.
