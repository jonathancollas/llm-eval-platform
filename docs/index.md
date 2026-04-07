# Mercury Retrograde

**AI Evaluation Platform — INESIA**

☿ Mercury Retrograde est l'infrastructure technique de l'INESIA pour évaluer les LLMs sur l'intégralité du spectre des risques.

## Modules

| Module | Description |
|--------|-------------|
| **Core Eval** | Campagnes N×M, progression temps réel, rapports Claude |
| **Genomia** | Diagnostic structurel d'échec (25+ signaux, 7 classifieurs) |
| **REDBOX** | Laboratoire adversarial (6 mutations, smart-forge) |
| **LLM Judge** | Multi-judge ensemble + calibration + bias detection |
| **Agent Eval** | Trajectoires multi-step, 6 axes de scoring |
| **Compliance** | EU AI Act, HIPAA, Finance |

## Quick Start

```bash
git clone https://github.com/jonathancollas/llm-eval-platform.git
cd llm-eval-platform
cp .env.example .env  # Edit with your API keys
docker-compose up --build
# → http://localhost:3000
```

## Architecture

Voir la page [Architecture](architecture.md) pour les spécifications techniques complètes.
