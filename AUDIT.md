# Mercury Retrograde — Audit Technique Final

**Date :** 7 avril 2026
**Session :** 14 commits, 39 fichiers, +5606 lignes
**Issues GitHub :** 28/28 closes

---

## ISSUES — TOUTES CLOSES ✅

| # | Issue | Status |
|---|-------|--------|
| GENOME-1 | Ontologie Failure Genome v1.0 | ✅ `ontology.py` |
| GENOME-2 | Signal Extractor Pipeline | ✅ `signal_extractor.py` — 25+ signaux |
| GENOME-3 | Failure Classifiers (rules) | ✅ `classifiers.py` — 7 classifieurs |
| GENOME-4 | LLM-as-Judge Hybrid | ✅ `classify_run_hybrid()` — 50/50 blend |
| GENOME-5 | DNA Profile storage + API | ✅ `FailureProfile` + 5 endpoints |
| GENOME-6 | Visualisation radar + timeline | ✅ `genome/page.tsx` |
| CATALOG-1 | Contamination Detection | ✅ `contamination.py` — 4 méthodes |
| CATALOG-2 | HuggingFace Dataset Import | ✅ `POST /benchmarks/import-huggingface` |
| REDBOX-1 | Architecture REDBOX UI | ✅ `redbox/page.tsx` |
| REDBOX-2 | Attack Mutation Engine | ✅ 6 mutation types + templates |
| REDBOX-3 | LLM-generated adversarial | ✅ Claude forge + rule fallback |
| REDBOX-4 | Severity scoring + Tracker | ✅ CVSS-like + GET /exploits |
| REDBOX-5 | Breach Replay | ✅ POST /replay/{id} |
| REDBOX-6 | Cross-Model Transfer | ✅ replay sur autre modèle |
| ANALYZER-1 | Behavioral Fingerprinting | ✅ `ModelFingerprint` |
| ANALYZER-2 | Safety Heatmaps | ✅ `/genome/safety-heatmap` |
| REGRESSION-1 | Run context store | ✅ `run_context_json` on Campaign |
| REGRESSION-2 | Diff engine + Causal scoring | ✅ `/regression/compare` |
| REGRESSION-3 | LLM causal narrative | ✅ `POST /regression/explain` |
| AGENT-1 | Trajectory data model | ✅ `AgentTrajectory` + steps_json |
| AGENT-2 | Agent eval engine (6 axes) | ✅ Hybrid LLM+rules scoring |
| JUDGE-1 | Multi-judge ensemble | ✅ Cohen's κ + Pearson r |
| JUDGE-2 | Bias detection | ✅ Length bias + model preference |
| PROD-1 | Policy Simulation Layer | ✅ EU AI Act, HIPAA, Finance |
| PROD-2 | Real-World Drift Replay | ✅ via REDBOX replay + regression |
| INFRA-1 | PostgreSQL | ✅ Dual mode SQLite/PostgreSQL |
| INFRA-2 | Redis job queue | ✅ Auto-fallback in-memory |
| INFRA-3 | Multi-tenant + auth | ✅ Tenant, User, API key auth |

---

## ARCHITECTURE FINALE

```
Mercury Retrograde v0.5
├── Core Eval Engine
│   ├── 74 API endpoints
│   ├── 13 frontend pages
│   └── 45 Python backend files
│
├── Failure Genome
│   ├── Signal Extractor (25+ signals)
│   ├── 7 Rule-based Classifiers
│   ├── LLM Hybrid Classification
│   ├── DNA Profile Storage
│   └── Radar + Bar Visualization
│
├── REDBOX Security Lab
│   ├── Adversarial Forge (LLM + rules)
│   ├── 6 Mutation Types
│   ├── Exploit Tracker + Severity
│   ├── Attack Surface Heatmap
│   ├── Breach Replay
│   └── Genome → REDBOX Smart Targeting
│
├── LLM-as-Judge
│   ├── Multi-Judge Ensemble
│   ├── Inter-Judge Agreement (κ, r)
│   ├── Oracle Calibration (CJE)
│   └── Bias Detection
│
├── Agent Evaluation
│   ├── Trajectory Data Model
│   ├── 6-Axis Scoring (hybrid)
│   ├── Step Timeline
│   └── Agent → Genome Bridge
│
├── Compliance
│   ├── EU AI Act (6 checks)
│   ├── HIPAA (5 checks)
│   └── Finance (5 checks)
│
├── Infrastructure
│   ├── SQLite / PostgreSQL dual mode
│   ├── Redis / in-memory job queue
│   ├── Multi-tenant (Tenant, User, API key)
│   ├── Ollama local models
│   ├── HuggingFace dataset import
│   └── Contamination detection
│
└── Cross-Module Intelligence
    ├── Auto-judge post-campaign
    ├── Genome → REDBOX smart forge
    ├── Agent → Genome bridge
    ├── Unified Campaign Insights
    └── Cross-module signal alerts
```

---

## SÉCURITÉ — 4 VULNÉRABILITÉS CORRIGÉES

| Fix | Description |
|-----|-------------|
| S1 | Token GitHub hardcodé → env var |
| S2 | Input validation sur tous les endpoints |
| S3 | Rate limiting 120 req/min/IP |
| S4 | Masquage API keys dans les logs |

---

## PERFORMANCE — 4 OPTIMISATIONS

| Fix | Description |
|-----|-------------|
| P1 | Cache catalog thread-safe |
| P2 | Batch insert → streaming items |
| P3 | Index DB sur EvalResult.score |
| P4 | Fix report_max_tokens (crash 500) |

---

## MÉTRIQUES FINALES

| Dimension | Valeur |
|-----------|--------|
| API endpoints | 74 |
| Frontend pages | 13 |
| Backend Python files | 45 |
| Total lignes ajoutées | +5606 |
| Fichiers modifiés | 39 |
| Nouveaux fichiers | 12 |
| Issues GitHub closes | 28/28 |
| Modules principaux | 7 (Eval, Genome, REDBOX, Judge, Agents, Compliance, Infra) |
| Providers supportés | 7 (OpenAI, Anthropic, Mistral, Groq, OpenRouter, Ollama, Custom) |
| Regulatory frameworks | 3 (EU AI Act, HIPAA, Finance) |

---

*Mercury Retrograde — INESIA AI Evaluation Platform*
*The only platform combining eval + red team + genome + judge calibration + agent eval + compliance in one system.*
