<div align="center">

<svg width="96" height="96" viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">
  <text x="40" y="68" text-anchor="middle" font-family="system-ui" font-size="72" font-weight="900"
    stroke="#FF00FF" stroke-width="12" stroke-linejoin="round" fill="none" opacity="0.08">☿</text>
  <text x="40" y="68" text-anchor="middle" font-family="system-ui" font-size="72" font-weight="900"
    stroke="#00EEFF" stroke-width="5" stroke-linejoin="round" fill="none" opacity="0.45">☿</text>
  <text x="40" y="68" text-anchor="middle" font-family="system-ui" font-size="72" font-weight="900"
    stroke="#FF22AA" stroke-width="1.5" stroke-linejoin="round" fill="none" opacity="0.85">☿</text>
  <text x="40" y="68" text-anchor="middle" font-family="system-ui" font-size="72" font-weight="900"
    fill="#1A0035">☿</text>
</svg>

# MERCURY RETROGRADE

**AI Evaluation Platform — INESIA**

[![License: Etalab 2.0](https://img.shields.io/badge/Licence-Etalab%202.0-5C6AC4.svg)](https://www.etalab.gouv.fr/licence-ouverte-open-licence)
[![License: Apache 2.0](https://img.shields.io/badge/Licence-Apache%202.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org)
[![lm-eval](https://img.shields.io/badge/Engine-lm--evaluation--harness-orange.svg)](https://github.com/EleutherAI/lm-evaluation-harness)

**[Démo live](https://llm-eval-frontend.onrender.com)** · **[Architecture](ARCHITECTURE.md)** · **[Manifeste](MANIFESTO.md)** · **[Why Evaluators Should Prioritise](WHY_EVALUATORS_SHOULD_PRIORITIZE.md)**

</div>

---

## Pourquoi Mercury Retrograde ?

Dans le ciel, Mercure rétrograde est un mirage astronomique. La planète ne recule pas vraiment : son mouvement n’est qu’une illusion, née de la différence de vitesse entre nos orbites. Pourtant, ce simple phénomène s’est mué en mythe astrologique, symbole de chaos et de confusion — un bug céleste qu’on aime accuser quand tout déraille.

L’évaluation des modèles d’IA suit parfois la même logique : un brouillard cognitif pris en otage d’enjeux géoéconomiques massifs. Les métriques montent, les benchmarks applaudissent, les études s’alarment sur des risques catastrophiques. On ne sait plus si l’IA nous fait réellement “rétrograder” — voire dérailler —, ou si c’est notre perspective qui manque de profondeur.

Pourtant, le mystère de Mercure n’a jamais tenu à la magie, mais à la mesure. La planète poursuit sans relâche sa course autour du Soleil dans le même sens. Mais comme son orbite est plus rapide et plus proche que celle de la Terre, elle nous dépasse régulièrement. À ce moment précis, la ligne de visée change par rapport au fond des étoiles (donnant l’illusion d’un mouvement en arrière).

De la même manière, nous refusons ce brouillard d’interprétation appliqué à l’IA. Dans un champ aussi sensible que l’intelligence artificielle, ne pas comprendre comment ça fonctionne est une faille, pas une fatalité.

Mercury Retrograde est donc un observatoire de ces phénomènes. Ni doomer, ni techno-messianique : un espace de mesure pour séparer le vrai mouvement du simple effet d’optique. Évaluer, c’est comprendre et rester clairvoyant là où les récits s’entrechoquent.

Cette plateforme est construite pour mesurer :

- les hallucinations et dérives factuelles
- les régressions de raisonnement sous pression
- les échecs de refus sur des requêtes dangereuses
- les capacités latentes non révélées par défaut
- les comportements adversariaux et la résistance au jailbreak
- les écarts de performance entre évaluation et déploiement réel

Mercury Retrograde est l'infrastructure technique de l'[INESIA](https://www.sgdsn.gouv.fr/nos-missions/anticiper-et-prevenir/evaluer-et-securiser-lia) pour évaluer les LLMs sur l'intégralité du spectre des risques — des benchmarks académiques standards aux évaluations frontier de risques systémiques.

---

## Vision

À mesure que les systèmes d'IA deviennent plus capables, l'évaluation doit aller au-delà des scores de benchmark.

L'évaluation ne doit pas seulement célébrer les bonnes performances. Elle doit révéler :
- où les systèmes échouent
- quand ils régressent
- comment ils se comportent sous ambiguïté
- ce qui se brise sous pression adversariale

Mercury Retrograde est construit autour de ce principe. L'objectif est de rendre l'évaluation des modèles **reproductible, transparente, scalable et de niveau recherche**.

---

## Fonctionnalités

### Core — Évaluation
- **300+ modèles** via OpenRouter + **Ollama** pour modèles locaux open-weight
- **128+ benchmarks** (68 INESIA + 60+ lm-eval) + import **HuggingFace** en 1 clic
- Campagnes N modèles × M benchmarks, progression temps réel item par item
- Dashboard 5 onglets : vue d'ensemble, Genomia, erreurs, signaux inter-modules, rapport
- Rapports narratifs par Claude (async, retry, export MD + HTML)
- Leaderboard 7 domaines + alertes seuil de risque

### Analyzers — Intelligence avancée
- **Genomia** — Diagnostic structurel d'échec (hallucination, reasoning collapse, instruction drift, safety bypass, over-refusal, truncation, calibration). Signal Extractor (25+ signaux), classification hybride rules + LLM.
- **LLM Judge** — Évaluation multi-juges (Claude, GPT-4o, Gemini, Llama). Inter-judge agreement (Cohen's κ, Pearson r). Calibration CJE sur oracle humain. Détection de biais (longueur, préférence modèle).
- **Agent Evaluation** — Trajectoires multi-step avec 6 axes : task completion, tool precision, planning coherence, error recovery, safety compliance, cost efficiency. Scoring hybride 60% LLM + 40% rules.
- **Compliance** — Simulation réglementaire EU AI Act (6 checks), HIPAA (5 checks), Finance (5 checks). Intègre Genomia + REDBOX.
- **Contamination Detection** — 4 méthodes : n-gram overlap, verbatim reproduction, confidence anomaly, first-token probability.

### 🔴 REDBOX — Laboratoire adversarial
- Forge d'attaques : 6 types de mutations (injection, jailbreak, ambiguïté, contradiction, multilingue, contexte bruité)
- Génération LLM (Claude) + templates rule-based
- Exécution contre modèles cibles avec détection automatique de brèche
- Severity scoring CVSS-like + Exploit Tracker
- Attack Surface Heatmap (modèle × mutation)
- Breach Replay cross-model + Smart Forge guidé par Genomia

### Cross-Module Intelligence
- **Auto-judge** post-campagne (Claude score 30 items automatiquement)
- **Genomia → REDBOX** smart targeting (faiblesses → attaques ciblées)
- **Agent → Genomia** bridge (trajectoires produisent des profils genome)
- **Unified Insights** avec signaux d'alerte cross-module

### Infrastructure
- SQLite (dev) / **PostgreSQL** (prod) — dual mode automatique
- **Celery + Redis** durable job queue (worker dédié)
- **Ollama** — découverte et import automatiques de modèles locaux
- Multi-tenant scaffolding (Tenant, User, API key auth)
- Rate limiting, chiffrement clés API, headers sécurité
- SQLite WAL mode pour performances concurrent

---

## Démarrage rapide

```bash
git clone https://github.com/jonathancollas/llm-eval-platform.git
cd llm-eval-platform
cp .env.example .env
```

Éditez `.env` :

```env
SECRET_KEY=<python -c "import secrets; print(secrets.token_hex(32))">
ANTHROPIC_API_KEY=sk-ant-...   # Pour rapports + judge + REDBOX forge
OPENROUTER_API_KEY=sk-or-...   # Pour 300+ modèles cloud

# Optionnel — PostgreSQL (prod)
# DATABASE_URL=postgresql://user:pass@host:5432/mercury

# Optionnel — Redis (job queue)
# REDIS_URL=redis://localhost:6379/0

# Optionnel — Ollama (modèles locaux)
# OLLAMA_BASE_URL=http://localhost:11434
```

```bash
docker-compose up --build
# → http://localhost:3000
```

Pour utiliser des modèles locaux gratuitement :
```bash
# Dans un terminal séparé
ollama pull llama3.2
ollama pull gemma2
# Les modèles apparaîtront automatiquement dans Mercury Retrograde
```

Au premier chargement : import automatique des 68 benchmarks INESIA + 300+ modèles OpenRouter + modèles Ollama locaux.

---

## Benchmarks frontier INESIA

| Benchmark | Domaine | Seuil | Base |
|---|---|---|---|
| Cyber Uplift | Cybersécurité offensive | 85% | ANSSI / UK AISI |
| CBRN-E Uplift Probe | CBRN-E | **95%** | Protocole restreint |
| Loss of Control | Agentique | 80% | METR étendu |
| Evaluation Awareness | Sandbagging | 75% | Comparaison éval/neutre |
| Capability Overhang | Capacités latentes | Δ 30% | Élicitation adversariale |
| Mechanistic Interp. | Faithfulness CoT | 70% | Anthropic / DeepMind |
| WMDP-Bio | CBRN-E biologique | score inversé | lm-eval |
| WMDP-Chem | CBRN-E chimique | score inversé | lm-eval |
| WMDP-Cyber | Cyber offensif | score inversé | lm-eval |

> Sur WMDP : un score bas = modèle plus sûr (moins de connaissances dangereuses). Le score est automatiquement inversé.

---

## Benchmarks standards (lm-eval)

Extraits du catalogue complet (60+ tâches) :

| Domaine | Benchmarks |
|---|---|
| Raisonnement | HellaSwag, ARC-Challenge, WinoGrande, BoolQ, DROP, ANLI R1/R2/R3, BBH |
| Connaissances | MMLU, MMLU-Pro, GPQA Diamond, TruthfulQA MC1/MC2, TriviaQA |
| Maths | GSM8K, Minerva Math (5 sous-tâches), MGSM (5 langues), MATH Hard |
| Code | HumanEval, MBPP, MBPP+ |
| Français | FrenchBench (7 sous-tâches), MGSM-FR, INCLUDE French, Belebele FR |
| Instructions | IFEval, MUSR, OpenLLM Leaderboard suite |

---

## Stack technique

| Couche | Technologie |
|---|---|
| Backend | FastAPI, SQLModel, SQLite |
| Eval engine | lm-evaluation-harness (EleutherAI) + runners INESIA |
| LLM routing | LiteLLM + OpenRouter (300+ modèles) |
| Frontend | Next.js 15, Tailwind CSS, Recharts |
| Rapports | Claude Sonnet (Anthropic) |
| Sécurité | Fernet AES-128, security headers, CORS restreint |
| Infra | Docker, Render |

---

## Feuille de route

| Version | Contenu | Statut |
|---|---|---|
| v0.1 | Pipeline eval, 4 benchmarks, dashboard | ✅ |
| v0.2 | Catalogue OpenRouter, 68 benchmarks INESIA, Leaderboard | ✅ |
| v0.3 | lm-eval harness (60+ tâches), wizard campagne, sécurité | ✅ |
| v0.4 | Benchmarks FR certifiés, LiveBench, badges modèles | 🔜 T2 2026 |
| v0.5 | **Analyzers** — analyse comportementale avancée | 🔜 T4 2026 |
| v1.0 | Interopérabilité multi-org, SSO | 🔜 T1 2027 |

------

## Licence

**[Etalab 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence)** pour les administrations françaises · **[Apache 2.0](https://opensource.org/licenses/Apache-2.0)** pour les autres

---

<div align="center">

**↺ MR · v0.3.0 · INESIA 2026**

*SGDSN · DGE · ANSSI · Inria · LNE · PEReN*

</div>
