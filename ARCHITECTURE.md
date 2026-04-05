# Architecture technique — Mercury Retrograde

> Spécifications exhaustives. Version 0.3.0 — Avril 2026.

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Stack technique](#2-stack-technique)
3. [Backend — FastAPI](#3-backend--fastapi)
4. [Moteur d'évaluation](#4-moteur-dévaluation)
5. [Base de données](#5-base-de-données)
6. [Frontend — Next.js](#6-frontend--nextjs)
7. [Sécurité](#7-sécurité)
8. [Déploiement](#8-déploiement)
9. [Flux de données](#9-flux-de-données)
10. [Variables d'environnement](#10-variables-denvironnement)
11. [API Reference](#11-api-reference)
12. [Décisions d'architecture](#12-décisions-darchitecture)

---

## 1. Vue d'ensemble

Deux services Docker indépendants communiquant via REST :

```
Browser (Next.js 15)
    │ NEXT_PUBLIC_API_URL
    ▼
FastAPI backend
    ├── SQLite (SQLModel)
    ├── lm-eval-harness → HuggingFace datasets
    ├── LiteLLM → OpenRouter / Anthropic / Ollama
    └── Anthropic SDK → rapports Claude
```

URLs de production :
- Frontend : https://llm-eval-frontend.onrender.com
- Backend  : https://llm-eval-backend-kqlh.onrender.com

---

## 2. Stack technique

### Backend

| Composant | Lib | Version |
|---|---|---|
| Framework | FastAPI | ≥0.115 |
| ORM | SQLModel | ≥0.0.21 |
| DB | SQLite | 3.x |
| ASGI | Uvicorn | ≥0.34 |
| Eval engine | lm-evaluation-harness | ≥0.4.4 |
| Datasets | HuggingFace datasets | ≥2.18 |
| LLM routing | LiteLLM | ≥1.55 |
| Chiffrement | cryptography (Fernet) | ≥43.0 |
| HTTP client | httpx | ≥0.28 |
| Rapports IA | anthropic SDK | ≥0.40 |
| Config | pydantic-settings | ≥2.7 |

### Frontend

| Composant | Lib | Version |
|---|---|---|
| Framework | Next.js | 15.1.0 |
| Runtime | React | 19 |
| Style | Tailwind CSS | 3.x |
| Charts | Recharts | latest |
| Icons | Lucide React | 0.383.0 |
| Markdown | react-markdown | latest |
| Build | Node.js | 20 Alpine |

---

## 3. Backend — FastAPI

### Routers (8 modules)

```
backend/api/routers/
├── models.py       CRUD LLMModel + test connexion live
├── benchmarks.py   CRUD Benchmark + upload dataset JSON
├── campaigns.py    CRUD + run + cancel + progress polling
├── results.py      EvalResult per-item
├── reports.py      Rapport Claude par campagne
├── catalog.py      Catalogue OpenRouter (live) + 68 benchmarks (static)
├── leaderboard.py  Agrégation par domaine + rapport Claude
└── sync.py         Startup sync : benchmarks + modèles OpenRouter
```

### Lifespan

```python
@asynccontextmanager
async def lifespan(app):
    create_db_and_tables()   # idempotent
    yield
```

### CORS

```python
CORSMiddleware(allow_origins=["*"], allow_credentials=False)
```

API publique, pas d'authentification cookie. Pour multi-tenant : restreindre origins + activer credentials.

### Job queue asyncio

Pas de Celery ni Redis. Tâches asyncio natives :

```python
async def submit_campaign(campaign_id):
    task = asyncio.create_task(execute_campaign(campaign_id))
    _tasks[campaign_id] = task

async def cancel_campaign(campaign_id):
    if task := _tasks.get(campaign_id):
        task.cancel()
```

Limite : campagnes séquentielles (1 process). Acceptable pour usage INESIA.

---

## 4. Moteur d'évaluation

### Architecture plugin

```
eval_engine/
├── base.py              BaseBenchmarkRunner (ABC)
├── harness_runner.py    lm-eval wrapper (priorité 1)
├── registry.py          Routing benchmark → runner
├── runner.py            Orchestrateur campagne (N×M)
├── litellm_client.py    Client LLM unifié + détection OpenRouter
├── academic/mmlu.py     Runner MMLU (dataset JSON local)
├── safety/refusals.py   Runner frontier INESIA (scoring refus)
└── custom/runner.py     Runner générique JSON
```

### Routing des runners

```
get_runner(benchmark)
    1. Nom match → HARNESS_TASK_MAP ?  → HarnessRunner
    2. Nom match → _NAME_REGISTRY ?    → Runner nommé (Safety, MMLU...)
    3. Type match → _TYPE_REGISTRY ?   → Runner par type
    4. Défaut                          → CustomRunner
```

### Mapping lm-eval (extrait)

| Clé interne | Task lm-eval |
|---|---|
| hellaswag | hellaswag |
| arc_challenge | arc_challenge |
| winogrande | winogrande |
| mmlu | mmlu |
| mmlu_pro | mmlu_pro |
| gsm8k | gsm8k |
| math_subset | math_word_problems |
| humaneval_full | humaneval |
| mbpp | mbpp |
| truthfulqa | truthfulqa_mc1 |
| ifeval | ifeval |
| mmlu_fr | mmlu_fr |
| drop | drop |
| anli | anli_r3 |
| … (30 tasks) | … |

### HarnessRunner

```python
class HarnessRunner(BaseBenchmarkRunner):
    def _run_sync(self, model, max_samples, seed, ...):
        lm = _make_lm_eval_model(model)   # adapte notre modèle → lm-eval LM
        results = evaluator.simple_evaluate(
            model=lm,
            tasks=[self.task_name],
            limit=max_samples,
            random_seed=seed,
        )
        score = task_results.get("acc,none") \
             or task_results.get("acc_norm,none") \
             or task_results.get("exact_match,none") or 0.0
        return RunSummary(score=score, ...)

    async def run(self, ...):
        # Exécuté dans thread pool pour ne pas bloquer asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None, self._run_sync, ...
        )
```

### Runner frontier INESIA (SafetyRefusalsRunner)

Score inversé :
- `1.0` = refus correct (modèle résistant)
- `0.0` = assistance dangereuse fournie

Détection par mots-clés multilingues : `refuse`, `cannot`, `not able`, `ne peux pas`, `inappropriate`…

### Gestion dataset manquant

```python
def load_dataset(self) -> list[dict]:
    if not full_path.exists():
        logger.warning(f"Dataset not found: {full_path}")
        return []   # RunSummary vide, COMPLETED, score=0, num_items=0
```

Plus de `FAILED` sur dataset absent — le run se termine proprement.

### LiteLLM client

Détection OpenRouter automatique par endpoint :

```python
def _is_openrouter(model) -> bool:
    return model.endpoint.rstrip("/") == "https://openrouter.ai/api/v1"

def _build_kwargs(model, ...) -> dict:
    if _is_openrouter(model):
        api_key = settings.openrouter_api_key   # auto depuis env
        kwargs["api_base"] = "https://openrouter.ai/api/v1"
    ...
```

---

## 5. Base de données

### Schéma complet

```sql
CREATE TABLE llmmodel (
    id                INTEGER PRIMARY KEY,
    name              TEXT NOT NULL,
    provider          TEXT NOT NULL,   -- openai|anthropic|ollama|mistral|groq|custom
    model_id          TEXT NOT NULL,   -- "meta-llama/llama-3.3-70b-instruct:free"
    endpoint          TEXT,            -- "https://openrouter.ai/api/v1"
    api_key_encrypted TEXT,            -- Fernet AES-128
    context_length    INTEGER DEFAULT 4096,
    cost_input_per_1k  REAL DEFAULT 0.0,
    cost_output_per_1k REAL DEFAULT 0.0,
    tags              TEXT DEFAULT '[]',
    notes             TEXT,
    is_active         BOOLEAN DEFAULT TRUE,
    created_at        DATETIME
);

CREATE TABLE benchmark (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    type            TEXT NOT NULL,   -- academic|safety|coding|custom
    description     TEXT,
    tags            TEXT DEFAULT '[]',
    dataset_path    TEXT,            -- relatif à BENCH_LIBRARY_PATH
    metric          TEXT DEFAULT 'accuracy',
    num_samples     INTEGER,
    config_json     TEXT DEFAULT '{}',  -- { few_shot, max_tokens }
    risk_threshold  REAL,               -- null = pas de seuil frontier
    is_builtin      BOOLEAN DEFAULT FALSE,
    has_dataset     BOOLEAN DEFAULT FALSE,
    created_at      DATETIME
);

CREATE TABLE campaign (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT,
    model_ids     TEXT NOT NULL,     -- JSON array [1, 2, 3]
    benchmark_ids TEXT NOT NULL,     -- JSON array [1, 2]
    status        TEXT DEFAULT 'pending',  -- pending|running|completed|failed|cancelled
    progress      REAL DEFAULT 0.0,        -- 0-100
    seed          INTEGER DEFAULT 42,
    max_samples   INTEGER DEFAULT 50,
    temperature   REAL DEFAULT 0.0,
    error_message TEXT,
    created_at    DATETIME,
    started_at    DATETIME,
    completed_at  DATETIME
);

CREATE TABLE evalrun (
    id             INTEGER PRIMARY KEY,
    campaign_id    INTEGER REFERENCES campaign(id),
    model_id       INTEGER REFERENCES llmmodel(id),
    benchmark_id   INTEGER REFERENCES benchmark(id),
    status         TEXT DEFAULT 'pending',
    score          REAL,            -- 0.0-1.0, null si dataset absent
    metrics_json   TEXT DEFAULT '{}',
    total_cost_usd REAL DEFAULT 0.0,
    total_latency_ms INTEGER DEFAULT 0,
    num_items      INTEGER DEFAULT 0,
    error_message  TEXT,
    started_at     DATETIME,
    completed_at   DATETIME
);

CREATE TABLE evalresult (
    id           INTEGER PRIMARY KEY,
    run_id       INTEGER REFERENCES evalrun(id),
    item_index   INTEGER,
    prompt       TEXT,
    response     TEXT,
    expected     TEXT,
    score        REAL,
    latency_ms   INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd     REAL,
    metadata_json TEXT DEFAULT '{}'
);
```

### Persistence sur Render

SQLite = volume éphémère (Free tier). Perdu à chaque redéploiement.

Options :
- **Render Disk** ($7/mois) — volume persistant monté à `/data`
- **PostgreSQL** — `DATABASE_URL=postgresql://...` (SQLModel compatible)
- **Export CSV** — dashboard → export avant redéploiement

---

## 6. Frontend — Next.js

### App Router

```
app/
├── layout.tsx              Root : Sidebar + SyncBanner + favicon ☿
├── page.tsx                Overview : compteurs animés, auto-refresh 10s
├── models/page.tsx         Registre + catalogue OpenRouter
├── benchmarks/page.tsx     Bibliothèque + catalogue + onglet ☿ INESIA
├── campaigns/page.tsx      Wizard 4 étapes + liste + Run polling
├── dashboard/page.tsx      Radar + Heatmap + Win-rate + CSV export
├── leaderboard/page.tsx    Vue globale + domain cards
├── leaderboard/[domain]/   Leaderboard thématique + rapport Claude
└── about/page.tsx          Mission + docs + réseau international
```

### Variable d'environnement critique

`NEXT_PUBLIC_API_URL` baked au build (pas runtime) :

```dockerfile
ARG NEXT_PUBLIC_API_URL=https://llm-eval-backend-kqlh.onrender.com/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build
```

Fallback hardcodé dans `lib/api.ts` :

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL
  ?? "https://llm-eval-backend-kqlh.onrender.com/api";
```

### Sync silencieuse

```typescript
// lib/useSync.ts — appelé dans layout.tsx via SyncBanner
useEffect(() => {
  const last = localStorage.getItem("mr_sync_ts");
  if (last && Date.now() - Number(last) < 15 * 60 * 1000) return;
  fetch(`${API_BASE}/sync/startup`, { method: "POST" })
    .then(r => r.json())
    .then(data => localStorage.setItem("mr_sync_ts", String(Date.now())));
}, []);
```

### Wizard campagne (4 étapes)

```
Étape 0 : Nom + description + max_samples + seed + temperature
Étape 1 : Sélection modèles (checkboxes, scroll, multi-select)
Étape 2 : Sélection benchmarks (filtres : all / INESIA / academic / safety / code / français / custom)
Étape 3 : Récap (N modèles × M benchmarks = total runs) + Créer
```

---

## 7. Sécurité

### Chiffrement des clés API

```python
from cryptography.fernet import Fernet

# AES-128-CBC + HMAC-SHA256
def encrypt_api_key(key: str) -> str:
    return Fernet(settings.secret_key.encode()).encrypt(key.encode()).decode()

def decrypt_api_key(encrypted: str) -> str:
    return Fernet(settings.secret_key.encode()).decrypt(encrypted.encode()).decode()
```

Les clés ne circulent jamais en clair dans les réponses API (champ `api_key_encrypted` exclu des schémas de réponse).

### Authentification

**Absente en v0.3**. Roadmap :
- v0.5 : Basic Auth Nginx en frontal
- v0.6 : API keys par organisation
- v1.0 : SSO SGDSN / INAIMES

---

## 8. Déploiement

### Render (production)

**Backend** (`llm-eval-backend-kqlh`) :
- Type : Web Service Docker
- Plan : Free (512MB RAM, 0.1 CPU)
- Port : 8000
- Health : `GET /api/health`
- Auto-deploy : push → main

**Frontend** (`llm-eval-frontend`) :
- Type : Web Service Docker
- Plan : Free
- Port : 3000
- Build arg : `NEXT_PUBLIC_API_URL`

### Variables Render backend

```
SECRET_KEY         = <64 hex chars>
ANTHROPIC_API_KEY  = sk-ant-...
OPENROUTER_API_KEY = sk-or-...
BENCH_LIBRARY_PATH = /bench_library
```

### Variables build frontend (Docker Build Args)

```
NEXT_PUBLIC_API_URL = https://llm-eval-backend-kqlh.onrender.com/api
```

### Limitations Free Tier

| Contrainte | Impact | Solution |
|---|---|---|
| 512MB RAM | lm-eval + datasets peut dépasser | Render Starter ($7/mois = 2GB) |
| Données éphémères | SQLite perdu au redeploy | Render Disk ($7/mois) |
| Cold start 30-60s | Première requête lente | Plan payant |
| Pas de GPU | CPU uniquement | OK pour LLMs cloud via API |

---

## 9. Flux de données

### Campagne (end-to-end)

```
POST /campaigns { name, model_ids, benchmark_ids, seed, max_samples }
    → DB: Campaign(status=pending)

POST /campaigns/{id}/run
    → asyncio.create_task(execute_campaign(id))
    → DB: Campaign(status=running)

Pour chaque (model_id, benchmark_id):
    DB: EvalRun(status=running)
    get_runner(benchmark)
        → HarnessRunner.run() [thread pool]
            → evaluator.simple_evaluate() → HuggingFace → LLM
        → ou MMLURunner.run() → local JSON → LiteLLM
        → ou SafetyRefusalsRunner.run() → local JSON → LiteLLM
    DB: EvalRun(status=completed, score=X)
    DB: N × EvalResult (per-item)
    DB: Campaign(progress=%)

DB: Campaign(status=completed, progress=100)
Frontend poll toutes les 2s → setRunningId(null)
```

### Leaderboard + rapport Claude

```
GET /leaderboard/{domain}
    → SELECT EvalRun WHERE status=completed
    → Agrège par modèle : avg_score, scores par benchmark
    → Retourne DomainLeaderboard

POST /leaderboard/{domain}/report
    → Vérifie _report_cache[domain]
    → Si absent : anthropic.messages.create(
          model="claude-sonnet-4-20250514",
          prompt=f"Analyse {results_json}..."
      )
    → Cache + retourne DomainReport { content_markdown }
```

### Sync démarrage

```
Frontend: check localStorage "mr_sync_ts" > 15min ?
    → POST /sync/startup

Backend:
    1. Benchmarks: BENCHMARK_CATALOG (68) - DB existants → INSERT manquants
    2. Si OPENROUTER_API_KEY:
           GET openrouter.ai/api/v1/models (~300 modèles)
           INSERT modèles absents en DB
       Sinon: INSERT starter pack (8 modèles gratuits)
    → { benchmarks_added: N, models_added: M }

Frontend: SyncBanner si N>0 ou M>0
```

---

## 10. Variables d'environnement

| Variable | Requis | Défaut | Description |
|---|---|---|---|
| `SECRET_KEY` | **Oui** | — | 64 hex chars — clé Fernet |
| `ANTHROPIC_API_KEY` | Rapports | — | Claude Sonnet pour rapports |
| `OPENROUTER_API_KEY` | Recommandé | — | 300+ modèles auto-importés |
| `OPENAI_API_KEY` | Non | — | Modèles OpenAI directs |
| `MISTRAL_API_KEY` | Non | — | Modèles Mistral directs |
| `GROQ_API_KEY` | Non | — | Modèles Groq directs |
| `OLLAMA_BASE_URL` | Non | `http://localhost:11434` | Modèles locaux |
| `BENCH_LIBRARY_PATH` | Non | `/bench_library` | Datasets built-in |
| `DATABASE_URL` | Non | `sqlite:///./data/llm_eval.db` | Postgres compatible |
| `REPORT_MODEL` | Non | `claude-sonnet-4-20250514` | Modèle pour rapports |
| `DEFAULT_MAX_SAMPLES` | Non | `50` | Samples par défaut |
| `NEXT_PUBLIC_API_URL` | **Build** | `https://…kqlh.onrender.com/api` | URL backend (baked) |

---

## 11. API Reference

Base URL : `https://llm-eval-backend-kqlh.onrender.com/api`

```
GET  /health

# Modèles
GET  /models
POST /models
PUT  /models/{id}
DEL  /models/{id}
POST /models/{id}/test           → { ok, latency_ms, response, error }

# Benchmarks
GET  /benchmarks
POST /benchmarks
POST /benchmarks/{id}/dataset    multipart/form-data
DEL  /benchmarks/{id}

# Campagnes
GET  /campaigns
POST /campaigns
POST /campaigns/{id}/run
POST /campaigns/{id}/cancel
GET  /campaigns/{id}/results
DEL  /campaigns/{id}

# Rapports campagne
POST /reports/{campaign_id}      → { content, generated_at }

# Catalogue
GET  /catalog/models             live OpenRouter
  ?free_only=true
  ?open_source_only=true
  ?search=llama
GET  /catalog/benchmarks         static 68 items
  ?frontier_only=true
  ?domain=cybersécurité

# Leaderboard
GET  /leaderboard/domains
GET  /leaderboard/{domain}
POST /leaderboard/{domain}/report
GET  /leaderboard/{domain}/report  (cached)

# Sync
POST /sync/startup
GET  /sync/benchmarks
POST /sync/benchmarks/import-all
```

---

## 12. Décisions d'architecture

### SQLite vs PostgreSQL

SQLite en v0.x pour zéro configuration et zero service additionnel. SQLModel/SQLAlchemy rend la migration triviale (`DATABASE_URL`). PostgreSQL prévu en v1.0 pour multi-tenant.

### asyncio vs Celery/Redis

Asyncio natif : zéro infra supplémentaire, Render Free tier ne supporte pas Redis, LiteLLM est async natif end-to-end. Limite : campagnes séquentielles (1 process). Parallélisme prévu via Render Background Workers en v0.6.

### lm-eval-harness vs runners custom

Harness en priorité : scores comparables aux publications des labs, datasets HuggingFace auto-gérés, 300+ tâches sans maintenance. Runners INESIA pour le frontier (inexistant dans harness par définition).

### OpenRouter comme catalogue modèles

300+ modèles via une clé, API OpenAI-compatible → LiteLLM trivial, modèles gratuits disponibles, détection automatique par endpoint dans `litellm_client.py`.

### NEXT_PUBLIC_API_URL bakée au build

Contrainte Next.js App Router : les variables `NEXT_PUBLIC_*` sont inlinées au `npm run build`. Solution : `ARG` Dockerfile + valeur par défaut hardcodée dans `api.ts`. Pattern documenté et reproductible.

---

*Document maintenu par l'équipe INESIA.*
*Dernière mise à jour : Avril 2026 — v0.3.0*
*Contributions : https://github.com/jonathancollas/llm-eval-platform*
