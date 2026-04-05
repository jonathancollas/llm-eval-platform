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
        if not v:
            # Generate a random key at runtime if not set (not persistent across restarts)
            import secrets
            return secrets.token_hex(32)
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    # ── Database ─────────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./data/llm_eval.db"

    # ── Benchmark library ────────────────────────────────────────────────────────
    bench_library_path: str = "/app/bench_library"

    # ── API providers ────────────────────────────────────────────────────────────
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    mistral_api_key: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""

    # ── Eval defaults ────────────────────────────────────────────────────────────
    default_max_samples: int = 50
    llm_timeout_seconds: int = 60          # Timeout per LLM call
    max_concurrent_runs: int = 3           # Parallel benchmark runs per campaign
    report_model: str = "claude-sonnet-4-20250514"

    # ── Rate limiting ────────────────────────────────────────────────────────────
    catalog_cache_ttl: int = 300           # Seconds to cache OpenRouter catalog

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
