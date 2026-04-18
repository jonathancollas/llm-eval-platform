# Architecture

> TODO: detailed architecture documentation

## Overview

Mercury Retrograde is composed of the following layers:

- **Frontend** — Next.js application for evaluation dashboards, campaigns, and leaderboards
- **Backend** — FastAPI service exposing the evaluation engine, benchmark management, and multi-tenant APIs
- **Eval Engine** — Core evaluation logic with support for LLM judges, harness runners, and agent trajectory evaluation
- **Storage** — SQLite (development) / PostgreSQL (production) with Alembic migrations
- **Task Queue** — Redis + Celery for asynchronous evaluation runs
- **Deployment** — Docker Compose for local and self-hosted deployments

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.11+ |
| Database | SQLite / PostgreSQL |
| Queue | Redis, Celery |
| AI Integrations | OpenRouter, Ollama, Anthropic |
| Deployment | Docker, Docker Compose |
