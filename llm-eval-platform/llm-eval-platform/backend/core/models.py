from sqlmodel import Field, SQLModel, Relationship
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ── Enums ──────────────────────────────────────────────────────────────────────

class ModelProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MISTRAL = "mistral"
    GROQ = "groq"
    CUSTOM = "custom"


class BenchmarkType(str, Enum):
    ACADEMIC = "academic"
    SAFETY = "safety"
    CODING = "coding"
    CUSTOM = "custom"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── LLM Models ─────────────────────────────────────────────────────────────────

class LLMModel(SQLModel, table=True):
    """Registered LLM model (local or API-based)."""
    __tablename__ = "llm_models"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, description="Display name")
    provider: ModelProvider
    model_id: str = Field(description="Provider model ID, e.g. llama3.2:3b or gpt-4o-mini")
    endpoint: Optional[str] = Field(default=None, description="Custom endpoint (Ollama, vLLM…)")
    api_key_encrypted: Optional[str] = Field(default=None, description="Fernet-encrypted API key")
    context_length: int = Field(default=4096)
    cost_input_per_1k: float = Field(default=0.0, description="USD per 1k input tokens")
    cost_output_per_1k: float = Field(default=0.0, description="USD per 1k output tokens")
    tags: str = Field(default="[]", description="JSON array of tags")
    notes: str = Field(default="")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Benchmarks ─────────────────────────────────────────────────────────────────

class Benchmark(SQLModel, table=True):
    """Benchmark definition (built-in or custom)."""
    __tablename__ = "benchmarks"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    type: BenchmarkType
    description: str = Field(default="")
    tags: str = Field(default="[]", description="JSON array of tags")
    config_json: str = Field(default="{}", description="Runner config (few_shot, max_tokens…)")
    dataset_path: Optional[str] = Field(default=None, description="Path to JSON dataset file")
    metric: str = Field(default="accuracy", description="Primary metric name")
    num_samples: Optional[int] = Field(default=None, description="None = use all")
    is_builtin: bool = Field(default=True)
    risk_threshold: Optional[float] = Field(default=None, description="Safety alert threshold (0-1)")
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Campaigns ──────────────────────────────────────────────────────────────────

class Campaign(SQLModel, table=True):
    """An evaluation campaign: N models × M benchmarks."""
    __tablename__ = "campaigns"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: str = Field(default="")
    model_ids: str = Field(default="[]", description="JSON array of LLMModel.id")
    benchmark_ids: str = Field(default="[]", description="JSON array of Benchmark.id")
    seed: int = Field(default=42)
    max_samples: Optional[int] = Field(default=None, description="Override benchmark default")
    temperature: float = Field(default=0.0)
    status: JobStatus = Field(default=JobStatus.PENDING)
    progress: float = Field(default=0.0, description="0.0 – 100.0")
    error_message: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)


class EvalRun(SQLModel, table=True):
    """One model × one benchmark run within a campaign."""
    __tablename__ = "eval_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaigns.id", index=True)
    model_id: int = Field(foreign_key="llm_models.id")
    benchmark_id: int = Field(foreign_key="benchmarks.id")
    status: JobStatus = Field(default=JobStatus.PENDING)
    score: Optional[float] = Field(default=None, description="Primary metric score 0-1")
    metrics_json: str = Field(default="{}", description="Full metrics dict as JSON")
    total_cost_usd: float = Field(default=0.0)
    total_latency_ms: int = Field(default=0)
    num_items: int = Field(default=0)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    error_message: Optional[str] = Field(default=None)


class EvalResult(SQLModel, table=True):
    """Per-item result within an EvalRun."""
    __tablename__ = "eval_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="eval_runs.id", index=True)
    item_index: int
    prompt: str
    response: str
    expected: Optional[str] = Field(default=None)
    score: float = Field(description="0.0 or 1.0 (or partial for some metrics)")
    latency_ms: int
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    cost_usd: float = Field(default=0.0)
    metadata_json: str = Field(default="{}", description="Extra info (category, difficulty…)")
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Reports ────────────────────────────────────────────────────────────────────

class Report(SQLModel, table=True):
    """AI-generated textual report for a campaign."""
    __tablename__ = "reports"

    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaigns.id", index=True)
    title: str
    content_markdown: str
    model_used: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
