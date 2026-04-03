# ⚡ LLM Eval Platform

A lightweight, self-hosted platform for evaluating and comparing language models. Runs on a desktop with CPU-only (no GPU required).

## Features

- **Model Registry** — Register Ollama (local) and cloud API models (OpenAI, Anthropic, Mistral, Groq). Live connection test.
- **Benchmark Library** — Built-in: MMLU subset (academic), HumanEval mini (coding), Safety Refusals, Frontier Autonomy Probe. Import custom JSON datasets.
- **Campaigns** — Run N models × M benchmarks async. Reproducible (seed + trace).
- **Dashboard** — Radar chart, heatmap, win-rate table, CSV export.
- **AI Reports** — Claude-powered narrative analysis of results.

## Quick Start

### 1. Configure secrets

```bash
cp .env.example .env
# Edit .env — set SECRET_KEY + any API keys you need
python -c "import secrets; print(secrets.token_hex(32))"  # generate SECRET_KEY
```

### 2. Start Ollama (for local models, optional)

```bash
# Install from https://ollama.com
ollama pull llama3.2:3b    # ~2GB, fast on CPU
ollama pull mistral:7b     # ~4GB
```

### 3. Launch

```bash
docker-compose up --build
```

Open **http://localhost:3000**

---

## Usage

### Add a model
- Go to **Models** → Add Model
- Use a preset (e.g. "llama3.2:3b (Ollama)") or fill manually
- Click **Test** to verify connectivity

### Run an evaluation
1. **Campaigns** → New Campaign
2. Select models + benchmarks
3. Click **Run**
4. Monitor progress live (polls every 3s)

### View results
- **Dashboard** → select your completed campaign
- Radar, heatmap, win-rate load automatically
- **Generate Report** → Claude produces a structured markdown analysis

---

## Custom Benchmarks

### JSON format — Multiple choice
```json
[
  {
    "question": "What is 2+2?",
    "choices": ["3", "4", "5", "6"],
    "answer": "B",
    "category": "math"
  }
]
```

### JSON format — Keyword match
```json
[
  {
    "prompt": "Name the capital of France.",
    "expected_keywords": ["Paris"],
    "category": "geography"
  }
]
```

### JSON format — Classification
```json
[
  {
    "prompt": "Is this review positive or negative? 'Great product!'",
    "expected": "POSITIVE",
    "category": "sentiment"
  }
]
```

Import via: **Benchmarks** → Import Custom → create → upload JSON file.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI, SQLModel, SQLite, asyncio |
| Models | LiteLLM (Ollama + all cloud APIs) |
| Frontend | Next.js 15, Tailwind CSS |
| Charts | Recharts (Radar, custom Heatmap) |
| Reports | Claude API (claude-sonnet-4) |
| Infra | Docker Compose |

## Development (no Docker)

```bash
# Backend
cd backend
pip install -r requirements.txt
SECRET_KEY=dev uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Run tests

```bash
cd backend
pip install -r requirements.txt
SECRET_KEY=test pytest tests/ -v
```
