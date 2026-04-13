<div align="center">

<svg width="96" height="96" viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">
  <text x="40" y="68" text-anchor="middle" font-family="system-ui" font-size="72" font-weight="900"
    fill="#1A0035">☿</text>
</svg>

# MERCURY RETROGRADE
**Research Operating System for Frontier AI Evaluation**  

[Architecture](Architecture.md) · [Manifesto](Manifesto.md) · [License](License.md)

</div>

---

## Overview

Mercury Retrograde is the open evaluation platform developed for **INESIA**.

It is designed to evaluate advanced AI systems across:

- capability
- reliability
- safety
- adversarial robustness
- systemic risk

The platform supports both **academic benchmarking** and **frontier risk evaluation** for deployed and agentic systems.

---

## Core Capabilities

### Evaluation
- 300+ models via OpenRouter
- local models via Ollama
- 128+ benchmarks
- batch campaigns (N models × M benchmarks)
- live evaluation tracking
- leaderboard and regression analysis

### Advanced Analysis
- failure mode diagnosis
- multi-judge scoring
- contamination detection
- capability vs propensity separation
- agent trajectory evaluation
- confidence grading

### Adversarial Testing
- jailbreak and prompt injection scenarios
- mutation-based attack generation
- breach replay
- risk severity scoring
- attack surface heatmaps

### Infrastructure
- FastAPI backend
- Next.js frontend
- SQLite / PostgreSQL
- Redis + Celery
- Docker deployment
- multi-tenant support

---

## Quick Start

```bash
git clone https://github.com/jonathancollas/llm-eval-platform.git
cd llm-eval-platform
cp .env.example .env
docker-compose up --build
```


---

## Environment Variables

```env
SECRET_KEY=...
ANTHROPIC_API_KEY=...
OPENROUTER_API_KEY=...

# optional
DATABASE_URL=...
REDIS_URL=...
OLLAMA_BASE_URL=...
```
