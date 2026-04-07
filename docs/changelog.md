# Changelog

## v0.5.0 (Avril 2026)

### Nouveaux modules
- **Genomia** — Signal Extractor (25+ signaux) + 7 classifieurs rules + LLM hybrid
- **REDBOX** — Forge adversariale (6 mutations) + exploit tracker + smart-forge
- **LLM-as-Judge** — Multi-judge + Cohen's κ + calibration CJE + bias detection
- **Agent Eval** — Trajectoires 6 axes + scoring hybride
- **Compliance** — EU AI Act (6 checks), HIPAA (5 checks), Finance (5 checks)

### Infrastructure
- PostgreSQL support (dual mode SQLite/PostgreSQL)
- Redis job queue (optional, fallback asyncio)
- Ollama local models (auto-discovery + import)
- Multi-tenant scaffolding (Tenant, User, API key auth)
- HuggingFace dataset import
- Contamination detection (4 méthodes)
- SQLite WAL mode

### Cross-Module Intelligence
- Auto-judge post-campagne (Claude, 30 items)
- Genome → REDBOX smart targeting
- Agent → Genome bridge
- Unified Campaign Insights

### Bug fixes
- LiveFeed item streaming (items now visible during execution)
- ETA computation from actual DB items
- UnboundLocalError on live feed endpoint (Python 3.12 import shadow)
- Report generation crash (missing report_max_tokens config)

### UI
- Sidebar reorganized: Core → Analyzers → REDBOX
- "Failure Genome" renamed → "Genomia"
- SWR cache layer for frontend data fetching
- Ollama models in campaign wizard (🦙 LOCAL filter)
