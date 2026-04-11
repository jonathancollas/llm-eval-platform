# Mercury Retrograde — Architecture v0.5.0

> INESIA AI Evaluation Platform

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js 15 Frontend                       │
│  19 pages · Tailwind · Lucide · Recharts                    │
│                                                              │
│  Foundation: Overview, Models, Benchmarks                    │
│  Phase 1 (Static Eval): New Evaluation, Campaigns,          │
│            Dashboard, Leaderboard, Compliance                │
│  Phase 2 (Behavioral Eval): Genomia, LLM Judge, Agents,     │
│            The Red Room (REDBOX)                             │
│  Phase 3 (Real World Eval): Evidence (RCT), Workspaces,     │
│            Incidents (SIX), Monitoring                       │
│  Misc: Methodology, About                                    │
└──────────────────────┬──────────────────────────────────────┘
                       │ REST API (fetch + polling)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                FastAPI Backend (Python 3.12)                  │
│  21 routers · 161 endpoints · SQLModel ORM                  │
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
│   ├── models.py              # SQLModel tables (24 tables)
│   ├── database.py            # Engine (SQLite/PostgreSQL dual mode, WAL)
│   ├── auth.py                # Multi-tenant API key auth
│   ├── security.py            # Fernet encryption for API keys
│   ├── job_queue.py           # Async task queue (Redis/in-memory)
│   └── utils.py               # safe_extract_text, generate_text (Ollama→Anthropic)
│
├── api/routers/ (21 routers, 161 endpoints)
│   ├── models.py              # CRUD + connection test + inference adapters
│   ├── benchmarks.py          # CRUD + dataset upload + HuggingFace import + fork/card/versions
│   ├── campaigns.py           # CRUD + run/cancel + live tracking + manifest
│   ├── results.py             # Results + live feed + failed items + contamination + confidence
│   ├── reports.py             # Narrative report generation (local/Anthropic) + HTML export
│   ├── leaderboard.py         # 7 domains (incl. global) + narrative reports
│   ├── catalog.py             # Benchmark + model catalog
│   ├── sync.py                # OpenRouter + Ollama model sync + Ollama pull
│   ├── genome.py              # Genomia API (DNA profile, signals, hybrid, regression, heuristics)
│   ├── redbox.py              # Adversarial forge (ATLAS/NIST/IoPC refs) + run + heatmap + killchain
│   ├── judge.py               # Multi-judge ensemble + agreement + bias + calibration
│   ├── agents.py              # Agent trajectory eval (6 axes) + replay + step ingestion
│   ├── policy.py              # Regulatory compliance (EU AI Act, HIPAA, Finance)
│   ├── tenants.py             # Multi-tenant CRUD + key rotation + users
│   ├── research.py            # Workspaces + manifests + incidents (SIX) + telemetry + replication
│   ├── evidence.py            # RCT trials + Real World Data + Real World Evidence synthesis
│   ├── deep_analysis.py       # Model deep introspection (tokenizer, refusal probe, embeddings)
│   ├── multiagent.py          # Multi-agent simulation + sandbagging probe
│   ├── events.py              # Event-sourced campaign state + timeline + diff
│   ├── monitoring.py          # Telemetry ingestion + drift detection + integrations
│   └── science.py             # Capability/propensity · mech interp · contamination · clustering
│
├── eval_engine/
│   ├── base.py                # BaseRunner with streaming item callback
│   ├── runner.py              # Campaign orchestrator + auto-genome + auto-judge
│   ├── litellm_client.py      # 7 providers + retry + timeout
│   ├── harness_runner.py      # lm-evaluation-harness integration
│   ├── contamination.py       # 4-method contamination detection
│   ├── confidence_engine.py   # Bootstrap CI + Wilson bounds + reliability grading
│   ├── comparison_engine.py   # Campaign regression detection + delta analysis
│   ├── win_rate_engine.py     # Model win-rate pairwise ranking
│   ├── failure_clustering.py  # TF-IDF + cosine cluster discovery (no LLM)
│   ├── compositional_risk.py  # System-level threat composition scoring
│   ├── capability_propensity.py # Capability vs propensity elicitation
│   ├── mech_interp.py         # CoT faithfulness validation
│   ├── adversarial_taxonomy.py # Attack taxonomy and mutation logic
│   ├── failure_genome/
│   │   ├── ontology.py        # Taxonomy v1.0 (7 failure types)
│   │   ├── signal_extractor.py # 25+ signals per item (deterministic)
│   │   └── classifiers.py     # Rule-based + LLM hybrid blend
│   ├── sandbagging/
│   │   └── detector.py        # Sandbagging detection
│   ├── multi_agent/
│   │   └── simulator.py       # Multi-agent pipeline simulation
│   ├── custom/
│   │   └── runner.py          # Custom benchmark runner
│   ├── academic/
│   │   └── mmlu.py            # MMLU runner
│   └── safety/
│       └── refusals.py        # Safety refusal scorer
│
└── bench_library/
    ├── academic/              # MMLU, GSM8K, HellaSwag, ARC, TruthfulQA, WinoGrande, HumanEval, NQ…
    ├── coding/                # MBPP subset
    ├── safety/                # Refusals, autonomy probe
    ├── french/                # MMLU-FR, FrenchBench raisonnement
    ├── frontier/              # Cyber uplift, CBRN probe, evaluation awareness, loss of control…
    └── custom/                # MITRE ATT&CK (61 items), DISARM (32 items), scheming, sycophancy…
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
