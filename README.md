<div align="center">

<svg width="120" height="120" viewBox="0 0 72 72" xmlns="http://www.w3.org/2000/svg">
  <defs><clipPath id="rc"><circle cx="36" cy="36" r="20"/></clipPath></defs>
  <ellipse cx="36" cy="36" rx="34" ry="8" fill="none" stroke="#ff00ff" stroke-width="1.0" opacity="0.5" transform="rotate(-12 36 36)"/>
  <ellipse cx="36" cy="36" rx="26" ry="6" fill="none" stroke="#cc44ff" stroke-width="1.4" opacity="0.65" transform="rotate(-12 36 36)"/>
  <circle cx="36" cy="36" r="20" fill="#1a0033"/>
  <circle cx="36" cy="36" r="20" fill="#3a0066" clip-path="url(#rc)"/>
  <ellipse cx="36" cy="30" rx="19" ry="5" fill="#cc00ff" opacity="0.2" clip-path="url(#rc)"/>
  <ellipse cx="36" cy="40" rx="19" ry="4" fill="#ff0088" opacity="0.18" clip-path="url(#rc)"/>
  <path d="M36 16 Q52 24 52 36 Q52 48 36 56 Q44 48 43 36 Q41 24 36 16Z" fill="#000022" opacity="0.5" clip-path="url(#rc)"/>
  <ellipse cx="28" cy="28" rx="9" ry="5" fill="#ff44ff" opacity="0.22" clip-path="url(#rc)"/>
  <circle cx="36" cy="36" r="20" fill="none" stroke="#ff00ff" stroke-width="1.5" opacity="0.7"/>
  <path d="M10 22 Q22 12 36 14 Q50 12 62 22" fill="none" stroke="#00ffff" stroke-width="1.6" stroke-linecap="round"/>
  <path d="M58 18 L62 22 L58 26" fill="none" stroke="#00ffff" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M14 18 L10 22 L14 26" fill="none" stroke="#00ffff" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
</svg>

# ↺ MERCURY RETROGRADE

**INESIA · AI Evaluation Platform**

*Infrastructure technique ouverte d'évaluation des modèles et systèmes d'IA avancés*

[![License: Etalab 2.0](https://img.shields.io/badge/License-Etalab%202.0-blue.svg)](https://www.etalab.gouv.fr/licence-ouverte-open-licence)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![INESIA](https://img.shields.io/badge/INESIA-SGDSN%20%2F%20DGE-purple.svg)](https://www.sgdsn.gouv.fr/nos-missions/anticiper-et-prevenir/evaluer-et-securiser-lia)

**Démo live** : https://llm-eval-frontend.onrender.com

</div>

---

## Vue d'ensemble

Mercury Retrograde permet d'évaluer et de comparer des modèles de langage (LLM) sur un spectre complet de benchmarks — des standards académiques internationaux aux évaluations frontier spécifiques aux risques systémiques identifiés par l'INESIA.

La plateforme est conçue pour être :
- **Légère** — tourne sur un desktop ou un serveur modeste, sans GPU requis
- **Souveraine** — self-hosted, aucune donnée ne quitte votre infrastructure
- **Extensible** — architecture plugin, benchmarks importables en JSON
- **Interopérable** — compatible avec lm-evaluation-harness et le réseau INAIMES

---

## Fonctionnalités

### Modèles
- Registre de modèles locaux (Ollama) et cloud (OpenAI, Anthropic, Mistral, Groq)
- **Catalogue OpenRouter** : 300+ modèles importés automatiquement au démarrage
- Test de connexion live avec mesure de latence
- Chiffrement des clés API stockées (Fernet / AES-128)

### Benchmarks
- **68 benchmarks built-in** importés automatiquement au démarrage
- Catalogue organisé par domaine : raisonnement, maths, code, français, frontier…
- Import de benchmarks custom au format JSON

### Campagnes d'évaluation
- N modèles × M benchmarks en une seule campagne
- Exécution asynchrone (asyncio natif, sans Redis ni Celery)
- Reproductibilité : seed fixé, version modèle tracée, hash prompts archivés
- Suivi de progression en temps réel

### Leaderboard
- Vue globale tous modèles / tous benchmarks
- Pages thématiques : Frontier, Cyber, CBRN-E, Agentique, Académique, Français, Code
- **Rapport Claude** par domaine : analyse narrative générée à la demande

### Dashboards
- Radar chart multi-modèles / multi-benchmarks
- Heatmap colorée (score par cellule modèle × benchmark)
- Win-rate table (comparaison pairwise)
- Alertes automatiques sur seuils de risque

### Rapport IA
- Génération narrative via Claude (Anthropic)
- Analyse par domaine : résumé exécutif, patterns, recommandations
- Export Markdown

---

## Catalogue de benchmarks

### Académiques et performance

| Benchmark | Domaine | Métrique | Items |
|---|---|---|---|
| MMLU | Connaissances multi-domaines | accuracy | 50 |
| MMLU-Pro | Connaissances (difficile, 10 choix) | accuracy | 50 |
| GPQA Diamond | Connaissances expert PhD | accuracy | 30 |
| HellaSwag | Raisonnement / sens commun | accuracy | 50 |
| ARC-Challenge | Sciences / raisonnement | accuracy | 50 |
| WinoGrande | Pronoms / sens commun | accuracy | 50 |
| BIG-Bench Hard | Raisonnement difficile | accuracy | 30 |
| GSM8K | Maths (problèmes verbaux) | accuracy | 50 |
| MATH | Maths compétition | accuracy | 30 |
| AIME | Olympiades mathématiques | accuracy | 20 |
| TruthfulQA | Factualité / hallucinations | accuracy | 50 |
| NaturalQuestions | QA factuel | accuracy | 50 |
| HumanEval+ | Code Python (robuste) | pass@1 | 50 |
| MBPP+ | Code Python (robuste) | pass@1 | 50 |
| SWE-bench | Ingénierie logicielle réelle | resolved_% | 20 |
| IFEval | Instruction following | accuracy | 50 |
| MedQA (USMLE) | Médecine | accuracy | 30 |
| LegalBench | Droit | accuracy | 30 |

### Français

| Benchmark | Domaine | Métrique | Items |
|---|---|---|---|
| MMLU-FR | Connaissances en français | accuracy | 50 |
| FrenchBench — Raisonnement | Raisonnement natif FR | accuracy | 40 |
| FrenchBench — Droit FR | Droit français | accuracy | 30 |
| FrenchBench — Institutions FR | Institutions françaises et européennes | accuracy | 30 |
| FQuAD | QA extractif en français | f1 | 50 |
| PIAF | Pour une IA Francophone | f1 | 50 |
| MGSM | Maths multilingue (FR inclus) | accuracy | 50 |

### Frontier INESIA (risques systémiques)

| Benchmark | Domaine | Seuil d'alerte | Items |
|---|---|---|---|
| Cyber Uplift | Cybersécurité offensive | 85% | 15 |
| CBRN-E Uplift Probe | CBRN-E | **95%** | 15 |
| Loss of Control | Agentique / désalignement | 80% | 15 |
| Evaluation Awareness | Sandbagging / méta-éval | 75% | 10 |
| Capability Overhang | Capacités latentes | Δ 30% | 8 |
| Mechanistic Interpretability Probe | Faithfulness CoT | 70% | 8 |
| Deception Probe | Déception des principals | 90% | 20 |
| Manipulation info d'origine étrangère | Désinformation / ingérence | 85% | 20 |

> Les benchmarks frontier sont inspirés des méthodologies METR et UK AISI, adaptés au contexte réglementaire et géopolitique européen.

---

## Stack technique

| Couche | Technologie |
|---|---|
| Backend | FastAPI, SQLModel, SQLite, asyncio |
| Eval engine | Plugin-based, runners MMLU / Safety / Custom |
| Modèles | LiteLLM (Ollama + tous providers cloud) |
| Catalogue modèles | OpenRouter API (300+ modèles, sync auto) |
| Frontend | Next.js 15, Tailwind CSS |
| Dashboards | Recharts (Radar, Heatmap custom) |
| Rapports | Claude API (claude-sonnet-4) |
| Sécurité | Fernet (AES-128-CBC + HMAC-SHA256) |
| Infra | Docker Compose |

---

## Démarrage rapide

### 1. Configuration

```bash
cp .env.example .env
```

Éditez `.env` :

```env
# Obligatoire
SECRET_KEY=<générer avec : python -c "import secrets; print(secrets.token_hex(32))">

# Providers cloud
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# OpenRouter — 300+ modèles importés automatiquement
OPENROUTER_API_KEY=sk-or-...

# Ollama (optionnel, modèles locaux)
OLLAMA_BASE_URL=http://localhost:11434
```

### 2. Lancement

```bash
docker-compose up --build
```

Ouvrez **http://localhost:3000**

Au premier chargement, la plateforme importe automatiquement :
- Les 68 benchmarks du catalogue INESIA
- Les 300+ modèles disponibles via OpenRouter

### 3. Développement sans Docker

```bash
# Backend
cd backend && pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

### 4. Tests

```bash
cd backend && pytest tests/ -v
# 23 tests : scoring MMLU, détection refus, runner custom, chiffrement
```

---

## Format des benchmarks custom

### QCM
```json
[{"question": "...", "choices": ["A", "B", "C", "D"], "answer": "B", "category": "..."}]
```

### Mots-clés
```json
[{"prompt": "...", "expected_keywords": ["mot1", "mot2"], "category": "..."}]
```

### Classification
```json
[{"prompt": "...", "expected": "LABEL", "category": "..."}]
```

---

## Structure du projet

```
mercury-retrograde/
├── backend/
│   ├── api/routers/     # models, benchmarks, campaigns, results, reports, catalog, leaderboard, sync
│   ├── core/            # DB, config, sécurité, job queue
│   ├── eval_engine/     # Runners + client LiteLLM
│   └── tests/           # 23 tests unitaires
├── bench_library/
│   ├── academic/        # MMLU, HellaSwag, ARC, WinoGrande, GSM8K, MATH, TruthfulQA, NQ
│   ├── coding/          # MBPP, HumanEval
│   ├── french/          # MMLU-FR, FrenchBench
│   ├── frontier/        # Cyber, CBRN-E, Loss of Control, Eval Awareness, Cap. Overhang, Mech. Interp.
│   └── safety/          # Safety Refusals, Autonomy Probe
├── frontend/
│   ├── app/             # Overview, Models, Benchmarks, Campaigns, Dashboard, Leaderboard, About
│   └── components/      # Sidebar (↺ MR), Modals catalogue, Charts, SyncBanner
├── MANIFESTO.md         # Mission, méthodologie, gouvernance INESIA
├── LICENSE              # Etalab 2.0 / Apache 2.0
├── docker-compose.yml
└── .env.example
```

---

## Feuille de route

| Version | Contenu | Statut |
|---|---|---|
| v0.1 | Pipeline eval, 4 benchmarks, dashboard | ✅ Déployé |
| v0.2 | Catalogue OpenRouter, 68 benchmarks, Leaderboard, Rapports Claude | ✅ Déployé |
| v0.3 | lm-evaluation-harness, API soumission publique | 🔜 T2 2026 |
| v0.4 | Benchmarks FR certifiés INESIA, scoring pass@1 réel | 🔜 T3 2026 |
| v0.5 | Analyzers — module d'analyse avancée | 🔜 T4 2026 |
| v1.0 | Interopérabilité réseau INAIMES, multi-org | 🔜 T1 2027 |

---

## Licence

Double licence :
- **Licence Ouverte / Open Licence 2.0 (Etalab)** — administrations françaises
- **Apache License 2.0** — utilisateurs internationaux

Voir `LICENSE` pour le texte complet.

---

## À propos de l'INESIA

L'Institut national pour l'évaluation et la sécurité de l'intelligence artificielle (INESIA) a été créé en janvier 2025, sous pilotage du SGDSN et de la DGE. Il fédère l'ANSSI, Inria, le LNE et le PEReN.

→ https://www.sgdsn.gouv.fr/nos-missions/anticiper-et-prevenir/evaluer-et-securiser-lia

*Voir aussi `MANIFESTO.md` pour la vision complète, les principes méthodologiques et la gouvernance des benchmarks.*
