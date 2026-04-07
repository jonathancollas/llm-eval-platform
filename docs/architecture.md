# Architecture technique — Mercury Retrograde

> Spécifications exhaustives. Version 0.5.0 — Avril 2026.

---

## 1. Vue d'ensemble

```
Browser (Next.js 15 + SWR cache)
    │
    ▼
FastAPI backend (74 endpoints, 15 routers)
    ├── SQLite / PostgreSQL (SQLModel ORM)
    ├── Redis job queue (optional, fallback asyncio)
    ├── lm-eval-harness → HuggingFace datasets
    ├── LiteLLM → OpenRouter / Anthropic / Mistral / Groq / Ollama
    ├── Anthropic SDK → rapports + judge + REDBOX forge
    └── Genomia pipeline → Signal Extractor → Classifiers → Profiles
```

### Modules

| Module | Rôle | Endpoints |
|--------|------|-----------|
| Core Eval | Campagnes, modèles, benchmarks, résultats | 25 |
| Genomia | Diagnostic structurel d'échec | 8 |
| REDBOX | Adversarial security testing | 6 |
| LLM Judge | Multi-judge evaluation | 5 |
| Agent Eval | Trajectoires multi-step | 5 |
| Compliance | Simulation réglementaire | 3 |
| Infra | Auth, sync, health | 10 |
| **Total** | | **74** |

---

## 2. Stack technique

### Backend

| Composant | Lib | Rôle |
|---|---|---|
| FastAPI ≥0.115 | Framework | API REST async |
| SQLModel ≥0.0.21 | ORM | Models + queries |
| SQLite 3.x / PostgreSQL 16+ | DB | WAL mode / Connection pooling |
| Redis 7+ (opt) | Queue | Job tracking |
| lm-evaluation-harness ≥0.4.4 | Engine | Benchmarks standardisés |
| LiteLLM ≥1.55 | Routing | 7 providers LLM |
| Ollama | Local | Modèles open-weight |
| anthropic SDK ≥0.40 | Reports | Claude Sonnet |
| cryptography (Fernet) | Security | Chiffrement clés API |

### Frontend

| Composant | Version |
|---|---|
| Next.js | 15.1.0 |
| React | 19 |
| SWR | 2.2.5 |
| Tailwind CSS | 3.x |
| Recharts | latest |
| Lucide React | 0.460 |
| Radix UI | latest |

---

## 3. Backend — FastAPI

### Routers (15 modules)

```
backend/api/routers/
├── models.py        CRUD LLMModel + test connexion + Ollama
├── benchmarks.py    CRUD + upload dataset + HuggingFace import
├── campaigns.py     CRUD + run + cancel + live tracking
├── results.py       EvalResult per-item + live feed + contamination
├── reports.py       Rapport Claude async + export HTML
├── catalog.py       Catalogue OpenRouter + 68 benchmarks INESIA
├── leaderboard.py   Agrégation domaines + rapport Claude
├── sync.py          Startup sync: benchmarks + OpenRouter + Ollama
├── genome.py        Genomia: profils + heatmap + regression
├── redbox.py        Forge + run + exploits + heatmap + replay
├── judge.py         Multi-judge + agreement + calibration + bias
├── agents.py        Trajectoires + eval 6 axes + dashboard
├── policy.py        EU AI Act + HIPAA + Finance compliance
├── tenants.py       Multi-tenant CRUD + API key rotation
└── __init__.py      Auto-import all routers
```

### Middleware stack

1. **CORS** — `allow_origins=["*"]`
2. **Rate limiting** — 120 req/min/IP
3. **Security headers** — X-Content-Type-Options, X-Frame-Options

### Job queue (dual mode)

```python
# Auto-detects Redis via REDIS_URL, falls back to asyncio
job_queue.submit_campaign(id, coro)
# Redis: hset campaign:{id} + asyncio task
# No Redis: pure asyncio.create_task()
```

---

## 4. Moteur d'évaluation

### Architecture

```
eval_engine/
├── base.py               BaseBenchmarkRunner → run() + streaming callback
├── harness_runner.py      lm-eval wrapper (sync in thread executor)
├── registry.py            Routing benchmark → runner
├── runner.py              Orchestrateur N×M + auto-genome + auto-judge
├── litellm_client.py      7 providers + retry 5xx + key masking
├── contamination.py       4 méthodes détection contamination
└── failure_genome/        Genomia pipeline (§5)
```

### Item streaming

Chaque item est persisté en DB immédiatement via `progress_callback`:

```
BaseBenchmarkRunner.run()
    for item in items:
        result = await complete(model, prompt)
        → progress_callback(idx, total, ItemResult)
            → INSERT EvalResult (powers LiveFeed)
            → UPDATE campaign.current_item_index
```

Pour HarnessRunner (sync, pas de callback) → batch insert fallback post-run.

### Post-campaign pipeline

```
Campaign completes → _compute_genome() → _auto_judge_campaign()
```

---

## 5. Failure Genome (Genomia)

3 couches de classification:

```
Layer 0: Signal Extractor (25+ signaux déterministes)
    Refusal detection (9 patterns), truth score (SequenceMatcher),
    self-contradictions, hedge count, format compliance (MCQ/JSON/code),
    repetition ratio, language detection, latency classification

Layer A: Rule-based Classifiers (7 types)
    hallucination, reasoning_collapse, instruction_drift,
    safety_bypass, over_refusal, truncation, calibration_failure

Layer B: LLM Hybrid (optionnel)
    Pour cas incertains (0.2 < prob < 0.7):
    Claude → blend 50% rules + 50% LLM
```

### Regression

- `GET /regression/compare` — diff + causal scoring
- `POST /regression/explain` — narrative Claude 5 points

---

## 6. REDBOX

```
POST /forge        → Mutations: injection, jailbreak, ambiguity,
                     contradiction, multilingual, malformed_context
POST /run          → Auto-détection brèche + severity CVSS-like
GET  /exploits     → Tracker filtrable
GET  /heatmap      → Matrice modèle × mutation
POST /replay/{id}  → Cross-model replay
POST /smart-forge  → Genome weaknesses → attaques ciblées
```

---

## 7. LLM-as-Judge

Multi-judge (Claude, GPT-4o, Gemini, Llama) + Cohen's κ + Pearson r.
Oracle calibration (CJE). Bias detection (longueur, préférence modèle).
Auto-judge post-campagne: Claude score 30 items automatiquement.

---

## 8. Agent Evaluation

6 axes: task_completion, tool_precision, planning_coherence,
error_recovery, safety_compliance, cost_efficiency.
Hybrid scoring 60% LLM + 40% rules.
Agent → Genome bridge (3 extensions: loop_collapse, tool_chain_break, goal_abandonment).

---

## 9. Compliance

| Framework | Checks | Intégration |
|-----------|--------|-------------|
| EU AI Act | 6 | Patterns + Genome + REDBOX |
| HIPAA | 5 | Patterns + Genome |
| Finance | 5 | Patterns |

---

## 10. Cross-Module Intelligence

```
Campaign → Genome → REDBOX smart-forge → breach → Genome
                 → Judge (auto 30 items)
                 → Unified Insights (signals cross-module)
         Agent trajectories → Genome profiles
```

---

## 11. Base de données

### Dual mode

```python
SQLite:     WAL mode, busy_timeout=30s, synchronous=NORMAL
PostgreSQL: pool_size=5, max_overflow=10, pool_recycle=300
            auto postgres:// → postgresql:// (Render compat)
```

### Tables principales

LLMModel, Benchmark, Campaign, EvalRun, EvalResult, FailureProfile,
ModelFingerprint, Report, RedboxExploit, JudgeEvaluation,
AgentTrajectory, Tenant, User

---

## 12. Frontend

### 13 pages

Core: Overview, Models, Benchmarks, Campaigns, Dashboard, Leaderboard
Analyzers: Genomia, LLM Judge, Agents, Compliance
Security: REDBOX

### SWR Cache (`useApi.ts`)

```typescript
useCampaigns()    // auto-refresh 3s when running
useModels()       // cached 30s, dedup
useBenchmarks()   // cached 30s
useDashboard(id)  // cached 10s, conditional
useGenome(id)     // cached 10s
useApi<T>(path)   // generic hook
```

---

## 13. Variables d'environnement

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | — | Fernet derivation (required) |
| `DATABASE_URL` | `sqlite:///./data/llm_eval.db` | SQLite or PostgreSQL |
| `ANTHROPIC_API_KEY` | — | Reports + Judge + REDBOX |
| `OPENROUTER_API_KEY` | — | 300+ cloud models |
| `OLLAMA_BASE_URL` | `localhost:11434` | Local models |
| `REDIS_URL` | — | Job queue (optional) |

---

*Mercury Retrograde v0.5.0 — INESIA AI Evaluation Platform*
