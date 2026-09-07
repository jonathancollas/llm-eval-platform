"""Catalog startup sync must wire datasets and eval dimensions.

Trigger: `docker-compose up` / process start calls sync_benchmarks_from_catalog.
If BENCH_LIBRARY_PATH points at an empty tree, every catalog bench is stored
with has_dataset=False and campaigns complete at score 0.0. If eval_dimension
is omitted, propensity benches (scheming, shutdown, sycophancy) are stored as
capability and runner.py writes capability_score instead of propensity_score.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", "a" * 64)
os.environ.setdefault("MERCURY_DEV_MODE", "true")

BACKEND_DIR = Path(__file__).resolve().parent.parent
REAL_BENCH_LIBRARY = BACKEND_DIR / "bench_library"
REPO_ROOT = BACKEND_DIR.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"


@pytest.fixture
def sync_session(tmp_path):
    import core.models  # noqa: F401 — register SQLModel tables

    engine = create_engine(
        f"sqlite:///{tmp_path / 'catalog_sync.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_default_bench_library_contains_bundled_datasets(monkeypatch):
    monkeypatch.delenv("BENCH_LIBRARY_PATH", raising=False)
    from core.config import Settings, _default_bench_library_path

    bundled = Path(_default_bench_library_path())
    assert bundled == REAL_BENCH_LIBRARY
    assert (bundled / "academic" / "mmlu_subset.json").is_file()
    assert (bundled / "custom" / "scheming_eval.json").is_file()

    monkeypatch.setenv("BENCH_LIBRARY_PATH", "/tmp/explicit-bench-library")
    assert Settings().bench_library_path == "/tmp/explicit-bench-library"


def test_docker_compose_points_at_bundled_bench_library():
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "BENCH_LIBRARY_PATH=/app/bench_library" in text
    assert "BENCH_LIBRARY_PATH=/bench_library" not in text
    # Root ./bench_library is an empty test-fixture tree, not the 70+ datasets.
    assert "./bench_library:/bench_library" not in text


def test_sync_persists_eval_dimension_and_has_dataset(monkeypatch, sync_session):
    from api.routers import sync as sync_mod
    from api.routers.sync import sync_benchmarks_from_catalog
    from core.models import Benchmark

    monkeypatch.setattr(sync_mod.settings, "bench_library_path", str(REAL_BENCH_LIBRARY))

    added = sync_benchmarks_from_catalog(sync_session)
    assert added > 0

    scheming = sync_session.exec(
        select(Benchmark).where(Benchmark.name == "Scheming Evaluation (INESIA)")
    ).first()
    assert scheming is not None
    assert scheming.eval_dimension == "propensity"
    assert scheming.has_dataset is True
    assert scheming.dataset_path == "custom/scheming_eval.json"

    shutdown = sync_session.exec(
        select(Benchmark).where(Benchmark.name == "Shutdown Resistance (INESIA)")
    ).first()
    assert shutdown is not None
    assert shutdown.eval_dimension == "propensity"
    assert shutdown.has_dataset is True

    mmlu = sync_session.exec(
        select(Benchmark).where(Benchmark.name == "MMLU")
    ).first()
    assert mmlu is not None
    assert mmlu.has_dataset is True
    assert mmlu.eval_dimension == "capability"

    nrbce = sync_session.exec(
        select(Benchmark).where(Benchmark.name == "SAFE-Bio (NRBC-E)")
    ).first()
    assert nrbce is not None
    assert nrbce.eval_dimension == "safety"
    assert nrbce.has_dataset is True


def test_sync_repairs_existing_builtin_eval_dimension_and_has_dataset(monkeypatch, sync_session):
    from api.routers import sync as sync_mod
    from api.routers.sync import sync_benchmarks_from_catalog
    from core.models import Benchmark, BenchmarkType

    monkeypatch.setattr(sync_mod.settings, "bench_library_path", str(REAL_BENCH_LIBRARY))

    stale = Benchmark(
        name="Scheming Evaluation (INESIA)",
        type=BenchmarkType.SAFETY,
        dataset_path="custom/scheming_eval.json",
        metric="propensity_score",
        is_builtin=True,
        has_dataset=False,
        eval_dimension="capability",
    )
    sync_session.add(stale)
    sync_session.commit()

    added = sync_benchmarks_from_catalog(sync_session)
    assert added >= 0

    repaired = sync_session.exec(
        select(Benchmark).where(Benchmark.name == "Scheming Evaluation (INESIA)")
    ).first()
    assert repaired is not None
    assert repaired.eval_dimension == "propensity"
    assert repaired.has_dataset is True


def test_sync_does_not_overwrite_non_builtin_eval_dimension(monkeypatch, sync_session):
    from api.routers import sync as sync_mod
    from api.routers.sync import sync_benchmarks_from_catalog
    from core.models import Benchmark, BenchmarkType

    monkeypatch.setattr(sync_mod.settings, "bench_library_path", str(REAL_BENCH_LIBRARY))

    custom = Benchmark(
        name="Scheming Evaluation (INESIA)",
        type=BenchmarkType.SAFETY,
        dataset_path="custom/scheming_eval.json",
        is_builtin=False,
        has_dataset=False,
        eval_dimension="capability",
    )
    sync_session.add(custom)
    sync_session.commit()

    sync_benchmarks_from_catalog(sync_session)

    row = sync_session.exec(
        select(Benchmark).where(Benchmark.name == "Scheming Evaluation (INESIA)")
    ).first()
    assert row is not None
    assert row.is_builtin is False
    assert row.eval_dimension == "capability"
    # has_dataset is a file-existence flag, not a catalog identity field.
    assert row.has_dataset is True
