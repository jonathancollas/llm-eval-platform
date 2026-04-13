"""
Application settings — Pydantic BaseSettings with env var support.
"""
import os
from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Mercury Retrograde — INESIA Eval Platform"
    app_version: str = "0.5.0"
    debug: bool = False

    # ── Security ────────────────────────────────────────────────────────────────
    secret_key: str = Field(default="")
    # Set MERCURY_DEV_MODE=true to explicitly acknowledge dev-only ephemeral key.
    # Any unrecognised prod platform (not RENDER/RAILWAY/FLY) will also warn.
    mercury_dev_mode: bool = Field(default=False)

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        if not v:
            # Detect known production platforms
            on_prod = any(os.getenv(k) for k in (
                "RENDER", "RAILWAY_ENVIRONMENT", "FLY_APP_NAME",
                "HEROKU_APP_NAME", "K_SERVICE",  # Cloud Run
            ))
            if on_prod:
                raise ValueError(
                    "SECRET_KEY is required in production. "
                    "Generate: python -c 'import secrets; print(secrets.token_hex(32))'"
                )
            # In dev: only allow ephemeral key if explicitly opted in
            dev_mode = os.getenv("MERCURY_DEV_MODE", "").lower() in ("1", "true", "yes")
            import secrets, logging
            log = logging.getLogger(__name__)
            if dev_mode:
                log.warning(
                    "SECRET_KEY not set — ephemeral key in use (MERCURY_DEV_MODE=true). "
                    "Never deploy with this setting."
                )
            else:
                log.warning(
                    "SECRET_KEY not set — ephemeral key in use. "
                    "Set SECRET_KEY in .env or set MERCURY_DEV_MODE=true to silence this warning."
                )
            return secrets.token_hex(32)
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    # ── Database ─────────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./data/llm_eval.db"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # ── Redis (optional) ──────────────────────────────────────────────────────
    redis_url: str = ""

    # ── Benchmark library ────────────────────────────────────────────────────────
    bench_library_path: str = "/app/bench_library"
    benchmark_upload_max_bytes: int = 50 * 1024 * 1024

    # ── API providers ────────────────────────────────────────────────────────────
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    mistral_api_key: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    lakera_guard_api_key: str = ""
    lakera_guard_url: str = "https://api.lakera.ai/v2/guard"
    lakera_guard_project_id: str = ""
    lakera_guard_timeout_seconds: float = 5.0
    lakera_guard_fail_closed: bool = False

    # ── Ollama ──────────────────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"

    # ── Eval defaults ────────────────────────────────────────────────────────────
    default_max_samples: int = 50
    llm_timeout_seconds: float = 60.0       # Timeout per LLM call (was hardcoded in utils.py)
    http_timeout_seconds: float = 5.0       # Timeout for HTTP health checks (was hardcoded 5.0)
    max_concurrent_runs: int = 3
    report_model: str = "claude-sonnet-4-20250514"
    report_max_tokens: int = 4096
    report_timeout_seconds: float = 120.0   # Timeout for report generation (was hardcoded 120)

    # ── Rate limiting ────────────────────────────────────────────────────────────
    catalog_cache_ttl: int = 300
    tenant_key_rate_limit: int = 10         # Max tenant key lookups per minute per IP

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
