# Configuration

| Variable | Requis | Défaut | Description |
|----------|--------|--------|-------------|
| `SECRET_KEY` | ✅ | — | Dérivation clé Fernet |
| `DATABASE_URL` | — | `sqlite:///./data/llm_eval.db` | SQLite ou PostgreSQL |
| `ANTHROPIC_API_KEY` | — | — | Rapports + Judge + REDBOX |
| `OPENROUTER_API_KEY` | — | — | 300+ modèles cloud |
| `OLLAMA_BASE_URL` | — | `http://localhost:11434` | Serveur Ollama |
| `REDIS_URL` | — | — | Queue Redis (optionnel) |

## PostgreSQL (production)

```env
DATABASE_URL=postgresql://user:pass@host:5432/mercury
```

## Redis (optionnel)

```env
REDIS_URL=redis://localhost:6379/0
```
