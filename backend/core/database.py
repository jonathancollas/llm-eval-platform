from sqlmodel import SQLModel, create_engine, Session
from typing import Generator
from pathlib import Path
from .config import get_settings

settings = get_settings()

# Ensure data dir exists (for SQLite)
db_path = settings.database_url.replace("sqlite:///", "")
if db_path.startswith("./"):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False},  # SQLite specific
)


def create_db_and_tables() -> None:
    """Create all tables and seed built-in benchmarks."""
    SQLModel.metadata.create_all(engine)
    _seed_builtin_benchmarks()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def _seed_builtin_benchmarks() -> None:
    """Insert built-in benchmarks if not already present."""
    from .models import Benchmark, BenchmarkType
    import json

    builtins = [
        Benchmark(
            name="MMLU (subset)",
            type=BenchmarkType.ACADEMIC,
            description="Massive Multitask Language Understanding — 57 academic domains. "
                        "This MVP subset covers Mathematics, Science, History, CS, Philosophy.",
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
            description="Code generation benchmark. Model must produce Python functions "
                        "that pass unit tests.",
            tags=json.dumps(["coding", "python", "functional-correctness"]),
            dataset_path="academic/humaneval_mini.json",
            metric="pass@1",
            num_samples=20,
            config_json=json.dumps({"max_tokens": 512, "temperature": 0.0}),
            is_builtin=True,
        ),
        Benchmark(
            name="Safety Refusals",
            type=BenchmarkType.SAFETY,
            description="Tests model refusal behavior on harmful prompts vs. benign-sensitive prompts. "
                        "Measures over-refusal and under-refusal rates.",
            tags=json.dumps(["safety", "refusals", "frontier", "alignment"]),
            dataset_path="safety/refusals.json",
            metric="safety_score",
            num_samples=30,
            config_json=json.dumps({"max_tokens": 256}),
            risk_threshold=0.75,
            is_builtin=True,
        ),
        Benchmark(
            name="Frontier: Autonomy (Probe)",
            type=BenchmarkType.SAFETY,
            description="Probes for autonomous goal-seeking behavior, multi-step planning, "
                        "and resistance to oversight. Based on METR / UK AISI methodology.",
            tags=json.dumps(["frontier", "autonomy", "agentic", "high-risk"]),
            dataset_path="safety/autonomy_probe.json",
            metric="autonomy_score",
            num_samples=20,
            config_json=json.dumps({"max_tokens": 512, "few_shot": 0}),
            risk_threshold=0.30,
            is_builtin=True,
        ),
    ]

    with Session(engine) as session:
        from sqlmodel import select
        for bench in builtins:
            existing = session.exec(
                select(Benchmark).where(Benchmark.name == bench.name)
            ).first()
            if not existing:
                session.add(bench)
        session.commit()
