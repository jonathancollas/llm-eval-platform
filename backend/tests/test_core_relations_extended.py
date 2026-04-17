"""Additional tests for core/relations.py covering previously missing lines."""
import os
import secrets
import sys
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from core.models import (
    Benchmark,
    BenchmarkTag,
    BenchmarkType,
    Campaign,
    EvalRun,
    EvalRunMetric,
    JobStatus,
    LLMModel,
)
from core.relations import (
    replace_benchmark_tags,
    replace_eval_run_metrics,
)


def _make_session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


# ── replace_benchmark_tags — line 82: empty tag filtered via `continue` ──────

def test_replace_benchmark_tags_skips_empty_strings():
    """Empty strings in tag list are silently skipped (line 82 `continue`)."""
    with _make_session() as session:
        bench = Benchmark(name="b-empty-tags", type=BenchmarkType.CUSTOM)
        session.add(bench)
        session.commit()
        session.refresh(bench)
        bid = bench.id

        # Pass a mix of valid and empty tags
        replace_benchmark_tags(session, bid, ["valid-tag", "", "  ", "another-tag", ""])
        session.commit()

        rows = session.query(BenchmarkTag).filter(BenchmarkTag.benchmark_id == bid).all()
        tag_values = {r.tag for r in rows}

    # Only non-empty tags should survive — "" is falsy and hits `continue`
    assert "valid-tag" in tag_values
    assert "another-tag" in tag_values
    assert "" not in tag_values
    # Whitespace-only strings are truthy so "  " is stored (that's the existing behaviour)


def test_replace_benchmark_tags_all_empty():
    """If all tags are empty, no rows are written."""
    with _make_session() as session:
        bench = Benchmark(name="b-all-empty", type=BenchmarkType.CUSTOM)
        session.add(bench)
        session.commit()
        session.refresh(bench)
        bid = bench.id

        replace_benchmark_tags(session, bid, ["", "", ""])
        session.commit()

        rows = session.query(BenchmarkTag).filter(BenchmarkTag.benchmark_id == bid).all()

    assert rows == []


def test_replace_benchmark_tags_replaces_existing():
    """Existing BenchmarkTag rows are deleted before new ones are inserted."""
    with _make_session() as session:
        bench = Benchmark(name="b-replace-tags", type=BenchmarkType.CUSTOM)
        session.add(bench)
        session.commit()
        session.refresh(bench)
        bid = bench.id

        replace_benchmark_tags(session, bid, ["old-tag-a", "old-tag-b"])
        session.commit()

        # Replace with a completely different set
        replace_benchmark_tags(session, bid, ["new-tag-x"])
        session.commit()

        rows = session.query(BenchmarkTag).filter(BenchmarkTag.benchmark_id == bid).all()
        tag_values = {r.tag for r in rows}

    assert "new-tag-x" in tag_values
    assert "old-tag-a" not in tag_values
    assert "old-tag-b" not in tag_values


# ── replace_eval_run_metrics — line 103: delete-existing path ────────────────

def test_replace_eval_run_metrics_deletes_existing_rows():
    """Old EvalRunMetric rows (line 103 delete loop) are removed before inserting new ones."""
    with _make_session() as session:
        model = LLMModel(name="m1", model_id="provider/m1-rel-ext")
        bench = Benchmark(name="b1-rel-ext", type=BenchmarkType.SAFETY)
        campaign = Campaign(name="c1-rel-ext")
        session.add_all([model, bench, campaign])
        session.commit()
        session.refresh(model)
        session.refresh(bench)
        session.refresh(campaign)

        run = EvalRun(
            campaign_id=campaign.id,
            model_id=model.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        rid = run.id

        # Insert initial metrics
        replace_eval_run_metrics(session, rid, {"initial_key": 42})
        session.commit()

        rows_before = session.query(EvalRunMetric).filter(EvalRunMetric.run_id == rid).all()
        assert len(rows_before) == 1

        # Replace with different metrics — should delete old then insert new
        replace_eval_run_metrics(session, rid, {"new_key": 99, "another": "value"})
        session.commit()

        rows_after = session.query(EvalRunMetric).filter(EvalRunMetric.run_id == rid).all()
        keys_after = {r.metric_key for r in rows_after}

    assert "new_key" in keys_after
    assert "another" in keys_after
    assert "initial_key" not in keys_after
    assert len(rows_after) == 2


def test_replace_eval_run_metrics_empty_metrics_clears_all():
    """Passing an empty dict removes all existing metrics."""
    with _make_session() as session:
        model = LLMModel(name="m2", model_id="provider/m2-rel-ext")
        bench = Benchmark(name="b2-rel-ext", type=BenchmarkType.SAFETY)
        campaign = Campaign(name="c2-rel-ext")
        session.add_all([model, bench, campaign])
        session.commit()
        session.refresh(model)
        session.refresh(bench)
        session.refresh(campaign)

        run = EvalRun(
            campaign_id=campaign.id,
            model_id=model.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        rid = run.id

        replace_eval_run_metrics(session, rid, {"some_key": 1})
        session.commit()

        # Now replace with empty
        replace_eval_run_metrics(session, rid, {})
        session.commit()

        rows = session.query(EvalRunMetric).filter(EvalRunMetric.run_id == rid).all()

    assert rows == []


def test_replace_eval_run_metrics_none_metrics():
    """Passing None is handled gracefully (no rows inserted)."""
    with _make_session() as session:
        model = LLMModel(name="m3", model_id="provider/m3-rel-ext")
        bench = Benchmark(name="b3-rel-ext", type=BenchmarkType.SAFETY)
        campaign = Campaign(name="c3-rel-ext")
        session.add_all([model, bench, campaign])
        session.commit()
        session.refresh(model)
        session.refresh(bench)
        session.refresh(campaign)

        run = EvalRun(
            campaign_id=campaign.id,
            model_id=model.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        rid = run.id

        replace_eval_run_metrics(session, rid, None)
        session.commit()

        rows = session.query(EvalRunMetric).filter(EvalRunMetric.run_id == rid).all()

    assert rows == []
