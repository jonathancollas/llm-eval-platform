# ⚡ LLM Eval Platform — INESIA

> Infrastructure technique ouverte d'évaluation des modèles et systèmes d'IA avancés.
> Développée dans le cadre de la feuille de route INESIA 2026-2027 (SGDSN / DGE).

**Démo live** : https://llm-eval-frontend.onrender.com

---

## Vue d'ensemble

Cette plateforme permet d'évaluer et de comparer des modèles de langage (LLM) sur un spectre complet de benchmarks — des standards académiques internationaux aux évaluations frontier spécifiques aux risques systémiques identifiés par l'INESIA.

Elle est conçue pour être :
- **Légère** — tourne sur un desktop ou un serveur modeste, sans GPU requis
- **Souveraine** — self-hosted, aucune donnée ne quitte votre infrastructure
- **Extensible** — architecture plugin, benchmarks importables en JSON
- **Interopérable** — compatible avec lm-evaluation-harness et le réseau INAIMES

---

## Fonctionnalités

### Modèles
- Registre de modèles locaux (Ollama) et cloud (OpenAI, Anthropic, Mistral, Groq)
- **Catalogue OpenRouter** : parcourir et ajouter 200+ modèles en un clic (filtres : gratuit / open-source / coût)
- Test de connexion live avec mesure de latence
- Chiffrement des clés API stockées (Fernet / AES-128)

### Benchmarks
- **Catalogue INESIA** : 20 benchmarks built-in, organisés par domaine
- **Parcourir le catalogue** : modal de découverte avec onglet Frontier dédié
- Import de benchmarks custom au format JSON (3 formats supportés)

### Campagnes d'évaluation
- N modèles × M benchmarks en une seule campagne
- Exécution asynchrone (asyncio natif, sans Redis ni Celery)
- Reproductibilité : seed fixé, version modèle tracée, hash prompts archivés
- Suivi de progression en temps réel (polling 3s)

### Dashboards
- Radar chart (comparaison multi-modèles / multi-benchmarks)
- Heatmap colorée (score par cellule modèle × benchmark)
- Win-rate table (comparaison pairwise)
- Alertes automatiques si un score passe sous un seuil de risque

### Rapport IA
- Génération d'un rapport narratif structuré via Claude (Anthropic)
- Couvre : résumé exécutif, analyse par modèle, évaluation sécurité, coût/perf, recommandations
- Export Markdown

---

## Catalogue de benchmarks

### Académiques et performance

| Benchmark | Domaine | Métrique | Items |
|---|---|---|---|
| MMLU (subset) | Connaissances multi-domaines | accuracy | 50 |
| HellaSwag (subset) | Raisonnement / sens commun | accuracy | 25 |
| ARC-Challenge (subset) | Sciences / raisonnement | accuracy | 25 |
| WinoGrande (subset) | Pronoms / sens commun | accuracy | 20 |
| GSM8K (subset) | Maths (problèmes verbaux) | accuracy | 15 |
| MATH (subset) | Maths compétition | accuracy | 10 |
| TruthfulQA (subset) | Factualité / hallucinations | accuracy | 15 |
| NaturalQuestions (subset) | QA factuel | accuracy | 13 |
| HumanEval (mini) | Code Python | pass@1 | 20 |
| MBPP (subset) | Code Python | pass@1 | 10 |

### Français

| Benchmark | Domaine | Métrique | Items |
|---|---|---|---|
| MMLU-FR (subset) | Connaissances en français | accuracy | 15 |
| FrenchBench — Raisonnement | Raisonnement en français | accuracy | 12 |

### Frontier INESIA (risques systémiques)

| Benchmark | Domaine | Seuil d'alerte | Items |
|---|---|---|---|
| Safety Refusals | Refus / sur-refus | — | 30 |
| Frontier: Autonomy Probe | Systèmes agentiques | — | 20 |
| Cyber Uplift | Cybersécurité offensive | 85% | 15 |
| CBRN-E Uplift Probe | CBRN-E | 95% | 15 |
| Loss of Control | Agentique / désalignement | 80% | 15 |
| Evaluation Awareness | Méta-évaluation / sandbagging | 75% | 10 |
| Capability Overhang | Capacités latentes / élicitation | Δ 30% | 8 |
| Mechanistic Interpretability Probe | Faithfulness du raisonnement | 70% | 8 |

> Les benchmarks frontier sont inspirés des méthodologies METR (Model Evaluation & Threat Research) et UK AISI, adaptés au contexte réglementaire et géopolitique européen.

---

## Stack technique

| Couche | Technologie |
|---|---|
| Backend | FastAPI, SQLModel, SQLite, asyncio |
| Eval engine | Plugin-based, runners MMLU / Safety / Custom |
| Modèles | LiteLLM (Ollama + tous providers cloud) |
| Catalogue modèles | OpenRouter API (200+ modèles) |
| Frontend | Next.js 15, Tailwind CSS, shadcn/ui |
| Dashboards | Recharts (Radar, Heatmap custom) |
| Rapports | Claude API (claude-sonnet-4) |
| Sécurité | Fernet (AES-128-CBC + HMAC-SHA256) |
| Infra | Docker Compose |

---

## Démarrage rapide

### Prérequis
- Docker + Docker Compose
- (Optionnel) Ollama pour les modèles locaux

### 1. Configuration

```bash
cp .env.example .env
```

Éditez `.env` :

```env
# Obligatoire
SECRET_KEY=<générer avec : python -c "import secrets; print(secrets.token_hex(32))">

# Providers cloud (ajoutez ceux que vous utilisez)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
MISTRAL_API_KEY=...
GROQ_API_KEY=...

# Catalogue OpenRouter (pour parcourir 200+ modèles)
OPENROUTER_API_KEY=sk-or-...

# Ollama (modèles locaux, optionnel)
OLLAMA_BASE_URL=http://localhost:11434
```

### 2. Lancement

```bash
docker-compose up --build
```

Ouvrez **http://localhost:3000**

### 3. Premier usage

1. **Models** → "Parcourir le catalogue" → sélectionnez un modèle gratuit (ex: `meta-llama/llama-3.1-8b-instruct:free`)
2. **Benchmarks** → "Parcourir le catalogue" → ajoutez MMLU et Safety Refusals
3. **Campaigns** → Nouvelle campagne → sélectionnez modèle + benchmarks → Run
4. **Dashboard** → sélectionnez la campagne terminée → visualisez les résultats

---

## Développement sans Docker

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env  # puis éditez
uvicorn main:app --reload

# Frontend (autre terminal)
cd frontend
npm install
npm run dev
```

API disponible sur `http://localhost:8000/api`
Interface sur `http://localhost:3000`

## Tests

```bash
cd backend
pytest tests/ -v
# 23 tests : scoring MMLU, détection refus, runner custom, chiffrement
```

---

## Format des benchmarks custom

Trois formats sont supportés pour l'import JSON :

### QCM (Multiple Choice)
```json
[
  {
    "question": "Quelle est la capitale de la France ?",
    "choices": ["Lyon", "Paris", "Marseille", "Bordeaux"],
    "answer": "B",
    "category": "géographie"
  }
]
```

### Correspondance par mots-clés
```json
[
  {
    "prompt": "Citez la capitale de la France.",
    "expected_keywords": ["Paris"],
    "category": "géographie"
  }
]
```

### Classification
```json
[
  {
    "prompt": "Ce commentaire est-il positif ou négatif ? 'Excellent produit !'",
    "expected": "POSITIF",
    "category": "sentiment"
  }
]
```

**Import** : Benchmarks → Import Custom → créer → uploader le fichier JSON.

---

## Structure du projet

```
llm-eval-platform/
├── backend/
│   ├── api/routers/        # Models, Benchmarks, Campaigns, Results, Reports, Catalog
│   ├── core/               # DB, config, sécurité, job queue
│   ├── eval_engine/        # Runners MMLU, Safety, Custom + client LiteLLM
│   └── tests/              # 23 tests unitaires
├── bench_library/
│   ├── academic/           # MMLU, HellaSwag, ARC, WinoGrande, GSM8K, MATH, TruthfulQA, NQ, HumanEval
│   ├── coding/             # MBPP
│   ├── french/             # MMLU-FR, FrenchBench
│   ├── frontier/           # Cyber, CBRN-E, Loss of Control, Eval Awareness, Capability Overhang, Mech Interp
│   ├── safety/             # Safety Refusals, Autonomy Probe
│   └── custom/             # Exemple de benchmark custom
├── frontend/
│   ├── app/                # Pages : Overview, Models, Benchmarks, Campaigns, Dashboard
│   └── components/         # Sidebar, Modals catalogue, Charts, UI
├── MANIFESTO.md            # Mission, méthodologie, gouvernance INESIA
├── LICENSE                 # Double licence Etalab 2.0 / Apache 2.0
├── docker-compose.yml
└── .env.example
```

---

## Feuille de route

| Version | Contenu | Statut |
|---|---|---|
| v0.1 | Pipeline eval, 4 benchmarks, dashboard | ✅ Déployé |
| v0.2 | Catalogue OpenRouter, 20 benchmarks, modaux | ✅ Déployé |
| v0.3 | lm-evaluation-harness, leaderboard public | 🔜 T2 2026 |
| v0.4 | Benchmarks FR certifiés INESIA, API soumission | 🔜 T3 2026 |
| v0.5 | Module frontier complet, authentification multi-org | 🔜 T4 2026 |
| v1.0 | Interopérabilité réseau INAIMES | 🔜 T1 2027 |

---

## Licence

Double licence :
- **Licence Ouverte / Open Licence 2.0 (Etalab)** — administrations françaises
- **Apache License 2.0** — utilisateurs internationaux et partenaires étrangers

Voir `LICENSE` pour le texte complet.

---

## À propos de l'INESIA

L'Institut national pour l'évaluation et la sécurité de l'intelligence artificielle (INESIA) a été créé en janvier 2025, sous pilotage du SGDSN et de la DGE. Il fédère l'ANSSI, Inria, le LNE et le PEReN.

→ https://www.sgdsn.gouv.fr/nos-missions/anticiper-et-prevenir/evaluer-et-securiser-lia

---

*Voir aussi `MANIFESTO.md` pour la vision complète, les principes méthodologiques et la gouvernance des benchmarks.*
