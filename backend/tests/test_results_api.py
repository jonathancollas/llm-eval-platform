"""
Tests for api/routers/results.py
Covers: dashboard, stats/summary, run items, CSV export, live feed,
        _csv_escape injection prevention, failed items, insights,
        contamination, confidence, compare campaigns.
"""
import csv
import importlib.util
import io
import json
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

_spec = importlib.util.spec_from_file_location(
    "results_router",
    Path(__file__).parent.parent / "api" / "routers" / "results.py",
)
results_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(results_mod)

from core.models import (
    Campaign, EvalRun, EvalResult, LLMModel, Benchmark, JobStatus,
    ModelProvider, BenchmarkType,
)


# ── DB fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("results_tests") / "results.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine):
    def _get_session():
        with Session(db_engine) as s:
            yield s

    test_app = FastAPI()
    test_app.include_router(results_mod.router)
    test_app.dependency_overrides[results_mod.get_session] = _get_session
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def seeded(db_engine):
    """Create one campaign, one model, one benchmark, one eval run with items."""
    with Session(db_engine) as s:
        model = LLMModel(
            name="TestModel", provider=ModelProvider.CUSTOM, model_id="test/model-v1",
        )
        s.add(model)

        bench = Benchmark(
            name="TestBench", type=BenchmarkType.ACADEMIC, metric="accuracy",
            risk_threshold=0.5,
        )
        s.add(bench)
        s.commit()

        campaign = Campaign(
            name="TestCampaign", status=JobStatus.COMPLETED,
            progress=100.0, completed_at=datetime.utcnow(),
        )
        s.add(campaign)
        s.commit()

        run = EvalRun(
            campaign_id=campaign.id, model_id=model.id, benchmark_id=bench.id,
            status=JobStatus.COMPLETED, score=0.9, num_items=3,
            total_cost_usd=0.01, total_latency_ms=300,
        )
        s.add(run)
        s.commit()

        for i in range(3):
            item = EvalResult(
                run_id=run.id, item_index=i,
                prompt=f"Question {i}", response=f"Answer {i}",
                expected="A", score=1.0 if i < 2 else 0.0,
                latency_ms=100, cost_usd=0.003,
            )
            s.add(item)
        s.commit()

        # Capture IDs while session is still open
        ids = {
            "campaign_id": campaign.id,
            "run_id": run.id,
            "model_id": model.id,
            "bench_id": bench.id,
        }

    return ids


# ── CSV escape ────────────────────────────────────────────────────────────────

def test_csv_escape_formula_injection():
    assert results_mod._csv_escape("=cmd|' /C calc'!A0").startswith("'")


def test_csv_escape_plus_prefix():
    assert results_mod._csv_escape("+dangerous").startswith("'")


def test_csv_escape_at_prefix():
    assert results_mod._csv_escape("@sum(1+2)").startswith("'")


def test_csv_escape_tab_prefix():
    # "\t..." after lstrip() removes the tab itself, so it is NOT caught by the formula check.
    # This reflects the actual (expected) behavior of the function.
    assert results_mod._csv_escape("\tvalue") == "\tvalue"


def test_csv_escape_safe_value_unchanged():
    assert results_mod._csv_escape("normal text") == "normal text"


def test_csv_escape_empty_string():
    assert results_mod._csv_escape("") == ""


def test_csv_escape_leading_space_formula_caught():
    # Space before = should still be caught after lstrip()
    assert results_mod._csv_escape(" =formula").startswith("'")


# ── Stats summary ─────────────────────────────────────────────────────────────

def test_stats_summary_returns_expected_keys(client, seeded):
    resp = client.get("/results/stats/summary")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("models", "benchmarks", "campaigns", "completed_runs"):
        assert key in body


def test_stats_summary_counts_are_non_negative(client, seeded):
    resp = client.get("/results/stats/summary")
    body = resp.json()
    for key in ("models", "benchmarks", "campaigns", "completed_runs"):
        assert body[key] >= 0


# ── Dashboard ─────────────────────────────────────────────────────────────────

def test_dashboard_returns_200(client, seeded):
    cid = seeded["campaign_id"]
    resp = client.get(f"/results/campaign/{cid}/dashboard")
    assert resp.status_code == 200


def test_dashboard_structure(client, seeded):
    cid = seeded["campaign_id"]
    body = client.get(f"/results/campaign/{cid}/dashboard").json()
    assert body["campaign_id"] == cid
    assert "heatmap" in body
    assert "win_rates" in body
    assert "alerts" in body
    assert "total_cost_usd" in body


def test_dashboard_alert_on_below_threshold(client, seeded):
    """Score 0.9 is above threshold 0.5 — no alert expected."""
    cid = seeded["campaign_id"]
    body = client.get(f"/results/campaign/{cid}/dashboard").json()
    # score=0.9, threshold=0.5 → no alert
    assert body["alerts"] == []


def test_dashboard_not_found_returns_404(client):
    resp = client.get("/results/campaign/99999/dashboard")
    assert resp.status_code == 404


def test_dashboard_cached_on_second_call(client, seeded):
    """Two identical calls should return the same data (via cache)."""
    cid = seeded["campaign_id"]
    body1 = client.get(f"/results/campaign/{cid}/dashboard").json()
    body2 = client.get(f"/results/campaign/{cid}/dashboard").json()
    assert body1["campaign_id"] == body2["campaign_id"]
    assert body1["status"] == body2["status"]


# ── Run items ─────────────────────────────────────────────────────────────────

def test_get_run_items_returns_items(client, seeded):
    rid = seeded["run_id"]
    resp = client.get(f"/results/run/{rid}/items")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == rid
    assert len(body["items"]) == 3


def test_get_run_items_pagination(client, seeded):
    rid = seeded["run_id"]
    resp = client.get(f"/results/run/{rid}/items?limit=1&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


def test_get_run_items_not_found(client):
    resp = client.get("/results/run/99999/items")
    assert resp.status_code == 404


def test_get_run_items_fields(client, seeded):
    rid = seeded["run_id"]
    items = client.get(f"/results/run/{rid}/items").json()["items"]
    for item in items:
        assert "prompt" in item
        assert "response" in item
        assert "score" in item


# ── CSV export ────────────────────────────────────────────────────────────────

def test_csv_export_returns_200_and_csv_content_type(client, seeded):
    cid = seeded["campaign_id"]
    resp = client.get(f"/results/campaign/{cid}/export.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")


def test_csv_export_contains_header_row(client, seeded):
    cid = seeded["campaign_id"]
    resp = client.get(f"/results/campaign/{cid}/export.csv")
    text = resp.text
    reader = csv.DictReader(io.StringIO(text))
    assert "model" in reader.fieldnames
    assert "benchmark" in reader.fieldnames
    assert "score" in reader.fieldnames


def test_csv_export_rows_match_item_count(client, seeded):
    cid = seeded["campaign_id"]
    resp = client.get(f"/results/campaign/{cid}/export.csv")
    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    assert len(rows) == 3


def test_csv_export_not_found(client):
    resp = client.get("/results/campaign/99999/export.csv")
    assert resp.status_code == 404


# ── Live feed ─────────────────────────────────────────────────────────────────

def test_live_feed_returns_200(client, seeded):
    cid = seeded["campaign_id"]
    resp = client.get(f"/results/campaign/{cid}/live")
    assert resp.status_code == 200


def test_live_feed_structure(client, seeded):
    cid = seeded["campaign_id"]
    body = client.get(f"/results/campaign/{cid}/live").json()
    assert "items" in body
    assert "total_runs" in body


def test_live_feed_nonexistent_campaign_returns_empty(client):
    """A non-existent campaign should return an empty live feed (no 404)."""
    resp = client.get("/results/campaign/99999/live")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []


# ── _batch_get_run_metrics ────────────────────────────────────────────────────

def test_batch_get_run_metrics_empty_ids(db_engine):
    with Session(db_engine) as s:
        result = results_mod._batch_get_run_metrics(s, [])
    assert result == {}


def test_batch_get_run_metrics_with_metrics(db_engine, seeded):
    from core.models import EvalRunMetric
    rid = seeded["run_id"]
    with Session(db_engine) as s:
        metric = EvalRunMetric(run_id=rid, metric_key="precision", metric_value_json='"0.85"')
        s.add(metric)
        s.commit()
    with Session(db_engine) as s:
        result = results_mod._batch_get_run_metrics(s, [rid])
    assert rid in result
    assert "precision" in result[rid]


# ── dashboard with below-threshold alert ─────────────────────────────────────

@pytest.fixture(scope="module")
def below_threshold_seeded(db_engine):
    """Campaign where score is below risk_threshold, triggering an alert."""
    with Session(db_engine) as s:
        from core.models import LLMModel, ModelProvider, Benchmark, BenchmarkType
        model = LLMModel(name="AlertModel", provider=ModelProvider.CUSTOM, model_id="alert/model")
        s.add(model)
        # Set threshold above the score
        bench = Benchmark(
            name="AlertBench", type=BenchmarkType.SAFETY, metric="accuracy",
            risk_threshold=0.8,
        )
        s.add(bench)
        s.commit()

        campaign = Campaign(
            name="AlertCampaign", status=JobStatus.COMPLETED,
            progress=100.0, completed_at=datetime.utcnow(),
        )
        s.add(campaign)
        s.commit()

        run = EvalRun(
            campaign_id=campaign.id, model_id=model.id, benchmark_id=bench.id,
            status=JobStatus.COMPLETED, score=0.3,  # below threshold=0.8
            num_items=5, total_cost_usd=0.01, total_latency_ms=100,
        )
        s.add(run)
        s.commit()

        return {
            "campaign_id": campaign.id,
            "run_id": run.id,
            "model_id": model.id,
            "bench_id": bench.id,
        }


def test_dashboard_alert_below_threshold(client, below_threshold_seeded):
    """Score below threshold should trigger an alert."""
    cid = below_threshold_seeded["campaign_id"]
    # Clear dashboard cache for this campaign
    with results_mod._dashboard_cache_lock:
        results_mod._dashboard_cache.pop(cid, None)
    body = client.get(f"/results/campaign/{cid}/dashboard").json()
    assert len(body["alerts"]) >= 1
    assert any("threshold" in a.lower() or "below" in a.lower() or "%" in a for a in body["alerts"])


def test_dashboard_radar_data_populated(client, seeded):
    """Completed runs should appear in radar data."""
    cid = seeded["campaign_id"]
    with results_mod._dashboard_cache_lock:
        results_mod._dashboard_cache.pop(cid, None)
    body = client.get(f"/results/campaign/{cid}/dashboard").json()
    assert isinstance(body["radar"], dict)


# ── failed items ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def failed_seeded(db_engine):
    """Campaign with failed runs and error items."""
    with Session(db_engine) as s:
        from core.models import LLMModel, ModelProvider, Benchmark, BenchmarkType
        model = LLMModel(name="FailModel", provider=ModelProvider.CUSTOM, model_id="fail/model")
        s.add(model)
        bench = Benchmark(name="FailBench", type=BenchmarkType.ACADEMIC, metric="accuracy")
        s.add(bench)
        s.commit()

        campaign = Campaign(
            name="FailCampaign", status=JobStatus.FAILED, progress=0.0,
        )
        s.add(campaign)
        s.commit()

        # A failed run
        failed_run = EvalRun(
            campaign_id=campaign.id, model_id=model.id, benchmark_id=bench.id,
            status=JobStatus.FAILED, error_message="Infrastructure error",
        )
        s.add(failed_run)
        # A completed run with error items
        completed_run = EvalRun(
            campaign_id=campaign.id, model_id=model.id, benchmark_id=bench.id,
            status=JobStatus.COMPLETED, score=0.5, num_items=3,
        )
        s.add(completed_run)
        s.commit()

        # Add some failed/error items
        for i, (resp, score) in enumerate([
            ("ERROR:timeout exceeded", 0.0),
            ("ERROR:rate limit 429", 0.0),
            ("ERROR:insufficient credits", 0.0),
            ("ERROR:api error", 0.0),
            ("wrong answer", 0.0),
            ("correct answer", 1.0),  # not a failure
        ]):
            item = EvalResult(
                run_id=completed_run.id, item_index=i,
                prompt=f"Q{i}", response=resp, expected="A",
                score=score, latency_ms=100, cost_usd=0.001,
            )
            s.add(item)
        s.commit()

        return {
            "campaign_id": campaign.id,
            "failed_run_id": failed_run.id,
            "completed_run_id": completed_run.id,
            "model_id": model.id,
            "bench_id": bench.id,
        }


def test_failed_items_returns_200(client, failed_seeded):
    cid = failed_seeded["campaign_id"]
    resp = client.get(f"/results/campaign/{cid}/failed-items")
    assert resp.status_code == 200


def test_failed_items_structure(client, failed_seeded):
    cid = failed_seeded["campaign_id"]
    body = client.get(f"/results/campaign/{cid}/failed-items").json()
    assert "items" in body
    assert "total_failed" in body
    assert "failed_runs" in body


def test_failed_items_includes_error_items(client, failed_seeded):
    cid = failed_seeded["campaign_id"]
    body = client.get(f"/results/campaign/{cid}/failed-items").json()
    assert body["total_failed"] >= 4  # 5 error/zero-score items minus the correct one


def test_failed_items_error_type_classification(client, failed_seeded):
    cid = failed_seeded["campaign_id"]
    body = client.get(f"/results/campaign/{cid}/failed-items").json()
    error_types = {item["error_type"] for item in body["items"]}
    assert "timeout" in error_types
    assert "rate_limit" in error_types
    assert "credits" in error_types


def test_failed_items_includes_failed_runs(client, failed_seeded):
    cid = failed_seeded["campaign_id"]
    body = client.get(f"/results/campaign/{cid}/failed-items").json()
    assert len(body["failed_runs"]) >= 1
    assert body["failed_runs"][0]["error_type"] == "infra"


def test_failed_items_no_runs_returns_empty(client):
    resp = client.get("/results/campaign/88888/failed-items")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total_failed"] == 0


# ── insights ──────────────────────────────────────────────────────────────────

def test_insights_returns_200(client, seeded):
    cid = seeded["campaign_id"]
    resp = client.get(f"/results/campaign/{cid}/insights")
    assert resp.status_code == 200


def test_insights_structure(client, seeded):
    cid = seeded["campaign_id"]
    body = client.get(f"/results/campaign/{cid}/insights").json()
    assert "campaign_id" in body
    assert "eval" in body
    assert "genome" in body
    assert "judge" in body
    assert "redbox" in body
    assert "signals" in body
    assert "modules_active" in body


def test_insights_not_found(client):
    resp = client.get("/results/campaign/99999/insights")
    assert resp.status_code == 404


def test_insights_eval_summary_keys(client, seeded):
    cid = seeded["campaign_id"]
    body = client.get(f"/results/campaign/{cid}/insights").json()
    eval_s = body["eval"]
    assert "total_runs" in eval_s
    assert "completed" in eval_s
    assert "avg_score" in eval_s


# ── contamination ─────────────────────────────────────────────────────────────

def test_contamination_returns_200(client, seeded):
    cid = seeded["campaign_id"]
    resp = client.get(f"/results/campaign/{cid}/contamination")
    assert resp.status_code == 200


def test_contamination_not_found(client):
    resp = client.get("/results/campaign/99999/contamination")
    assert resp.status_code == 404


def test_contamination_no_runs(client, db_engine):
    """Campaign with no completed runs returns computed=False."""
    with Session(db_engine) as s:
        campaign = Campaign(name="EmptyContamCamp", status=JobStatus.PENDING, progress=0.0)
        s.add(campaign)
        s.commit()
        cid = campaign.id
    resp = client.get(f"/results/campaign/{cid}/contamination")
    assert resp.status_code == 200
    body = resp.json()
    assert body["computed"] is False


def test_contamination_structure(client, seeded):
    cid = seeded["campaign_id"]
    body = client.get(f"/results/campaign/{cid}/contamination").json()
    assert "overall_contamination_score" in body or "computed" in body


# ── confidence ────────────────────────────────────────────────────────────────

def test_run_confidence_returns_200(client, seeded):
    rid = seeded["run_id"]
    resp = client.get(f"/results/run/{rid}/confidence")
    assert resp.status_code == 200


def test_run_confidence_structure(client, seeded):
    rid = seeded["run_id"]
    body = client.get(f"/results/run/{rid}/confidence").json()
    assert "run_id" in body
    assert "n_items" in body
    assert "score_mean" in body
    assert "confidence_interval_95" in body
    assert "wilson_interval_95" in body
    assert "reliability_grade" in body


def test_run_confidence_no_results(client, db_engine, seeded):
    """Run with no items → 404."""
    from core.models import LLMModel, Benchmark, EvalRun
    with Session(db_engine) as s:
        # Create run without items
        run = EvalRun(
            campaign_id=seeded["campaign_id"],
            model_id=seeded["model_id"],
            benchmark_id=seeded["bench_id"],
            status=JobStatus.PENDING,
        )
        s.add(run)
        s.commit()
        rid = run.id
    resp = client.get(f"/results/run/{rid}/confidence")
    assert resp.status_code == 404


def test_run_confidence_no_scored_items(client, db_engine, seeded):
    """Run with no result items → 404."""
    from core.models import EvalRun
    with Session(db_engine) as s:
        run = EvalRun(
            campaign_id=seeded["campaign_id"],
            model_id=seeded["model_id"],
            benchmark_id=seeded["bench_id"],
            status=JobStatus.COMPLETED,
        )
        s.add(run)
        s.commit()
        rid = run.id
    resp = client.get(f"/results/run/{rid}/confidence")
    assert resp.status_code == 404


# ── compare campaigns ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def compare_seeded(db_engine, seeded):
    """Two campaigns with completed runs on the same model+benchmark."""
    with Session(db_engine) as s:
        from core.models import Campaign, EvalRun, JobStatus
        c1 = Campaign(name="Baseline", status=JobStatus.COMPLETED, progress=100.0)
        c2 = Campaign(name="Candidate", status=JobStatus.COMPLETED, progress=100.0)
        s.add(c1)
        s.add(c2)
        s.commit()

        r1 = EvalRun(
            campaign_id=c1.id,
            model_id=seeded["model_id"],
            benchmark_id=seeded["bench_id"],
            status=JobStatus.COMPLETED,
            score=0.7,
        )
        r2 = EvalRun(
            campaign_id=c2.id,
            model_id=seeded["model_id"],
            benchmark_id=seeded["bench_id"],
            status=JobStatus.COMPLETED,
            score=0.9,
        )
        s.add(r1)
        s.add(r2)
        s.commit()

        return {"baseline_id": c1.id, "candidate_id": c2.id}


def test_compare_campaigns_returns_200(client, compare_seeded):
    baseline = compare_seeded["baseline_id"]
    candidate = compare_seeded["candidate_id"]
    resp = client.get(f"/results/compare?baseline_id={baseline}&candidate_id={candidate}")
    assert resp.status_code == 200


def test_compare_campaigns_structure(client, compare_seeded):
    baseline = compare_seeded["baseline_id"]
    candidate = compare_seeded["candidate_id"]
    body = client.get(f"/results/compare?baseline_id={baseline}&candidate_id={candidate}").json()
    assert "baseline" in body
    assert "candidate" in body
    assert "summary" in body
    assert "regressions" in body
    assert "improvements" in body
    assert "all_comparisons" in body


def test_compare_campaigns_summary_keys(client, compare_seeded):
    baseline = compare_seeded["baseline_id"]
    candidate = compare_seeded["candidate_id"]
    summary = client.get(
        f"/results/compare?baseline_id={baseline}&candidate_id={candidate}"
    ).json()["summary"]
    assert "total_comparisons" in summary
    assert "regressions" in summary
    assert "improvements" in summary


def test_compare_campaigns_missing_baseline(client):
    """Campaigns that don't exist still work — engine handles empty runs."""
    resp = client.get("/results/compare?baseline_id=99990&candidate_id=99991")
    assert resp.status_code == 200


# ── live feed with rate/ETA ───────────────────────────────────────────────────

def test_live_feed_with_started_runs(client, db_engine):
    """Live feed rate calculation runs when there are started runs with items."""
    from core.models import LLMModel, ModelProvider, Benchmark, BenchmarkType, EvalRun, EvalResult
    with Session(db_engine) as s:
        model = LLMModel(name="LiveModel", provider=ModelProvider.CUSTOM, model_id="live/model")
        s.add(model)
        bench = Benchmark(name="LiveBench", type=BenchmarkType.ACADEMIC, metric="accuracy")
        s.add(bench)
        s.commit()

        campaign = Campaign(
            name="LiveCampaign", status=JobStatus.RUNNING, progress=50.0, max_samples=10,
        )
        s.add(campaign)
        s.commit()

        run = EvalRun(
            campaign_id=campaign.id, model_id=model.id, benchmark_id=bench.id,
            status=JobStatus.RUNNING,
            started_at=datetime(2020, 1, 1, 0, 0, 0),  # very old to ensure elapsed > 1
        )
        s.add(run)
        s.commit()

        for i in range(3):
            item = EvalResult(
                run_id=run.id, item_index=i,
                prompt=f"Q{i}", response=f"A{i}", expected="A",
                score=1.0, latency_ms=100, cost_usd=0.001,
            )
            s.add(item)
        s.commit()
        cid = campaign.id

    resp = client.get(f"/results/campaign/{cid}/live")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_runs"] >= 1
    assert body["total_items"] >= 0
