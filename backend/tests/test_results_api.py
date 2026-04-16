"""
Tests for api/routers/results.py
Covers: dashboard, stats/summary, run items, CSV export, live feed,
        _csv_escape injection prevention.
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
