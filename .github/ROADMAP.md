# Mercury Retrograde — Roadmap

> Feuille de route complète pour devenir la plateforme d'évaluation de LLM la plus avancée au monde.
> Chaque section correspond à un milestone GitHub. Les issues détaillées sont dans le tracker.

---

## ☿ Milestone v0.3 — Core Infrastructure ✅ Déployé

Plateforme fonctionnelle : campagnes, benchmarks lm-eval, leaderboard, rapports Claude.

---

## 🧬 Milestone v0.4 — Failure Genome

**Objectif : passer du score agrégé au diagnostic structurel d'échec.**

Un score dit *qui gagne*. Le Failure Genome dit *pourquoi le modèle échoue*.

- [ ] **[GENOME-1]** Définir l'ontologie Failure Genome v1.0 (taxonomie YAML versionnée)
  - Catégories : hallucination, instruction_failure, reasoning_failure, safety_failure, tool_failure, system_failure, calibration_failure
  - Chaque failure : id stable, description, signals, severity weight, benchmark mapping

- [ ] **[GENOME-2]** Signal extractor pipeline
  - Extraire depuis chaque run : latency, response_length, refusal_detected, contradictions, truth_score, tool_errors

- [ ] **[GENOME-3]** Failure classifiers (rules-based layer)
  - HallucinationClassifier, ReasoningCollapseClassifier, InstructionDriftClassifier, SafetyBypassClassifier
  - Chaque classifier retourne `{failure_type, probability, severity}`

- [ ] **[GENOME-4]** LLM-as-judge layer (hybride)
  - Prompt Claude pour classer les failures nuancées (drift, bypass, incohérence)
  - Retourne JSON de probabilités par failure type

- [ ] **[GENOME-5]** DNA Profile storage + API
  - Stocker `failure_genome JSONB` par run et agrégat par campagne
  - `GET /api/runs/{id}/genome`, `GET /api/campaigns/{id}/genome`

- [ ] **[GENOME-6]** Visualisation radar + heatmap
  - Radar chart par modèle (hallucination / reasoning / safety / drift)
  - Timeline de régression genome entre versions

---

## 📐 Milestone v0.4 — Badges & Catalog Enrichissement

- [ ] **[CATALOG-1]** Badges capacités modèles (Vision / Tools / Reasoning) dans l'UI ✅ Backend prêt
- [ ] **[CATALOG-2]** LiveBench integration — onglet "High-signal / Anti-contamination"
- [ ] **[CATALOG-3]** Benchmarks FR certifiés INESIA (FQuAD natif, PIAF, PAWS-FR)
- [ ] **[CATALOG-4]** Persistence datasets en DB (SQLite blob → load une fois, rejouer N fois)
- [ ] **[CATALOG-5]** Bouton "Charger depuis HuggingFace" par benchmark (hydrate DB)

---

## 🔴 Milestone v0.5 — REDBOX Security Lab

**Objectif : laboratoire offensif intégré pour red teaming automatisé.**

> *Break the model before reality does.*

- [ ] **[REDBOX-1]** Architecture module REDBOX (séparé de Core Eval dans l'UI)
  - Sidebar : onglet REDBOX avec Jailbreak Lab, Forge, Policy Breach Analyzer

- [ ] **[REDBOX-2]** Attack Mutation Engine
  - Mutateurs : prompt_injection, ambiguity, multilingual, contradiction, malformed_context, tool_misuse
  - Interface `ScenarioMutator` + pipeline seed → variants
  - Stockage avec `parent_id` pour traçabilité de lignée

- [ ] **[REDBOX-3]** LLM-generated adversarial synthesis
  - Générer 20+ variantes adversariales depuis un seed via Claude
  - Scorer la difficulté de chaque variant

- [ ] **[REDBOX-4]** Severity scoring + Exploit tracking
  - Niveaux : Critical / High / Medium / Low
  - Basé sur : reproducibility, policy bypass depth, tool impact, autonomy risk

- [ ] **[REDBOX-5]** Exploit Dependency Graph
  - Visualiser les chemins d'attaque : `policy → ambiguity → roleplay → bypass`
  - Identifier quels vecteurs sont combinés pour réussir un exploit

- [ ] **[REDBOX-6]** Breach Replay
  - Rejouer automatiquement les exploits connus sur nouvelles versions de modèle
  - "Does v4.3 still fail the same exploit?"

- [ ] **[REDBOX-7]** Cross-Model Adversarial Transfer
  - Tester si un exploit trouvé sur GPT-4o peut être transféré à Claude/Gemini

- [ ] **[REDBOX-8]** WMDP score inversion + alertes automatiques ✅ Partiel
  - Alertes si score CBRN dépasse le seuil de risque

---

## 📊 Milestone v0.5 — Analyzers (Behavioral Intelligence)

- [ ] **[ANALYZER-1]** Behavioral Fingerprinting
  - Profilage multi-dimensionnel : prudence, hallucination, assertivité, créativité, refus, latence
  - Compare les "personnalités opérationnelles" des modèles

- [ ] **[ANALYZER-2]** Cross-Model Behavioral Diff Engine
  - Pas juste les scores : comparer le *style comportemental*
  - "Claude est plus prudeant et refus-heavy ; GPT plus assertif et hallucination-prone sous ambiguïté"

- [ ] **[ANALYZER-3]** Consistency Trajectory
  - Cohérence des réponses avec variations mineures de prompt (±10%)
  - Détecte fragilités invisibles aux benchmarks classiques

- [ ] **[ANALYZER-4]** Safety Heatmaps by Capability
  - Matrice capability × risk (coding, legal, medical, autonomous tool use…)
  - Risk decomposition : hallucination / unsafe advice / tool misuse / policy bypass
  - Alertes gouvernance si seuil dépassé (Green / Yellow / Red)

---

## ⚙️ Milestone v0.6 — Regression Causality Engine

**Objectif : expliquer POURQUOI le score a changé, pas seulement le détecter.**

> "87% probability regression caused by retrieval chunk-size update"

- [ ] **[REGRESSION-1]** Run context store
  - Stocker toutes les variables causales par campagne : system_prompt_hash, provider, temperature, dataset_version, judge_model, retrieval_config

- [ ] **[REGRESSION-2]** Diff engine
  - `diff_campaigns(baseline, candidate)` → liste des variables changées avec before/after

- [ ] **[REGRESSION-3]** Causal scoring (MVP)
  - Poids causaux par type de changement : prompt=0.9, provider=0.7, chunk_size=0.85, temperature=0.6
  - Classement des causes probables avec probabilité

- [ ] **[REGRESSION-4]** Statistical attribution (version avancée)
  - `P(Cause | Regression)` basé sur l'historique des campagnes
  - Retourner `{cause, probability, confidence}`

- [ ] **[REGRESSION-5]** LLM-generated causal explanation
  - Narrative lisible : "The regression is most likely caused by..."
  - Alimenter le dashboard avec explication executive-friendly

- [ ] **[REGRESSION-6]** Causal Graph (DAG)
  - `provider switch → latency → truncation → reasoning regression`
  - Root cause analysis visuelle

---

## 🤖 Milestone v0.6 — Autonomous Agent Evaluation

**Objectif : évaluer des systèmes AI complets, pas seulement des single-turn LLMs.**

- [ ] **[AGENT-1]** Trajectory data model
  - Schema canonique : goal, steps[], memory, tool_calls, final_result
  - API `POST /api/campaigns/{id}/agent-run`

- [ ] **[AGENT-2]** Agent evaluation engine (6 axes)
  - Goal completion score, Tool chain quality, Memory consistency, Loop detection, Unsafe autonomy, Planning quality

- [ ] **[AGENT-3]** Composite agent score
  - `0.30 * goal + 0.20 * tool_chain + 0.15 * memory + 0.15 * planning + 0.10 * (1-loop) + 0.10 * (1-unsafe)`

- [ ] **[AGENT-4]** Loop detection algorithm
  - Détecter répétitions d'états ou de tool chains sans progression

- [ ] **[AGENT-5]** Unsafe autonomy detector
  - Flaguer : exécution non confirmée, email envoyé sans validation, suppression non demandée

- [ ] **[AGENT-6]** Agent Failure Genome integration
  - Nouveaux failure types : loop_collapse, memory_drift, tool_chain_break, unsafe_autonomy, goal_abandonment

- [ ] **[AGENT-7]** Timeline visualization
  - Rejouer step-by-step la trace de l'agent avec annotations failure

---

## 🔬 Milestone v0.7 — Judge Reliability Layer

**Objectif : scorer les évaluateurs, pas seulement les modèles.**

> "Score: 82, with judge reliability 0.81 and human agreement 89%"

- [ ] **[JUDGE-1]** Multi-judge ensemble
  - Faire juger le même output par 3 juges différents (GPT-4o, Claude, Mistral)
  - Mesurer inter-judge agreement (Cohen's kappa)

- [ ] **[JUDGE-2]** Human calibration pipeline
  - Stocker annotations humaines, calculer human agreement %
  - Schema `judge_validation` avec `human_score` vs `judge_score`

- [ ] **[JUDGE-3]** Confidence calibration (ECE)
  - Expected Calibration Error : le juge doit savoir quand il est incertain

- [ ] **[JUDGE-4]** Bias detection
  - Length bias : réponses longues scorées plus haut
  - Provider bias : favoritisme selon le modèle évalué
  - Language bias : performances selon la langue

- [ ] **[JUDGE-5]** Judge drift monitoring
  - Tracer la fiabilité du juge dans le temps (mises à jour provider)
  - Détecter "judge regressions"

- [ ] **[JUDGE-6]** Trust envelope sur chaque score
  - Afficher `{score: 0.82, judge_reliability: 0.81, confidence_interval: [0.77, 0.86]}`

---

## 🌐 Milestone v0.7 — Production & Real-World Integration

- [ ] **[PROD-1]** Real-World Drift Replay
  - Import anonymisé de logs production, replay sur nouvelles versions
  - "v4 fixes 71% of failures from last 30 days"

- [ ] **[PROD-2]** Policy Simulation Layer
  - Tester sous contraintes réglementaires : EU AI Act, HIPAA, Finance compliance
  - Score de conformité simulé par scénario

- [ ] **[PROD-3]** Audit Trails
  - Tout test enregistré avec versions, paramètres, hash datasets
  - Export pour régulateurs / compliance

- [ ] **[PROD-4]** Governance reporting
  - Rapport PDF par modèle : safety heatmap + failure genome + judge reliability
  - "Can we deploy this model for medical copilots?"

---

## 🏗️ Milestone v1.0 — Infrastructure & Scalabilité

- [ ] **[INFRA-1]** Migration PostgreSQL (remplace SQLite)
- [ ] **[INFRA-2]** Redis + job queue persistante (remplace asyncio in-memory)
- [ ] **[INFRA-3]** Multi-tenant / multi-organisation
- [ ] **[INFRA-4]** SSO SGDSN / INAIMES
- [ ] **[INFRA-5]** API publique soumission benchmarks
- [ ] **[INFRA-6]** Interopérabilité réseau INAIMES

---

## 🎯 Positionnement vs concurrents

| Feature | LangSmith | Arize | Promptfoo | **Mercury Retrograde** |
|---|---|---|---|---|
| Failure Genome | ❌ | ❌ | ❌ | ✅ v0.4 |
| Regression Causality | ❌ | Partiel | ❌ | ✅ v0.6 |
| Adversarial Forge (REDBOX) | ❌ | ❌ | Partiel | ✅ v0.5 |
| Judge Reliability | ❌ | ❌ | ❌ | ✅ v0.7 |
| Agent Evaluation | Partiel | ❌ | ❌ | ✅ v0.6 |
| Frontier CBRN-E benchmarks | ❌ | ❌ | ❌ | ✅ v0.3 |
| Rapports narratifs IA | ❌ | ❌ | ❌ | ✅ v0.3 |

**Mercury Retrograde est la seule plateforme qui combine :**
évaluation standardisée + diagnostic comportemental + stress-test offensif + causalité de régression + benchmarks frontier institutionnels.

---

*Maintenu par l'équipe INESIA — Mercury Retrograde v0.3+*
