from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    app_name: str = "Mercury Retrograde — INESIA Eval Platform"
    app_version: str = "0.3.0"

    # Security
    secret_key: str = Field(default="dev-secret-key-change-in-production-64chars!!!!!")

    # Database
    database_url: str = "sqlite:///./data/llm_eval.db"

    # Benchmark library — inside Docker image at /app/bench_library
    bench_library_path: str = "/app/bench_library"

    # Model providers
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    mistral_api_key: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # Eval defaults
    default_max_samples: int = 50
    report_model: str = "claude-sonnet-4-20250514"

    debug: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
