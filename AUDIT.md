# Mercury Retrograde — Audit Technique & Roadmap

**Date :** 7 avril 2026
**Scope :** Backend (FastAPI/Python) + Frontend (Next.js 15/React) + Infra
**Commit de base :** `7e5a171` (post Sprint 3)

---

## 1. STATUS DES ISSUES GITHUB

### ✅ CLOSES (implémentées — à clôturer)

| Issue | Titre | Preuve |
|-------|-------|--------|
| GENOME-1 | Ontologie Failure Genome v1.0 | `ontology.py` — 7 failure types versionnés |
| GENOME-3 | Failure classifiers (rules-based) | `classifiers.py` — HallucinationClassifier, ReasoningCollapse, SafetyBypass, OverRefusal, Truncation, CalibrationFailure, InstructionDrift |
| GENOME-5 | DNA Profile storage + API | `FailureProfile` model + 5 endpoints genome router |
| GENOME-6 | Visualisation radar + timeline | `genome/page.tsx` — RadarViz SVG + DNA bars + 3 onglets |
| ANALYZER-1 | Behavioral Fingerprinting | `ModelFingerprint` model + `/genome/models` endpoint + Fingerprints tab |
| ANALYZER-2 | Safety Heatmaps by Capability | `/genome/safety-heatmap` endpoint + heatmap tab avec risk matrix |
| REGRESSION-1 | Run context store | Campaign model : `system_prompt_hash`, `dataset_version`, `judge_model`, `run_context_json` |
| REGRESSION-2 | Diff engine + Causal scoring | `/genome/regression/compare` endpoint avec CAUSAL_WEIGHTS |
| REDBOX-1 | Architecture module REDBOX | `redbox/page.tsx` — UI Forge + Mutation types définis |

### ⏳ OUVERTES (non implémentées)

| Issue | Titre | Priorité | Effort |
|-------|-------|----------|--------|
| GENOME-2 | Signal extractor pipeline | Haute | 2j |
| GENOME-4 | LLM-as-judge classification hybride | Haute | 3j |
| CATALOG-1 | LiveBench integration anti-contamination | Moyenne | 3j |
| CATALOG-2 | Persistence datasets HuggingFace | Moyenne | 2j |
| REDBOX-2 | Attack Mutation Engine (backend) | Haute | 3j |
| REDBOX-3 | LLM-generated adversarial synthesis | Haute | 2j |
| REDBOX-4 | Severity scoring + Exploit Tracker | Moyenne | 2j |
| REDBOX-5 | Breach Replay | Moyenne | 2j |
| REDBOX-6 | Cross-Model Adversarial Transfer | Basse | 3j |
| REGRESSION-3 | LLM-generated causal narrative | Basse | 1j |
| AGENT-1 | Trajectory data model | Haute | 3j |
| AGENT-2 | Agent evaluation engine (6 axes) | Haute | 5j |
| JUDGE-1 | Multi-judge ensemble + agreement | Haute | 4j |
| JUDGE-2 | Bias detection juges LLM | Moyenne | 3j |
| PROD-1 | Policy Simulation Layer | Basse | 3j |
| PROD-2 | Real-World Drift Replay | Basse | 3j |
| INFRA-1 | Migration PostgreSQL | Haute (scale) | 3j |
| INFRA-2 | Redis job queue | Haute (scale) | 2j |
| INFRA-3 | Multi-tenant + auth | Haute (scale) | 5j |

---

## 2. AUDIT SÉCURITÉ

### 🔴 CRITIQUES (corrigés dans ce commit)

| # | Problème | Impact | Fix |
|---|----------|--------|-----|
| S1 | **Token GitHub hardcodé** dans `create_github_issues.py` (ligne 10) | Fuite credential dans repo public | Remplacé par `os.environ["GITHUB_TOKEN"]` |
| S2 | **Aucune validation d'entrée** sur `CampaignCreate` | max_samples=-1, temperature=999 acceptés | Ajout `Field(ge=, le=, max_length=)` avec bornes |
| S3 | **Pas de rate limiting** | DDoS / abuse possible sur tous endpoints | Ajout middleware rate limiter 120 req/min par IP |
| S4 | **API keys dans les logs** | Fuite potentielle dans stdout/stderr | Ajout `_sanitize_error()` dans litellm_client |

### 🟡 MODÉRÉS (à traiter)

| # | Problème | Impact | Recommandation |
|---|----------|--------|----------------|
| S5 | `ADMIN_API_KEY` optionnel (vide = pas d'auth) | API ouverte en production si pas configuré | Forcer en production (comme SECRET_KEY) |
| S6 | Pas de CSRF token | Faible (CORS protège les navigateurs) | Ajouter si frontend sert des formulaires |
| S7 | SQLite sans WAL mode | Risque de DB lock sous charge | Activer `PRAGMA journal_mode=WAL` |
| S8 | Fernet key dérivée de SHA-256 de secret_key | Acceptable mais HKDF serait mieux | Passer à `cryptography.hazmat.primitives.kdf.hkdf` |
| S9 | Pas de sanitization des prompts stockés | XSS possible si affiché raw dans le frontend | Échapper les prompts côté frontend (React le fait par défaut via JSX) |

### 🟢 BONNES PRATIQUES DÉJÀ EN PLACE

- Chiffrement AES-128-CBC + HMAC (Fernet) pour les API keys stockées
- Headers de sécurité HTTP (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection)
- CORS configuré avec whitelist explicite
- Secret key obligatoire en production (validation Pydantic)
- API keys jamais exposées dans les réponses API

---

## 3. AUDIT PERFORMANCE

### 🔴 CORRIGÉS DANS CE COMMIT

| # | Problème | Impact | Fix |
|---|----------|--------|-----|
| P1 | **Cache catalog non thread-safe** | Race condition sous multi-workers | `threading.Lock` ajouté |
| P2 | **Insertion EvalResults en boucle** | Lent sur gros benchmarks (N requêtes DB) | `session.add_all()` batch |
| P3 | **Pas d'index sur EvalResult.score** | Requête failed-items lente | `Field(index=True)` ajouté |
| P4 | **`report_max_tokens` manquant** (bug) | Crash 500 → `Failed to fetch` | Ajouté dans config avec valeur 4096 |

### 🟡 À TRAITER (prochains sprints)

| # | Problème | Impact estimé | Recommandation |
|---|----------|---------------|----------------|
| P5 | Frontend monolithique `campaigns/page.tsx` (585 lignes) | Rerender excessifs | Découper en sous-composants + React.memo |
| P6 | Pas de SWR/React Query | Refetch réseau à chaque navigation | Migrer vers SWR pour cache client |
| P7 | Recharts re-calculé à chaque render | CPU gaspillé | `useMemo` sur toutes les data préparées |
| P8 | `"use client"` sur pages lecture seule | Bundle JS trop gros, TTI élevé | Migrer benchmarks, leaderboard en Server Components |
| P9 | Genome computation synchrone post-run | Bloque la completion du run | Déporter en background task |
| P10 | Pas de pagination sur `/models/`, `/benchmarks/` | Problème si >1000 modèles | Ajouter `limit`/`offset` |
| P11 | SQLite single-writer bottleneck | Limite à ~50 req/s d'écriture | Migration PostgreSQL (INFRA-1) |

---

## 4. FEATURES AVANCÉES — ROADMAP POUR DEVENIR LEADER

### Tier 1 — Différenciateurs immédiats (v0.5)

#### 🧪 LLM-as-Judge avec Calibration (JUDGE-1 + JUDGE-2)

**Pourquoi :** Tous les outils d'eval utilisent des juges LLM (G-Eval, etc.) mais personne ne calibre le juge. Première plateforme à implémenter le Causal Judge Evaluation (CJE).

**Implémentation :**
- Multi-judge ensemble : 3 juges LLM (Claude, GPT-4, Gemini) votent sur chaque item
- Inter-judge agreement : Fleiss' kappa, Cohen's kappa pairwise
- Calibration oracle : petit subset labellisé humain → correction du biais du juge
- Surrogacy metrics : le juge prédit-il le même ranking que les humains ?
- Dashboard : carte thermique agreement + scatter plot calibration

**Avantage compétitif :** Ni DeepEval, ni OpenCompass, ni EleutherAI n'ont ça.

---

#### 🤖 Agent Evaluation Engine (AGENT-1 + AGENT-2)

**Pourquoi :** Les agents LLM (tool-use, multi-step) sont le futur, mais il n'existe aucune plateforme d'évaluation qui les traite nativement comme des pipelines.

**Implémentation :**
- Data model `AgentTrajectory` : séquence de (thought, action, observation, result)
- 6 axes de scoring : task completion, tool precision, planning coherence, error recovery, safety compliance, cost efficiency
- Support des traces LangChain/LangGraph via callback handler
- Replay trajectoire dans le dashboard
- Benchmark agents : WebArena-like tasks

**Avantage compétitif :** Seul Braintrust a un début d'agent eval, mais pas de scoring multi-axe.

---

#### 🔴 REDBOX Engine complet (REDBOX-2 → REDBOX-6)

**Pourquoi :** Le red teaming automatisé est le sujet #1 en AI safety. Personne n'a de plateforme intégrée eval + red team.

**Implémentation :**
- Attack Mutation Engine : 6 types de mutations (injection, ambiguïté, multilingue, contradiction, jailbreak, contexte bruité)
- LLM-generated adversarial synthesis : Claude génère des attaques calibrées selon le genome du modèle cible
- Severity scoring CVSS-like pour chaque exploit
- Breach Replay : rejouer les exploits réussis sur les nouvelles versions
- Cross-model transfer : tester si un exploit sur Gemma marche sur Llama

**Avantage compétitif :** Unique combo "eval + red team + genome" dans un seul outil.

---

### Tier 2 — Avance technique (v0.6)

#### 📊 Contamination Detection

Détecter si un modèle a vu les données de test pendant l'entraînement :
- N-gram overlap analysis entre les réponses et le dataset
- Permutation testing : mélanger les réponses et vérifier si le score chute
- LiveBench integration (benchmarks avec données post-cutoff)
- Dashboard contamination score par benchmark

#### 🔄 A/B Testing continu

Comparer 2 modèles en production avec significance statistique :
- Sequential testing (pas besoin de sample size fixe)
- Bayesian A/B avec posterior updates en temps réel
- Alertes automatiques quand significance atteinte
- Support multi-metric (score + latency + cost)

#### 🔌 MCP Server

Exposer les résultats d'eval via Model Context Protocol :
- `get_model_scores(model, benchmark)` — scores d'un modèle
- `compare_models(model_a, model_b)` — comparaison head-to-head
- `get_safety_alerts(model)` — alertes safety actives
- Intégration CI/CD : bloquer un déploiement si score < seuil

---

### Tier 3 — Vision long terme (v1.0)

#### 📝 Eval-as-Code (DSL)

```yaml
# eval.mercury.yaml
pipeline:
  name: "GPT-4o safety audit Q2 2026"
  models: [gpt-4o, claude-sonnet-4, gemini-2.0-flash]
  benchmarks:
    - mmlu: { samples: 200, few_shot: 5 }
    - safety_refusals: { threshold: 0.8 }
    - custom: { path: ./my_dataset.json, metric: f1 }
  judges:
    - claude-sonnet-4: { calibration: true, oracle: ./human_labels.json }
  red_team:
    mutations: [injection, jailbreak, multilingual]
    intensity: 3
  alerts:
    - if: safety_score < 0.75 then: block_deploy
    - if: regression > 5% then: notify_slack
```

#### 🏢 Enterprise Features

- Multi-tenant avec SSO (SAML/OIDC)
- Audit trail complet (qui a lancé quoi, quand)
- Role-based access control (viewer, runner, admin)
- Data retention policies
- SOC2 compliance logging

#### 🧠 INAIMES Integration

- Connecteur vers le framework INAIMES d'INESIA
- Mapping automatique ontologie Failure Genome → taxonomie INAIMES
- Export rapport conformité réglementaire (EU AI Act, NIST AI RMF)

---

## 5. MÉTRIQUES DE QUALITÉ POST-AUDIT

| Dimension | Avant audit | Après audit |
|-----------|-------------|-------------|
| Vulnérabilités critiques | 4 (S1-S4) | 0 |
| Rate limiting | Aucun | 120 req/min/IP |
| Input validation | Aucune | Bornes sur tous les champs |
| Cache thread-safety | Non | Oui |
| DB batch performance | Loop N inserts | `add_all()` batch |
| Report generation | Sync + crash | Async + retry + timeout 120s |
| Live tracking | Aucun | Item-level en temps réel |
| Dashboard | 3 widgets statiques | 4 onglets (overview, genome, erreurs, rapport) |
| Error classification | Aucune | 5 types (wrong_answer, timeout, rate_limit, credits, api_error) |
| Export formats | CSV + MD | CSV + MD + HTML |

---

*Document généré automatiquement par Claude — commit `audit-security-perf-roadmap`*
