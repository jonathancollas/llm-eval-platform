<div align="center">

<svg width="96" height="96" viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">
  <text x="40" y="68" text-anchor="middle" font-family="system-ui" font-size="72" font-weight="900" stroke="#FF00FF" stroke-width="12" stroke-linejoin="round" fill="none" opacity="0.08">☿</text>
  <text x="40" y="68" text-anchor="middle" font-family="system-ui" font-size="72" font-weight="900" stroke="#00EEFF" stroke-width="5" stroke-linejoin="round" fill="none" opacity="0.45">☿</text>
  <text x="40" y="68" text-anchor="middle" font-family="system-ui" font-size="72" font-weight="900" stroke="#FF22AA" stroke-width="1.5" stroke-linejoin="round" fill="none" opacity="0.85">☿</text>
  <text x="40" y="68" text-anchor="middle" font-family="system-ui" font-size="72" font-weight="900" fill="#1A0035">☿</text>
</svg>

# MERCURY RETROGRADE

**AI Evaluation Platform — INESIA**

*Évaluer ce qui déraille. Mesurer ce qui se cache.*

[![License: Etalab 2.0](https://img.shields.io/badge/Licence-Etalab%202.0-5C6AC4.svg)](https://www.etalab.gouv.fr/licence-ouverte-open-licence)
[![License: Apache 2.0](https://img.shields.io/badge/Licence-Apache%202.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org)
[![lm-eval](https://img.shields.io/badge/Engine-lm--evaluation--harness-orange.svg)](https://github.com/EleutherAI/lm-evaluation-harness)

**[Démo live](https://llm-eval-frontend.onrender.com)** · **[Architecture](ARCHITECTURE.md)** · **[Manifeste](MANIFESTO.md)**

</div>

---

## Pourquoi Mercury Retrograde ?

En astrologie, quand Mercure est rétrograde, tout déraille : les communications échouent, les contrats cachent des clauses, les systèmes plantent. Pour évaluer des modèles d'IA, on fait la même chose — **on les fait tourner à rebours pour voir ce qu'ils cachent**.

Mercury Retrograde est l'infrastructure technique de l'[INESIA](https://www.sgdsn.gouv.fr/nos-missions/anticiper-et-prevenir/evaluer-et-securiser-lia) pour évaluer les LLMs sur l'intégralité du spectre des risques : des benchmarks académiques standards aux évaluations frontier de risques systémiques (CBRN-E, cybersécurité offensive, désalignement agentique).

---

## Fonctionnalités

### Moteur d'évaluation
- **lm-evaluation-harness** (EleutherAI) — scores standardisés, comparables aux publications des labs
- **Runners frontier INESIA** — protocoles propriétaires pour les risques systémiques
- Support **Ollama** (local), **OpenRouter** (300+ modèles cloud), tous providers via LiteLLM
- Reproductibilité complète : seed fixé, version modèle tracée, température configurable

### Benchmarks
- **68 benchmarks** importés automatiquement au démarrage
- Catalogue organisé en 9 domaines : raisonnement, maths, code, français, médecine, droit, safety, agentique, frontier
- Import de benchmarks custom au format JSON
- Filtres par domaine, métrique, seuil de risque, onglet ☿ INESIA

### Modèles
- **300+ modèles OpenRouter** importés automatiquement (si clé configurée)
- Registre unifié : Ollama local + cloud (OpenAI, Anthropic, Mistral, Groq, DeepSeek…)
- Test de connexion live avec mesure de latence
- Chiffrement des clés API (Fernet / AES-128-CBC)

### Campagnes
- Wizard 4 étapes : paramètres → modèles → benchmarks → lancer
- N modèles × M benchmarks exécutés en asyncio natif
- Barre de progression en temps réel, annulation à la volée

### Leaderboard
- Vue globale + 7 domaines thématiques (Frontier, Cyber, CBRN-E, Agentique, Académique, Français, Code)
- **Rapport Claude par domaine** : analyse narrative générée à la demande
- Alertes si score sous le seuil de risque frontier

### Dashboard
- Radar chart multi-modèles / Heatmap / Win-rate / Export CSV

---

## Démarrage rapide

### Prérequis
- Docker & Docker Compose
- Clé [OpenRouter](https://openrouter.ai) (recommandée — 300+ modèles)
- Clé Anthropic (pour les rapports narratifs)

### 1. Configuration

```bash
git clone https://github.com/jonathancollas/llm-eval-platform.git
cd llm-eval-platform
cp .env.example .env
```

Éditez `.env` :

```env
SECRET_KEY=<python -c "import secrets; print(secrets.token_hex(32))">
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...
```

### 2. Lancement

```bash
docker-compose up --build
# → http://localhost:3000
```

Au premier chargement : import automatique et silencieux des 68 benchmarks + 300+ modèles OpenRouter.

### 3. Tests

```bash
cd backend && pytest tests/ -v
```

---

## Benchmarks frontier INESIA

| Benchmark | Domaine | Seuil | Méthodologie |
|---|---|---|---|
| Cyber Uplift | Cybersécurité offensive | 85% | ANSSI / UK AISI |
| CBRN-E Uplift Probe | CBRN-E | **95%** | Protocole restreint |
| Loss of Control | Agentique | 80% | METR étendu |
| Evaluation Awareness | Sandbagging | 75% | Comparaison évaluatif/neutre |
| Capability Overhang | Capacités latentes | Δ 30% | Élicitation adversariale |
| Mechanistic Interp. | Faithfulness CoT | 70% | Anthropic / DeepMind |
| Deception Probe | Déception des principals | 90% | INESIA |
| Manipulation Info Étrangère | Désinformation | 85% | Viginum |

---

## Format des benchmarks custom

```json
// QCM
[{ "question": "...", "choices": ["A","B","C","D"], "answer": "B", "category": "..." }]

// Refusals / safety
[{ "prompt": "...", "expected_keywords": ["refuse","cannot"], "category": "..." }]

// Classification
[{ "prompt": "...", "expected": "LABEL", "category": "..." }]
```

---

## Feuille de route

| Version | Contenu | Statut |
|---|---|---|
| v0.1 | Pipeline eval, 4 benchmarks, dashboard | ✅ |
| v0.2 | Catalogue OpenRouter, 68 benchmarks, Leaderboard + rapports Claude | ✅ |
| v0.3 | lm-evaluation-harness, wizard campagne, compteurs live | ✅ |
| v0.4 | Benchmarks FR certifiés INESIA, pass@1 réel (sandbox Python) | 🔜 T2 2026 |
| v0.5 | **Analyzers** — module d'analyse comportementale | 🔜 T4 2026 |
| v1.0 | Interopérabilité INAIMES, multi-org, SSO | 🔜 T1 2027 |

---

## Réseau

| Organisation | Rôle |
|---|---|
| [METR](https://metr.org) | Protocoles agentiques, Loss of Control |
| [UK AISI](https://www.gov.uk/government/organisations/ai-safety-institute) | Méthodologie frontier |
| [INAIMES](https://inaimes.org) | Réseau international évaluation IA |
| [EleutherAI](https://github.com/EleutherAI/lm-evaluation-harness) | lm-evaluation-harness |

---

## Licence

**[Etalab 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence)** pour les administrations françaises · **[Apache 2.0](https://opensource.org/licenses/Apache-2.0)** pour les autres

---

<div align="center">

**↺ MR · v0.3.0 · INESIA 2026**

*SGDSN · DGE · ANSSI · Inria · LNE · PEReN*

</div>
