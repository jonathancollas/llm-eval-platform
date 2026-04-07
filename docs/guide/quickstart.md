# Démarrage rapide

## Prérequis

- Docker & Docker Compose
- (Optionnel) Ollama pour modèles locaux

## Installation

```bash
git clone https://github.com/jonathancollas/llm-eval-platform.git
cd llm-eval-platform
cp .env.example .env
```

Éditez `.env` avec vos clés API, puis :

```bash
docker-compose up --build
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000/docs (Swagger)
```

## Premier run

1. **Models** — importés automatiquement depuis OpenRouter + Ollama
2. **Benchmarks** — 68 benchmarks INESIA pré-chargés
3. **Campaign** — Créer → modèles → benchmarks → Run
4. **Dashboard** — Résultats temps réel + Genomia automatique
