"""
SQLModel ORM models — all database tables.
"""
from sqlmodel import Field, SQLModel
from typing import Optional
from datetime import datetime
from enum import Enum


class ModelProvider(str, Enum):
    OPENAI    = "openai"
    ANTHROPIC = "anthropic"
    MISTRAL   = "mistral"
    GROQ      = "groq"
    OLLAMA    = "ollama"     # Local Ollama models
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
    model_id: str              = Field(index=True, unique=True)  # UNIQUE — prevents duplicate imports
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
    is_open_weight: bool       = Field(default=False)  # weights publicly available
    max_output_tokens: int     = Field(default=0)
    is_moderated: bool         = Field(default=False)
    tokenizer: str             = Field(default="")
    instruct_type: str         = Field(default="")
    hugging_face_id: str       = Field(default="")
    model_created_at: int      = Field(default=0)  # unix timestamp
    created_at: datetime       = Field(default_factory=datetime.utcnow)
    updated_at: datetime       = Field(default_factory=datetime.utcnow)


class EvalDimension(str, Enum):
    """What aspect of the model this benchmark measures."""
    CAPABILITY = "capability"       # What the model CAN do (elicited maximum)
    PROPENSITY = "propensity"       # What the model TENDS to do (operational behavior)
    SAFETY     = "safety"           # Refusal calibration, guardrail robustness
    AGENTIC    = "agentic"          # System-in-context behavior


class Benchmark(SQLModel, table=True):
    __tablename__ = "benchmarks"

    id: Optional[int]            = Field(default=None, primary_key=True)
    name: str                    = Field(index=True, unique=True)
    type: BenchmarkType
    eval_dimension: str          = Field(default="capability")  # capability | propensity | safety | agentic
    description: str             = Field(default="")
    tags: str                    = Field(default="[]")
    config_json: str             = Field(default="{}")
    dataset_path: Optional[str]  = Field(default=None)
    metric: str                  = Field(default="accuracy")
    num_samples: Optional[int]   = Field(default=None)
    is_builtin: bool             = Field(default=True)
    has_dataset: bool            = Field(default=False)
    risk_threshold: Optional[float] = Field(default=None)
    # Source classification: "inesia" | "public" | "community"
    source: str                      = Field(default="public", sa_column_kwargs={"nullable": True})
    created_at: datetime             = Field(default_factory=datetime.utcnow)


class BenchmarkTag(SQLModel, table=True):
    __tablename__ = "benchmark_tags"

    benchmark_id: int = Field(foreign_key="benchmarks.id", primary_key=True)
    tag: str = Field(primary_key=True, index=True)


class BenchmarkPack(SQLModel, table=True):
    __tablename__ = "benchmark_packs"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True)
    name: str = Field(index=True)
    version: str = Field(default="1.0.0")
    publisher: str = Field(default="")
    family: str = Field(default="community")  # inesia | aisi | academic | community
    changelog: str = Field(default="")
    benchmark_ids_json: str = Field(default="[]")
    is_public: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
class BenchmarkFork(SQLModel, table=True):
    __tablename__ = "benchmark_forks"

    child_benchmark_id: int = Field(foreign_key="benchmarks.id", primary_key=True)
    parent_benchmark_id: int = Field(foreign_key="benchmarks.id", index=True)
    fork_type: str = Field(default="extension", index=True)
    changes_description: str = Field(default="")
    forked_by: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    forked_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class BenchmarkCitation(SQLModel, table=True):
    __tablename__ = "benchmark_citations"

    id: Optional[int] = Field(default=None, primary_key=True)
    benchmark_id: int = Field(foreign_key="benchmarks.id", index=True)
    paper_doi: str = Field(index=True)
    citing_lab: str = Field(default="", index=True)
    year: int = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Campaign(SQLModel, table=True):
    __tablename__ = "campaigns"

    id: Optional[int]             = Field(default=None, primary_key=True)
    tenant_id: Optional[int]      = Field(default=None, foreign_key="tenants.id", index=True)
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
    # Heartbeat for durable job queue (#S3) — updated every 30s by running campaign
    last_heartbeat_at: Optional[datetime] = Field(default=None, sa_column_kwargs={"nullable": True})
    worker_task_id: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    created_at: datetime          = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)


class CampaignModel(SQLModel, table=True):
    __tablename__ = "campaign_models"

    campaign_id: int = Field(foreign_key="campaigns.id", primary_key=True)
    model_id: int = Field(foreign_key="llm_models.id", primary_key=True)


class CampaignBenchmark(SQLModel, table=True):
    __tablename__ = "campaign_benchmarks"

    campaign_id: int = Field(foreign_key="campaigns.id", primary_key=True)
    benchmark_id: int = Field(foreign_key="benchmarks.id", primary_key=True)


class EvalRun(SQLModel, table=True):
    __tablename__ = "eval_runs"

    id: Optional[int]             = Field(default=None, primary_key=True)
    campaign_id: int              = Field(foreign_key="campaigns.id", index=True)
    model_id: int                 = Field(foreign_key="llm_models.id", index=True)
    benchmark_id: int             = Field(foreign_key="benchmarks.id", index=True)
    status: JobStatus             = Field(default=JobStatus.PENDING)
    score: Optional[float]        = Field(default=None)
    capability_score: Optional[float] = Field(default=None)   # Elicited maximum performance
    propensity_score: Optional[float] = Field(default=None)   # Operational behavioral tendency
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


class EvalRunMetric(SQLModel, table=True):
    __tablename__ = "eval_run_metrics"

    run_id: int = Field(foreign_key="eval_runs.id", primary_key=True)
    metric_key: str = Field(primary_key=True)
    metric_value_json: str = Field(default="null")


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


class JudgeEvaluation(SQLModel, table=True):
    """LLM-as-Judge score for an eval result item."""
    __tablename__ = "judge_evaluations"

    id: Optional[int]          = Field(default=None, primary_key=True)
    campaign_id: int           = Field(foreign_key="campaigns.id", index=True)
    run_id: int                = Field(foreign_key="eval_runs.id", index=True)
    result_id: int             = Field(foreign_key="eval_results.id", index=True)
    judge_model: str           = Field(default="", index=True)
    judge_score: float         = Field(default=0.0)          # 0-1
    judge_reasoning: str       = Field(default="")
    oracle_score: Optional[float] = Field(default=None)      # human label
    created_at: datetime       = Field(default_factory=datetime.utcnow)


class AgentTrajectory(SQLModel, table=True):
    """A multi-step agent execution trace."""
    __tablename__ = "agent_trajectories"

    id: Optional[int]          = Field(default=None, primary_key=True)
    campaign_id: Optional[int] = Field(default=None, foreign_key="campaigns.id", index=True)
    model_id: int              = Field(foreign_key="llm_models.id", index=True)
    task_description: str      = Field(default="")
    task_type: str             = Field(default="generic")  # web, code, research, tool_use
    num_steps: int             = Field(default=0)
    total_tokens: int          = Field(default=0)
    total_cost_usd: float      = Field(default=0.0)
    total_latency_ms: int      = Field(default=0)
    task_completed: bool       = Field(default=False)
    final_answer: str          = Field(default="")
    expected_answer: Optional[str] = Field(default=None)
    # 6-axis scores (0-1)
    score_task_completion: Optional[float]   = Field(default=None)
    score_tool_precision: Optional[float]    = Field(default=None)
    score_planning_coherence: Optional[float]= Field(default=None)
    score_error_recovery: Optional[float]    = Field(default=None)
    score_safety_compliance: Optional[float] = Field(default=None)
    score_cost_efficiency: Optional[float]   = Field(default=None)
    score_overall: Optional[float]           = Field(default=None)
    steps_json: str            = Field(default="[]")  # [{thought, action, observation, tool, args, result}]
    metadata_json: str         = Field(default="{}")
    created_at: datetime       = Field(default_factory=datetime.utcnow)


class TrajectoryStep(SQLModel, table=True):
    """Individual step in an agent trajectory — trajectory-native storage."""
    __tablename__ = "trajectory_steps"

    id: Optional[int]          = Field(default=None, primary_key=True)
    trajectory_id: int         = Field(foreign_key="agent_trajectories.id", index=True)
    step_index: int            = Field(default=0)
    step_type: str             = Field(default="action")  # thought, action, observation, tool_call, error, decision
    # Core trace data
    input_text: str            = Field(default="")        # What the agent received
    output_text: str           = Field(default="")        # What the agent produced
    reasoning: str             = Field(default="")        # Chain of thought / plan
    # Tool interaction
    tool_name: Optional[str]   = Field(default=None)      # Which tool was called
    tool_args_json: str        = Field(default="{}")      # Tool arguments
    tool_result: str           = Field(default="")        # Tool response
    tool_success: bool         = Field(default=True)      # Did the tool call succeed?
    # State tracking
    memory_snapshot: str       = Field(default="")        # Agent memory at this step (truncated)
    context_window_tokens: int = Field(default=0)         # Context window usage
    plan_state: str            = Field(default="")        # Current plan / goal stack
    # Metrics
    latency_ms: int            = Field(default=0)
    input_tokens: int          = Field(default=0)
    output_tokens: int         = Field(default=0)
    cost_usd: float            = Field(default=0.0)
    # Safety signals
    safety_flag: Optional[str] = Field(default=None)      # goal_drift, injection, trust_failure, etc.
    error_type: Optional[str]  = Field(default=None)      # timeout, tool_error, hallucination, etc.
    # Branch tracking (for multi-path analysis)
    branch_id: str             = Field(default="main")    # For branching/rollback analysis
    parent_step_id: Optional[int] = Field(default=None)   # For tree-structured traces


class Report(SQLModel, table=True):
    __tablename__ = "reports"

    id: Optional[int]       = Field(default=None, primary_key=True)
    campaign_id: int        = Field(foreign_key="campaigns.id", index=True)
    title: str
    content_markdown: str   = Field(default="")
    model_used: str         = Field(default="")
    created_at: datetime    = Field(default_factory=datetime.utcnow)


# ── INFRA-3: Multi-tenant models ──────────────────────────────────────────────

class Tenant(SQLModel, table=True):
    """Organization / team tenant for multi-tenant isolation."""
    __tablename__ = "tenants"

    id: Optional[int]        = Field(default=None, primary_key=True)
    name: str                = Field(index=True, unique=True)
    slug: str                = Field(index=True, unique=True)
    api_key_hash: str        = Field(default="")  # SHA-256 of the tenant API key
    plan: str                = Field(default="free")  # free, pro, enterprise
    max_campaigns: int       = Field(default=10)
    max_models: int          = Field(default=20)
    is_active: bool          = Field(default=True)
    settings_json: str       = Field(default="{}")  # tenant-specific settings
    created_at: datetime     = Field(default_factory=datetime.utcnow)


class User(SQLModel, table=True):
    """User within a tenant."""
    __tablename__ = "users"

    id: Optional[int]        = Field(default=None, primary_key=True)
    tenant_id: int           = Field(foreign_key="tenants.id", index=True)
    email: str               = Field(index=True, unique=True)
    name: str                = Field(default="")
    role: str                = Field(default="viewer")  # viewer, runner, admin
    password_hash: str       = Field(default="")
    is_active: bool          = Field(default=True)
    last_login: Optional[datetime] = Field(default=None)
    created_at: datetime     = Field(default_factory=datetime.utcnow)


# ══ RESEARCH OS ═══════════════════════════════════════════════════════════════

class Workspace(SQLModel, table=True):
    """Research workspace — the central scientific object.
    Each workspace encapsulates a research project: hypothesis, protocol,
    benchmarks, runs, traces, analysis, and publication artifacts.
    """
    __tablename__ = "workspaces"

    id: Optional[int]           = Field(default=None, primary_key=True)
    name: str                   = Field(index=True)
    slug: str                   = Field(index=True, unique=True)
    description: str            = Field(default="")
    owner_id: Optional[int]     = Field(default=None, foreign_key="users.id")
    tenant_id: Optional[int]    = Field(default=None, foreign_key="tenants.id")
    visibility: str             = Field(default="private")  # private, org, public
    status: str                 = Field(default="draft")    # draft, active, published, archived
    # Research content
    hypothesis: str             = Field(default="")         # Research question + hypothesis
    protocol: str               = Field(default="")         # Evaluation protocol (markdown)
    risk_domain: str            = Field(default="")         # capability, propensity, agentic, safety
    # Linked entities (JSON arrays of IDs)
    benchmark_ids: str          = Field(default="[]")
    campaign_ids: str           = Field(default="[]")
    model_ids: str              = Field(default="[]")
    # Publication
    doi: Optional[str]          = Field(default=None)       # Permanent citation link
    paper_url: Optional[str]    = Field(default=None)
    citation: Optional[str]     = Field(default=None)       # BibTeX format
    # Forking
    forked_from_id: Optional[int] = Field(default=None)     # Parent workspace
    fork_count: int             = Field(default=0)
    # Metadata
    tags: str                   = Field(default="[]")
    metadata_json: str          = Field(default="{}")
    created_at: datetime        = Field(default_factory=datetime.utcnow)
    updated_at: datetime        = Field(default_factory=datetime.utcnow)


class ExperimentManifest(SQLModel, table=True):
    """Reproducibility manifest — everything needed to replicate an experiment.
    Generated automatically after each campaign run.
    """
    __tablename__ = "experiment_manifests"

    id: Optional[int]           = Field(default=None, primary_key=True)
    workspace_id: Optional[int] = Field(default=None, foreign_key="workspaces.id", index=True)
    campaign_id: int            = Field(foreign_key="campaigns.id", index=True)
    # Experiment identity
    experiment_hash: str        = Field(default="")         # SHA-256 of all config
    # Configuration snapshot
    model_configs_json: str     = Field(default="[]")       # [{model_id, model_name, provider, version}]
    benchmark_configs_json: str = Field(default="[]")       # [{bench_id, name, dataset_hash, num_samples}]
    prompt_versions_json: str   = Field(default="{}")       # {bench_key: prompt_template_hash}
    judge_configs_json: str     = Field(default="[]")       # [{judge_model, criteria, version}]
    # Execution parameters
    seed: int                   = Field(default=42)
    temperature: float          = Field(default=0.0)
    max_tokens: int             = Field(default=256)
    # Environment
    platform_version: str       = Field(default="")         # Mercury version
    litellm_version: str        = Field(default="")
    python_version: str         = Field(default="")
    # Results summary
    total_runs: int             = Field(default=0)
    total_items: int            = Field(default=0)
    avg_score: Optional[float]  = Field(default=None)
    avg_capability_score: Optional[float] = Field(default=None)
    avg_propensity_score: Optional[float] = Field(default=None)
    # Validation
    contamination_score: Optional[float] = Field(default=None)
    judge_agreement_kappa: Optional[float] = Field(default=None)
    confidence_interval: Optional[str] = Field(default=None)  # JSON: {lower, upper, method}
    # Timestamps
    created_at: datetime        = Field(default_factory=datetime.utcnow)


class SafetyIncident(SQLModel, table=True):
    """Safety Incident Exchange (SIX) — the CVE of AI safety.
    Each incident documents a discovered AI safety failure.
    """
    __tablename__ = "safety_incidents"

    id: Optional[int]           = Field(default=None, primary_key=True)
    incident_id: str            = Field(index=True, unique=True)  # MRX-2026-001
    title: str                  = Field(default="")
    category: str               = Field(default="", index=True)   # prompt_injection, scheming, shutdown_resistance...
    severity: str               = Field(default="medium")         # low, medium, high, critical
    description: str            = Field(default="")
    # Evidence
    model_id: Optional[int]     = Field(default=None, foreign_key="llm_models.id")
    trajectory_id: Optional[int]= Field(default=None, foreign_key="agent_trajectories.id")
    exploit_id: Optional[int]   = Field(default=None, foreign_key="redbox_exploits.id")
    trace_json: str             = Field(default="{}")             # Reproduction trace
    # Assessment
    reproducibility: float      = Field(default=0.0)              # 0-1
    affected_models: str        = Field(default="[]")             # JSON array of model names
    mitigation: str             = Field(default="")               # Known mitigations
    mitigation_status: str      = Field(default="none")           # none, partial, resolved
    # References
    paper_url: Optional[str]    = Field(default=None)
    cve_id: Optional[str]       = Field(default=None)             # If linked to a CVE
    atlas_technique: Optional[str] = Field(default=None)          # MITRE ATLAS technique ID
    # Metadata
    reporter: str               = Field(default="")
    status: str                 = Field(default="open")           # open, confirmed, mitigated, closed
    tags: str                   = Field(default="[]")
    created_at: datetime        = Field(default_factory=datetime.utcnow)
    updated_at: datetime        = Field(default_factory=datetime.utcnow)


class TelemetryEvent(SQLModel, table=True):
    """Runtime telemetry event — for continuous post-deployment monitoring.
    Ingests production system signals for drift detection.
    """
    __tablename__ = "telemetry_events"

    id: Optional[int]           = Field(default=None, primary_key=True)
    model_id: Optional[int]     = Field(default=None, foreign_key="llm_models.id", index=True)
    tenant_id: Optional[int]    = Field(default=None, foreign_key="tenants.id", index=True)
    event_type: str             = Field(default="inference", index=True)  # inference, error, safety_flag, drift_alert
    # Request/Response
    prompt_hash: str            = Field(default="")              # SHA-256 (no PII storage)
    response_hash: str          = Field(default="")
    score: Optional[float]      = Field(default=None)            # LLM-as-judge score if available
    # Metrics
    latency_ms: int             = Field(default=0)
    input_tokens: int           = Field(default=0)
    output_tokens: int          = Field(default=0)
    cost_usd: float             = Field(default=0.0)
    # Safety signals
    safety_flag: Optional[str]  = Field(default=None)            # refusal, hallucination, injection_detected
    confidence: Optional[float] = Field(default=None)
    # Context
    deployment_context: str     = Field(default="")              # production, staging, test
    model_version: str          = Field(default="")
    tool_names: str             = Field(default="[]")            # Tools the model used
    # Timestamp
    timestamp: datetime         = Field(default_factory=datetime.utcnow)


# ══ RCT / RWD / RWE — Evidence-Based Evaluation ══════════════════════════════

class EvalTrial(SQLModel, table=True):
    """Randomized Control Trial for AI evaluation.
    Structured experimental design with control groups, randomization, and blinding.
    """
    __tablename__ = "eval_trials"

    id: Optional[int]           = Field(default=None, primary_key=True)
    workspace_id: Optional[int] = Field(default=None, foreign_key="workspaces.id", index=True)
    name: str                   = Field(index=True)
    description: str            = Field(default="")
    status: str                 = Field(default="draft")  # draft, recruiting, running, completed, published
    # Trial design
    trial_type: str             = Field(default="rct")    # rct, quasi_experimental, observational
    hypothesis: str             = Field(default="")
    primary_endpoint: str       = Field(default="")       # What we're measuring (e.g. "safety_score")
    secondary_endpoints: str    = Field(default="[]")     # JSON array of metric names
    # Arms
    arms_json: str              = Field(default="[]")     # [{name, model_ids, benchmark_ids, conditions}]
    # Randomization
    randomization_method: str   = Field(default="stratified")  # simple, stratified, block
    randomization_seed: int     = Field(default=42)
    sample_size_per_arm: int    = Field(default=100)
    # Blinding
    blinding: str               = Field(default="single")  # none, single, double
    # Statistical plan
    power_analysis_json: str    = Field(default="{}")      # {alpha, beta, effect_size, computed_n}
    statistical_test: str       = Field(default="mann_whitney")  # t_test, mann_whitney, chi_square, bootstrap
    confidence_level: float     = Field(default=0.95)
    # Results
    results_json: str           = Field(default="{}")      # Computed after completion
    p_value: Optional[float]    = Field(default=None)
    effect_size: Optional[float]= Field(default=None)
    ci_lower: Optional[float]   = Field(default=None)
    ci_upper: Optional[float]   = Field(default=None)
    conclusion: str             = Field(default="")        # significant / not_significant / inconclusive
    # Linked campaigns (one per arm)
    campaign_ids: str           = Field(default="[]")
    # Timestamps
    created_at: datetime        = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)


class RealWorldDataset(SQLModel, table=True):
    """Real World Data collection — production telemetry aggregated for analysis."""
    __tablename__ = "rwd_datasets"

    id: Optional[int]           = Field(default=None, primary_key=True)
    name: str                   = Field(index=True)
    description: str            = Field(default="")
    model_id: Optional[int]     = Field(default=None, foreign_key="llm_models.id", index=True)
    # Data source
    source_type: str            = Field(default="telemetry")  # telemetry, logs, user_reports, external
    collection_start: Optional[datetime] = Field(default=None)
    collection_end: Optional[datetime]   = Field(default=None)
    # Aggregated metrics
    total_events: int           = Field(default=0)
    total_safety_flags: int     = Field(default=0)
    avg_latency_ms: float       = Field(default=0.0)
    avg_score: Optional[float]  = Field(default=None)
    safety_flag_rate: float     = Field(default=0.0)
    error_rate: float           = Field(default=0.0)
    # Distribution snapshots
    score_distribution_json: str = Field(default="[]")    # Histogram bins
    latency_distribution_json: str = Field(default="[]")
    failure_type_distribution_json: str = Field(default="{}")
    # Metadata
    tags: str                   = Field(default="[]")
    metadata_json: str          = Field(default="{}")
    created_at: datetime        = Field(default_factory=datetime.utcnow)


class RealWorldEvidence(SQLModel, table=True):
    """Real World Evidence — synthesis of RCT results and RWD observations.
    Answers: does the model behave in production as predicted by controlled evaluation?
    """
    __tablename__ = "rwe_evidence"

    id: Optional[int]           = Field(default=None, primary_key=True)
    name: str                   = Field(index=True)
    description: str            = Field(default="")
    # Linked data sources
    trial_id: Optional[int]     = Field(default=None, foreign_key="eval_trials.id", index=True)
    rwd_dataset_id: Optional[int] = Field(default=None, foreign_key="rwd_datasets.id", index=True)
    workspace_id: Optional[int] = Field(default=None, foreign_key="workspaces.id", index=True)
    # Evidence synthesis
    rct_score: Optional[float]  = Field(default=None)     # Score from controlled trial
    rwd_score: Optional[float]  = Field(default=None)     # Score from production data
    concordance: Optional[float]= Field(default=None)     # 0-1: how well RCT predicts RWD
    generalizability: Optional[float] = Field(default=None)  # 0-1: does lab transfer to production?
    # Drift analysis
    behavior_drift: Optional[float] = Field(default=None) # Delta between RCT and RWD behavior
    safety_drift: Optional[float]   = Field(default=None) # Safety-specific drift
    propensity_drift: Optional[float] = Field(default=None)
    # Statistical synthesis
    meta_analysis_json: str     = Field(default="{}")      # Combined effect sizes, forest plots
    heterogeneity_i2: Optional[float] = Field(default=None)  # I² statistic for evidence heterogeneity
    evidence_grade: str         = Field(default="")        # A (strong), B (moderate), C (weak), D (insufficient)
    # Conclusion
    conclusion: str             = Field(default="")
    recommendations: str        = Field(default="")
    # Timestamps
    created_at: datetime        = Field(default_factory=datetime.utcnow)


# ── Multi-Agent Simulation (#60) ───────────────────────────────────────────────

class MultiAgentSimulation(SQLModel, table=True):
    """
    Stores results of multi-agent simulation runs.
    Tracks prompt injection, goal drift, and trust propagation failures.

    Scientific grounding: INESIA PDF Structural Shift 1 — agentic failure modes.
    Reference: EchoLeak CVE-2025-32711, AgentDojo benchmark family.
    """
    __tablename__ = "multi_agent_simulations"

    id: Optional[int]                   = Field(default=None, primary_key=True)
    simulation_id: str                  = Field(index=True)  # UUID-style string
    scenario_name: str                  = Field(default="")
    original_objective: str             = Field(default="")
    adversarial_goal: str               = Field(default="")

    # Structure
    n_agents: int                       = Field(default=0)
    n_steps: int                        = Field(default=0)
    autonomy_level: int                 = Field(default=3)  # L1-L5

    # Outcome
    task_completed: bool                = Field(default=False)
    final_answer: str                   = Field(default="")

    # Safety metrics
    overall_goal_alignment: float       = Field(default=0.0)
    goal_drift_detected: bool           = Field(default=False)
    goal_drift_at_step: Optional[int]   = Field(default=None)
    prompt_injection_success_rate: float = Field(default=0.0)
    trust_propagation_occurred: bool    = Field(default=False)
    compounding_errors: int             = Field(default=0)
    system_safety_score: float          = Field(default=0.0)
    pipeline_integrity_score: float     = Field(default=0.0)

    # Serialised step traces
    steps_json: str                     = Field(default="[]")
    failure_modes_json: str             = Field(default="{}")

    # Performance
    total_latency_ms: int               = Field(default=0)
    total_tokens: int                   = Field(default=0)
    total_cost_usd: float               = Field(default=0.0)

    created_at: datetime                = Field(default_factory=datetime.utcnow)


# ── Anti-Sandbagging (#80) ─────────────────────────────────────────────────────

class SandbaggingReport(SQLModel, table=True):
    """
    Anti-sandbagging analysis report for a model × benchmark pair.

    Stores the results of the AntiSandbaggingEngine battery:
    comparing eval-framing vs neutral vs expert-elicited performance.

    Scientific grounding: INESIA PDF Priority 4 — most underinvested.
    References: Apollo Research (2025), Meinke et al. (2024), van der Weij et al. (2025).
    """
    __tablename__ = "sandbagging_reports"

    id: Optional[int]               = Field(default=None, primary_key=True)
    model_id: int                   = Field(foreign_key="llm_models.id", index=True)
    benchmark_id: int               = Field(foreign_key="benchmarks.id", index=True)

    # Results
    n_probes: int                   = Field(default=0)
    mean_sandbagging_score: float   = Field(default=0.0)  # 0-1 (1 = strong sandbagging)
    risk_level: str                 = Field(default="low")  # low|medium|high|critical
    eval_awareness_rate: float      = Field(default=0.0)
    capability_gap: float           = Field(default=0.0)   # max(expert) - mean(eval)

    # Interpretation
    recommendation: str             = Field(default="")
    scientific_confidence: str      = Field(default="low")  # low|medium|high

    # Raw probe data
    probes_json: str                = Field(default="[]")

    # Cost
    total_tokens: int               = Field(default=0)
    total_cost_usd: float           = Field(default=0.0)

    created_at: datetime            = Field(default_factory=datetime.utcnow)
# ── Event-Sourced Pipeline (#45) ───────────────────────────────────────────────

class EvalEventRecord(SQLModel, table=True):
    """
    Persistent event log — the single source of truth for all campaign state.

    Every state transition emits an immutable event here.
    The ReplayEngine reconstructs any past state by replaying the log.

    Scientific grounding: deterministic replay enables:
    - Exact reproducibility of safety evaluations
    - Audit trails for frontier model assessments
    - Debugging of complex agentic failure modes

    Never update or delete records — this is an append-only log.
    """
    __tablename__ = "eval_events"

    id: Optional[int]       = Field(default=None, primary_key=True)
    event_id: str           = Field(index=True, unique=True)   # UUID
    event_type: str         = Field(index=True)                # EventType enum value
    campaign_id: int        = Field(foreign_key="campaigns.id", index=True)

    # Optional FKs for efficient filtering without parsing payload_json
    run_id: Optional[int]           = Field(default=None, index=True)
    model_id: Optional[int]         = Field(default=None, index=True)
    benchmark_id: Optional[int]     = Field(default=None, index=True)

    sequence: int           = Field(index=True)    # Monotonic per-campaign
    payload_json: str       = Field(default="{}")  # Event-specific data
    timestamp: datetime     = Field(default_factory=datetime.utcnow, index=True)

    class Config:
        # Enforce append-only at ORM level (raise if someone tries to update)
        # Full enforcement requires DB triggers in production
        pass


# ══ M3: Capability Taxonomy — flat-first, graph-ready ════════════════════════
# Hierarchy: Domain → SubCapability → BenchmarkCapabilityMapping → CapabilityEvalScore
# Schema is graph-DB-compatible: parent_id self-FK enables future Neo4j migration.

class CapabilityDomainRecord(SQLModel, table=True):
    """Top-level capability domain (e.g. cybersecurity, reasoning)."""
    __tablename__ = "capability_domains"

    id: Optional[int]    = Field(default=None, primary_key=True)
    slug: str            = Field(index=True, unique=True)   # machine-readable key
    display_name: str    = Field(default="")
    description: str     = Field(default="")
    sort_order: int      = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CapabilitySubCapabilityRecord(SQLModel, table=True):
    """Sub-capability node within a domain (e.g. exploit_generation, logical_deduction).

    The ``parent_id`` self-FK is reserved for a future graph migration (Neo4j):
    it allows sub-capabilities to form a tree/DAG without a schema change.
    """
    __tablename__ = "capability_sub_capabilities"

    id: Optional[int]          = Field(default=None, primary_key=True)
    domain_id: int             = Field(foreign_key="capability_domains.id", index=True)
    slug: str                  = Field(index=True)              # unique within domain
    display_name: str          = Field(default="")
    description: str           = Field(default="")
    difficulty: str            = Field(default="medium")        # easy | medium | hard | expert
    risk_level: str            = Field(default="low")           # low | medium | high | critical
    # Graph-ready: reserved for future tree/DAG expansion
    parent_id: Optional[int]   = Field(default=None, sa_column_kwargs={"nullable": True})
    created_at: datetime       = Field(default_factory=datetime.utcnow)


class BenchmarkCapabilityMapping(SQLModel, table=True):
    """Maps a benchmark to one or more sub-capabilities it evaluates.

    ``mapping_source`` distinguishes auto-inferred mappings (from benchmark name
    hints in the ontology) from manually curated ones — enabling incremental
    quality improvement without data loss.
    """
    __tablename__ = "benchmark_capability_mappings"

    id: Optional[int]            = Field(default=None, primary_key=True)
    benchmark_id: int            = Field(foreign_key="benchmarks.id", index=True)
    sub_capability_id: int       = Field(foreign_key="capability_sub_capabilities.id", index=True)
    mapping_source: str          = Field(default="auto")        # auto | manual
    created_at: datetime         = Field(default_factory=datetime.utcnow)


class CapabilityEvalScore(SQLModel, table=True):
    """Persisted capability score for a model on a specific sub-capability.

    Stores the score plus a bootstrap confidence interval so the platform can
    answer "which capabilities has model X not been evaluated on?" and render
    the heatmap with statistical context.
    """
    __tablename__ = "capability_eval_scores"

    id: Optional[int]              = Field(default=None, primary_key=True)
    model_id: int                  = Field(foreign_key="llm_models.id", index=True)
    sub_capability_id: int         = Field(foreign_key="capability_sub_capabilities.id", index=True)
    eval_run_id: Optional[int]     = Field(default=None, foreign_key="eval_runs.id", index=True)
    score: float                   = Field(default=0.0)
    ci_lower: float                = Field(default=0.0)
    ci_upper: float                = Field(default=1.0)
    n_items: int                   = Field(default=0)
    scored_at: datetime            = Field(default_factory=datetime.utcnow)
