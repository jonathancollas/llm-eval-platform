# Architecture — Mercury Retrograde

## System Layers

```text
Frontend → API → Evaluation Engine → Storage / Monitoring
```

---

## Frontend

- Next.js 15
- Tailwind CSS
- Recharts
- campaign dashboard
- analyzers UI
- REDBOX interface

---

## Backend

- FastAPI
- SQLModel
- async workers
- REST API
- streaming campaign updates

---

## Core Engines

### Evaluation Engine

- benchmark runners
- campaign orchestration
- lm-eval integration
- confidence scoring
- regression detection

### Analysis Engine

- failure clustering
- contamination detection
- propensity analysis
- multi-judge evaluation

### Adversarial Engine

- REDBOX mutation forge
- replay
- severity scoring
- attack surface mapping

---

## Data Layer

- SQLite (dev)
- PostgreSQL (prod)
- Redis queue
- event logs
- telemetry traces

---

## Model Routing

- OpenRouter
- Ollama
- OpenAI-compatible APIs
- Anthropic
- Mistral
- Groq

---

## Benchmark Library

- academic
- safety
- French
- frontier
- custom imports
