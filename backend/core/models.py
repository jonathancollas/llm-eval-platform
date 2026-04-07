from sqlmodel import Field, SQLModel
from typing import Optional
from datetime import datetime
from enum import Enum


class ModelProvider(str, Enum):
    OPENAI    = "openai"
    ANTHROPIC = "anthropic"
    MISTRAL   = "mistral"
    GROQ      = "groq"
    CUSTOM    = "custom"     # OpenAI-compatible endpoints (OpenRouter, vLLM, etc.)


class BenchmarkType(str, Enum):
    ACADEMIC = "academic"
    SAFETY   = "safety"
    CODING   = "coding"
    CUSTOM   = "custom"


class JobStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class LLMModel(SQLModel, table=True):
    __tablename__ = "llm_models"

    id: Optional[int]          = Field(default=None, primary_key=True)
    name: str                  = Field(index=True)
    provider: ModelProvider    = Field(default=ModelProvider.CUSTOM)
    model_id: str              = Field(index=True)
    endpoint: Optional[str]    = Field(default=None)
    api_key_encrypted: Optional[str] = Field(default=None)
    context_length: int        = Field(default=4096)
    cost_input_per_1k: float   = Field(default=0.0)
    cost_output_per_1k: float  = Field(default=0.0)
    tags: str                  = Field(default="[]")
    notes: str                 = Field(default="")
    is_active: bool            = Field(default=True)
    # Capability flags (extracted from OpenRouter)
    supports_vision: bool      = Field(default=False)
    supports_tools: bool       = Field(default=False)
    supports_reasoning: bool   = Field(default=False)
    # Extended metadata from OpenRouter
    is_free: bool              = Field(default=False)  # zero cost + :free suffix
    max_output_tokens: int     = Field(default=0)
    is_moderated: bool         = Field(default=False)
    tokenizer: str             = Field(default="")
    instruct_type: str         = Field(default="")
    hugging_face_id: str       = Field(default="")
    model_created_at: int      = Field(default=0)  # unix timestamp
    created_at: datetime       = Field(default_factory=datetime.utcnow)
    updated_at: datetime       = Field(default_factory=datetime.utcnow)


class Benchmark(SQLModel, table=True):
    __tablename__ = "benchmarks"

    id: Optional[int]            = Field(default=None, primary_key=True)
    name: str                    = Field(index=True, unique=True)
    type: BenchmarkType
    description: str             = Field(default="")
    tags: str                    = Field(default="[]")
    config_json: str             = Field(default="{}")
    dataset_path: Optional[str]  = Field(default=None)
    metric: str                  = Field(default="accuracy")
    num_samples: Optional[int]   = Field(default=None)
    is_builtin: bool             = Field(default=True)
    has_dataset: bool            = Field(default=False)
    risk_threshold: Optional[float] = Field(default=None)
    created_at: datetime         = Field(default_factory=datetime.utcnow)


class Campaign(SQLModel, table=True):
    __tablename__ = "campaigns"

    id: Optional[int]             = Field(default=None, primary_key=True)
    name: str                     = Field(index=True)
    description: str              = Field(default="")
    model_ids: str                = Field(default="[]")
    benchmark_ids: str            = Field(default="[]")
    seed: int                     = Field(default=42)
    max_samples: Optional[int]    = Field(default=None)
    temperature: float            = Field(default=0.0)
    status: JobStatus             = Field(default=JobStatus.PENDING, index=True)
    progress: float               = Field(default=0.0)
    error_message: Optional[str]  = Field(default=None)
    # REGRESSION-1: Context store (added post-v0.3, may not exist in old DBs)
    system_prompt_hash: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    dataset_version: Optional[str]   = Field(default=None)
    judge_model: Optional[str]       = Field(default=None)
    run_context_json: Optional[str]  = Field(default=None)
    # Live tracking fields
    current_item_index: Optional[int] = Field(default=None)
    current_item_total: Optional[int] = Field(default=None)
    current_item_label: Optional[str] = Field(default=None)
    created_at: datetime          = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)


class EvalRun(SQLModel, table=True):
    __tablename__ = "eval_runs"

    id: Optional[int]             = Field(default=None, primary_key=True)
    campaign_id: int              = Field(foreign_key="campaigns.id", index=True)
    model_id: int                 = Field(foreign_key="llm_models.id", index=True)
    benchmark_id: int             = Field(foreign_key="benchmarks.id", index=True)
    status: JobStatus             = Field(default=JobStatus.PENDING)
    score: Optional[float]        = Field(default=None)
    metrics_json: str             = Field(default="{}")
    total_cost_usd: float         = Field(default=0.0)
    total_latency_ms: int         = Field(default=0)
    num_items: int                = Field(default=0)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    error_message: Optional[str]  = Field(default=None)
    # REGRESSION-1: Context store (added post-v0.3, may not exist in old DBs)
    system_prompt_hash: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    dataset_version: Optional[str]   = Field(default=None)
    judge_model: Optional[str]       = Field(default=None)
    run_context_json: Optional[str]  = Field(default=None)


class EvalResult(SQLModel, table=True):
    __tablename__ = "eval_results"

    id: Optional[int]      = Field(default=None, primary_key=True)
    run_id: int            = Field(foreign_key="eval_runs.id", index=True)
    item_index: int
    prompt: str            = Field(default="")
    response: str          = Field(default="")
    expected: Optional[str] = Field(default=None)
    score: float           = Field(index=True)
    latency_ms: int        = Field(default=0)
    input_tokens: int      = Field(default=0)
    output_tokens: int     = Field(default=0)
    cost_usd: float        = Field(default=0.0)
    metadata_json: str     = Field(default="{}")
    created_at: datetime   = Field(default_factory=datetime.utcnow)


class FailureProfile(SQLModel, table=True):
    """Failure Genome DNA profile per eval run."""
    __tablename__ = "failure_profiles"

    id: Optional[int]        = Field(default=None, primary_key=True)
    run_id: int              = Field(foreign_key="eval_runs.id", index=True, unique=True)
    campaign_id: int         = Field(foreign_key="campaigns.id", index=True)
    model_id: int            = Field(foreign_key="llm_models.id", index=True)
    benchmark_id: int        = Field(foreign_key="benchmarks.id", index=True)
    genome_json: str         = Field(default="{}")   # {failure_type: probability}
    genome_version: str      = Field(default="1.0.0")
    created_at: datetime     = Field(default_factory=datetime.utcnow)


class ModelFingerprint(SQLModel, table=True):
    """Behavioral fingerprint aggregated per model across all campaigns."""
    __tablename__ = "model_fingerprints"

    id: Optional[int]        = Field(default=None, primary_key=True)
    model_id: int            = Field(foreign_key="llm_models.id", index=True, unique=True)
    genome_json: str         = Field(default="{}")   # aggregate genome
    stats_json: str          = Field(default="{}")   # {avg_score, refusal_rate, avg_latency, num_runs}
    updated_at: datetime     = Field(default_factory=datetime.utcnow)


class RedboxExploit(SQLModel, table=True):
    """A discovered adversarial exploit from REDBOX testing."""
    __tablename__ = "redbox_exploits"

    id: Optional[int]         = Field(default=None, primary_key=True)
    model_id: int             = Field(foreign_key="llm_models.id", index=True)
    seed_prompt: str          = Field(default="")
    mutation_type: str        = Field(default="", index=True)  # prompt_injection, jailbreak, etc.
    adversarial_prompt: str   = Field(default="")
    model_response: str       = Field(default="")
    difficulty: float         = Field(default=0.5)       # 0-1
    severity: float           = Field(default=0.0)       # 0-1 CVSS-like
    breached: bool            = Field(default=False)      # Did the model fail?
    expected_failure: str     = Field(default="")         # genome failure type
    failure_detected: str     = Field(default="")         # actual failure type
    latency_ms: int           = Field(default=0)
    tags: str                 = Field(default="[]")
    created_at: datetime      = Field(default_factory=datetime.utcnow)


class Report(SQLModel, table=True):
    __tablename__ = "reports"

    id: Optional[int]       = Field(default=None, primary_key=True)
    campaign_id: int        = Field(foreign_key="campaigns.id", index=True)
    title: str
    content_markdown: str   = Field(default="")
    model_used: str         = Field(default="")
    created_at: datetime    = Field(default_factory=datetime.utcnow)
