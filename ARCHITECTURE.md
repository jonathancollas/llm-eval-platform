# Mercury Retrograde — Architecture v0.5.0

> INESIA AI Evaluation Platform

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js 15 Frontend                       │
│  13 pages · Tailwind · Lucide · Recharts                    │
│                                                              │
│  Core: Overview, Models, Benchmarks, Campaigns,             │
│        Dashboard, Leaderboard                                │
│  Analyzers: Genomia, LLM Judge, Agents, Compliance          │
│  Security: REDBOX (adversarial lab)                          │
└──────────────────────┬──────────────────────────────────────┘
                       │ REST API (fetch + polling)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                FastAPI Backend (Python 3.12)                  │
│  15 routers · 74 endpoints · SQLModel ORM                   │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ Eval     │  │ Genomia  │  │ REDBOX   │  │ Judge      │  │
│  │ Engine   │  │ Engine   │  │ Forge    │  │ Ensemble   │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬──────┘  │
│       │             │             │               │          │
│  ┌────┴─────────────┴─────────────┴───────────────┴──────┐  │
│  │              Cross-Module Intelligence                 │  │
│  │  Auto-judge · Genome→REDBOX · Agent→Genome · Insights │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ LiteLLM │  │ Anthropic│  │ Ollama   │  │ lm-eval    │  │
│  │ Router  │  │ SDK      │  │ Local    │  │ Harness    │  │
│  └─────────┘  └──────────┘  └──────────┘  └────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   ┌─────────┐   ┌─────────┐   ┌──────────┐
   │ SQLite  │   │PostgreSQL│   │  Redis   │
   │  (dev)  │   │  (prod)  │   │(optional)│
   └─────────┘   └─────────┘   └──────────┘
```

## Backend Structure

```
backend/
├── main.py                    # FastAPI app, CORS, startup, health
├── core/
│   ├── config.py              # Pydantic settings (env vars)
│   ├── models.py              # SQLModel tables (13 models)
│   ├── database.py            # Engine (SQLite/PostgreSQL dual mode, WAL)
│   ├── auth.py                # Multi-tenant API key auth
│   ├── security.py            # Fernet encryption for API keys
│   ├── job_queue.py           # Async task queue (Redis/in-memory)
│   └── utils.py               # safe_extract_text, generate_text (Ollama→Anthropic)
│
├── api/routers/ (15 routers, 74 endpoints)
│   ├── models.py              # CRUD + connection test
│   ├── benchmarks.py          # CRUD + dataset upload + HuggingFace import
│   ├── campaigns.py           # CRUD + run/cancel + live tracking
│   ├── results.py             # Results + live feed + failed items + contamination
│   ├── reports.py             # Narrative report generation (local/Anthropic)
│   ├── leaderboard.py         # 6 domains + narrative reports
│   ├── catalog.py             # Benchmark catalog
│   ├── sync.py                # OpenRouter + Ollama model sync
│   ├── genome.py              # Genomia API (DNA profile, signals, hybrid, regression)
│   ├── redbox.py              # Adversarial forge (ATLAS/NIST/IoPC refs) + run + heatmap
│   ├── judge.py               # Multi-judge ensemble + agreement + bias + calibration
│   ├── agents.py              # Agent trajectory eval (6 axes)
│   ├── policy.py              # Regulatory compliance (EU AI Act, HIPAA, Finance)
│   └── tenants.py             # Multi-tenant CRUD + key rotation
│
├── eval_engine/
│   ├── base.py                # BaseRunner with streaming item callback
│   ├── runner.py              # Campaign orchestrator + auto-genome + auto-judge
│   ├── litellm_client.py      # 7 providers + retry + timeout
│   ├── harness_runner.py      # lm-evaluation-harness integration
│   ├── contamination.py       # 4-method contamination detection
│   └── failure_genome/
│       ├── ontology.py        # Taxonomy v1.0 (7 failure types)
│       ├── signal_extractor.py # 25+ signals per item (deterministic)
│       └── classifiers.py     # Rule-based + LLM hybrid blend
│
└── bench_library/custom/
    ├── mitre_attack_cyber.json        # 61 items · 14 ATT&CK tactics
    └── disarm_info_manipulation.json  # 32 items · 12 DISARM phases
```

## Adversarial References (REDBOX)

| Framework | Coverage | Usage |
|-----------|----------|-------|
| MITRE ATLAS | AML.T0051, T0054, T0043, T0052 | Mutation type mapping |
| NIST AI 100-2 | §4.3 Cross-lingual attacks | Multilingual mutations |
| OWASP LLM Top 10 | LLM01 Prompt Injection | Contradiction mutations |
| SecurityBreak IoPC | Adversarial prompt patterns | Template inspiration |
| MITRE ATT&CK | 14 tactics, 61 techniques | Cyber benchmark |
| DISARM Red | 12 phases, 32 techniques | Info manipulation benchmark |

## Model Providers (7)

| Provider | Routing | Notes |
|----------|---------|-------|
| OpenRouter | `openrouter/{id}` | 300+ models, :free tier |
| Ollama | `ollama/{id}` | Local, free, auto-discovered |
| OpenAI | `{id}` direct | GPT-4o, o1, etc. |
| Anthropic | `anthropic/{id}` | Claude family |
| Mistral | `mistral/{id}` | Mistral/Mixtral |
| Groq | `groq/{id}` | Fast inference |
| Custom | `openai/{id}` + endpoint | Any OpenAI-compatible |

## Cross-Module Intelligence

```
Campaign completes
  → auto Failure Genome (rule-based, instant)
  → auto LLM Judge (30 items, local or Claude)
  → genome weaknesses → REDBOX smart-forge targeting
  → breach results → genome feedback loop
  → /insights endpoint unifies all signals
  → agent trajectories → genome profile bridge
```

---

*Mercury Retrograde v0.5.0 — INESIA 2025-2026*
