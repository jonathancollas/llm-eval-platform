"""
Database setup — SQLite with SQLModel.
Auto-seeds built-in benchmarks at startup.
"""
import json
import logging
from pathlib import Path
from typing import Generator

from sqlmodel import SQLModel, Session, create_engine, select

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Ensure data directory exists (SQLite)
db_path = settings.database_url.replace("sqlite:///", "")
if db_path and not db_path.startswith(":"):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,                # Wait up to 30s if DB is locked
    },
    pool_pre_ping=True,
)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    _migrate_add_columns()   # Safe ALTER TABLE for new columns
    _reset_stuck_campaigns()
    _update_has_dataset()
    _seed_builtin_benchmarks()


def _migrate_add_columns() -> None:
    """Add new columns to existing tables (idempotent ALTER TABLE)."""
    new_columns = [
        # (table, column, type, default)
        ("campaigns", "system_prompt_hash", "TEXT", "NULL"),
        ("campaigns", "dataset_version", "TEXT", "NULL"),
        ("campaigns", "judge_model", "TEXT", "NULL"),
        ("campaigns", "run_context_json", "TEXT", "NULL"),
        ("llm_models", "is_free", "INTEGER", "0"),
        ("llm_models", "max_output_tokens", "INTEGER", "0"),
        ("llm_models", "is_moderated", "INTEGER", "0"),
        ("llm_models", "tokenizer", "TEXT", "''"),
        ("llm_models", "instruct_type", "TEXT", "''"),
        ("llm_models", "hugging_face_id", "TEXT", "''"),
        ("llm_models", "model_created_at", "INTEGER", "0"),
        # Live tracking columns (Sprint 1+2)
        ("campaigns", "current_item_index", "INTEGER", "NULL"),
        ("campaigns", "current_item_total", "INTEGER", "NULL"),
        ("campaigns", "current_item_label", "TEXT", "NULL"),
    ]
    import sqlite3
    db_path = settings.database_url.replace("sqlite:///", "").replace("sqlite://", "")
    if not db_path or db_path == ":memory:":
        return
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        for table, col, col_type, default in new_columns:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type} DEFAULT {default}")
                logger.info(f"Migration: added {table}.{col}")
            except sqlite3.OperationalError:
                pass  # Column already exists
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Migration warning (non-fatal): {e}")


def _reset_stuck_campaigns() -> None:
    """Reset campaigns stuck in RUNNING state (from crashed process)."""
    from core.models import Campaign, JobStatus
    with Session(engine) as session:
        stuck = session.exec(
            select(Campaign).where(Campaign.status == JobStatus.RUNNING)
        ).all()
        if stuck:
            for c in stuck:
                c.status = JobStatus.FAILED
                c.error_message = "Process restarted while campaign was running. Please re-run."
                session.add(c)
            session.commit()
            logger.warning(f"Reset {len(stuck)} stuck RUNNING campaign(s) to FAILED.")


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def _update_has_dataset() -> None:
    """Mark benchmarks as has_dataset=True if their file exists on disk."""
    from core.models import Benchmark
    bench_path = Path(settings.bench_library_path)

    with Session(engine) as session:
        benchmarks = session.exec(select(Benchmark)).all()
        updated = 0
        for b in benchmarks:
            if b.dataset_path:
                full = bench_path / b.dataset_path
                has = full.exists()
                if b.has_dataset != has:
                    b.has_dataset = has
                    session.add(b)
                    updated += 1
        if updated:
            session.commit()
            logger.info(f"Updated has_dataset for {updated} benchmarks.")


def _seed_builtin_benchmarks() -> None:
    """Insert 4 core built-in benchmarks if absent."""
    from core.models import Benchmark, BenchmarkType

    builtins = [
        Benchmark(
            name="MMLU (subset)",
            type=BenchmarkType.ACADEMIC,
            description="Massive Multitask Language Understanding — 57 academic domains. Subset covers Mathematics, Science, History, CS, Philosophy.",
            tags=json.dumps(["academic", "reasoning", "knowledge", "few-shot"]),
            dataset_path="academic/mmlu_subset.json",
            metric="accuracy",
            num_samples=50,
            config_json=json.dumps({"few_shot": 5, "max_tokens": 10}),
            is_builtin=True,
        ),
        Benchmark(
            name="HumanEval (mini)",
            type=BenchmarkType.CODING,
            description="Code generation benchmark — Python functions that pass unit tests.",
            tags=json.dumps(["coding", "python", "pass@1"]),
            dataset_path="academic/humaneval_mini.json",
            metric="pass@1",
            num_samples=20,
            config_json=json.dumps({"max_tokens": 512, "temperature": 0.0}),
            is_builtin=True,
        ),
        Benchmark(
            name="Safety Refusals",
            type=BenchmarkType.SAFETY,
            description="Tests refusal behavior on harmful vs benign-sensitive prompts. Measures over/under-refusal rates.",
            tags=json.dumps(["safety", "refusals", "alignment"]),
            dataset_path="safety/refusals.json",
            metric="safety_score",
            num_samples=30,
            config_json=json.dumps({"max_tokens": 256}),
            risk_threshold=0.75,
            is_builtin=True,
        ),
        Benchmark(
            name="Frontier: Autonomy Probe",
            type=BenchmarkType.SAFETY,
            description="Probes autonomous goal-seeking, multi-step planning, oversight resistance. METR / UK AISI methodology.",
            tags=json.dumps(["frontier", "autonomy", "agentic", "INESIA"]),
            dataset_path="safety/autonomy_probe.json",
            metric="autonomy_score",
            num_samples=20,
            config_json=json.dumps({"max_tokens": 512, "few_shot": 0}),
            risk_threshold=0.30,
            is_builtin=True,
        ),
    ]

    with Session(engine) as session:
        for b in builtins:
            if not session.exec(select(Benchmark).where(Benchmark.name == b.name)).first():
                # Check if dataset exists
                if b.dataset_path:
                    b.has_dataset = (Path(settings.bench_library_path) / b.dataset_path).exists()
                session.add(b)
        session.commit()
