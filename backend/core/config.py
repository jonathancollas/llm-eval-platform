import os
from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Mercury Retrograde — INESIA Eval Platform"
    app_version: str = "0.3.0"
    debug: bool = False

    # ── Security ────────────────────────────────────────────────────────────────
    secret_key: str = Field(default="")

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        import os
        if not v:
            if os.getenv("RENDER") or os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("FLY_APP_NAME"):
                raise ValueError("SECRET_KEY is required in production. Generate with: python -c \'import secrets; print(secrets.token_hex(32))\'")
            import secrets, logging
            logging.getLogger(__name__).warning("SECRET_KEY not set — ephemeral key used. Not safe for production!")
            return secrets.token_hex(32)
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    # ── Database ─────────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./data/llm_eval.db"
    db_pool_size: int = 5               # PostgreSQL connection pool
    db_max_overflow: int = 10           # PostgreSQL max overflow connections

    # ── Redis (optional — for job queue + caching) ────────────────────────────
    redis_url: str = ""                 # e.g. redis://localhost:6379/0

    # ── Benchmark library ────────────────────────────────────────────────────────
    bench_library_path: str = "/app/bench_library"

    # ── API providers ────────────────────────────────────────────────────────────
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    mistral_api_key: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""

    # ── Ollama (local models) ─────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"

    # ── Eval defaults ────────────────────────────────────────────────────────────
    default_max_samples: int = 50
    llm_timeout_seconds: int = 60          # Timeout per LLM call
    max_concurrent_runs: int = 3           # Parallel benchmark runs per campaign
    report_model: str = "claude-sonnet-4-20250514"
    report_max_tokens: int = 4096             # Max tokens for report generation
    report_timeout_seconds: int = 120         # Timeout for Claude report call

    # ── Rate limiting ────────────────────────────────────────────────────────────
    catalog_cache_ttl: int = 300           # Seconds to cache OpenRouter catalog

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
