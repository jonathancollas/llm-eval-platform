from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from pathlib import Path

class Settings(BaseSettings):
    # App
    app_name: str = "LLM Eval Platform"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database
    database_url: str = "sqlite:///./data/eval_platform.db"

    # Security — used to encrypt stored API keys
    secret_key: str = Field(..., description="32-byte hex secret for Fernet encryption")

    # LiteLLM / providers
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    mistral_api_key: str = ""
    groq_api_key: str = ""

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # Bench library
    bench_library_path: str = str(Path(__file__).parent.parent.parent / "bench_library")

    # Claude report generation
    report_model: str = "claude-sonnet-4-20250514"
    report_max_tokens: int = 4096

    # Eval defaults
    default_seed: int = 42
    default_max_samples: int = 50
    default_temperature: float = 0.0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
