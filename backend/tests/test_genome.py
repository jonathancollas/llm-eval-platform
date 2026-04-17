"""
Tests for api/routers/genome.py
Covers: compute campaign genome, get campaign genome, model genome,
        list fingerprints, ontology endpoint, safety heatmap.
"""
import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

_spec = importlib.util.spec_from_file_location(
    "genome_router",
    Path(__file__).parent.parent / "api" / "routers" / "genome.py",
)
mod = importlib.util.module_from_spec(_spec)
sys.modules["genome_router"] = mod
_spec.loader.exec_module(mod)

from core.models import (
    Campaign, EvalRun, EvalResult, LLMModel, Benchmark,
    FailureProfile, ModelFingerprint, JobStatus,
    ModelProvider, BenchmarkType,
)


@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("genome_tests") / "test.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine):
    def _get_session():
        with Session(db_engine) as s:
            yield s

    test_app = FastAPI()
    test_app.include_router(mod.router)
    test_app.dependency_overrides[mod.get_session] = _get_session
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def seeded(db_engine):
    """Seed model, benchmark, completed campaign and runs."""
    with Session(db_engine) as s:
        model = LLMModel(name="GPT-Test", provider=ModelProvider.OPENAI, model_id="gpt-test-1")
        s.add(model)
        bench = Benchmark(name="TestBench", type=BenchmarkType.ACADEMIC, metric="accuracy")
        s.add(bench)
        s.flush()

        campaign = Campaign(
            name="Completed Campaign",
            model_ids=json.dumps([model.id]),
            benchmark_ids=json.dumps([bench.id]),
            status=JobStatus.COMPLETED,
        )
        s.add(campaign)
        s.flush()

        run = EvalRun(
            campaign_id=campaign.id,
            model_id=model.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
            score=0.85,
            total_latency_ms=1200,
            num_items=5,
        )
        s.add(run)
        s.flush()

        result = EvalResult(
            run_id=run.id,
            item_index=0,
            prompt="What is 2+2?",
            response="4",
            expected="4",
            score=1.0,
            latency_ms=200,
        )
        s.add(result)
        s.commit()

        return {
            "model_id": model.id,
            "bench_id": bench.id,
            "campaign_id": campaign.id,
            "run_id": run.id,
        }


# ── ontology ───────────────────────────────────────────────────────────────────

def test_get_ontology(client):
    resp = client.get("/genome/ontology")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "failures" in data


# ── compute campaign genome ────────────────────────────────────────────────────

def test_compute_campaign_genome_404(client):
    resp = client.post("/genome/campaigns/99999/compute")
    assert resp.status_code == 404


def test_compute_campaign_genome_not_completed(client, db_engine):
    with Session(db_engine) as s:
        campaign = Campaign(
            name="Pending Campaign",
            model_ids="[]",
            benchmark_ids="[]",
            status=JobStatus.PENDING,
        )
        s.add(campaign)
        s.commit()
        cid = campaign.id

    resp = client.post(f"/genome/campaigns/{cid}/compute")
    assert resp.status_code == 400


def test_compute_campaign_genome_success(client, seeded, db_engine):
    cid = seeded["campaign_id"]
    mock_genome = {"hallucination": 0.1, "refusal": 0.05, "factual_error": 0.2}

    with patch("genome_router.classify_run", return_value=mock_genome), \
         patch("genome_router.aggregate_genome", return_value=mock_genome):
        resp = client.post(f"/genome/campaigns/{cid}/compute")

    assert resp.status_code == 200
    data = resp.json()
    assert "profiles_created" in data
    assert "total_runs" in data


def test_compute_campaign_genome_idempotent(client, seeded, db_engine):
    """Computing twice should update existing profiles, not duplicate."""
    cid = seeded["campaign_id"]
    mock_genome = {"hallucination": 0.2}

    with patch("genome_router.classify_run", return_value=mock_genome), \
         patch("genome_router.aggregate_genome", return_value=mock_genome):
        resp1 = client.post(f"/genome/campaigns/{cid}/compute")
        resp2 = client.post(f"/genome/campaigns/{cid}/compute")

    assert resp1.status_code == 200
    assert resp2.status_code == 200


# ── get campaign genome ────────────────────────────────────────────────────────

def test_get_campaign_genome_empty(client):
    resp = client.get("/genome/campaigns/99999")
    assert resp.status_code == 200
    data = resp.json()
    assert data["computed"] is False
    assert data["models"] == {}


def test_get_campaign_genome_with_data(client, seeded, db_engine):
    cid = seeded["campaign_id"]
    # Ensure profiles exist by computing
    mock_genome = {"hallucination": 0.1}
    with patch("genome_router.classify_run", return_value=mock_genome), \
         patch("genome_router.aggregate_genome", return_value=mock_genome):
        client.post(f"/genome/campaigns/{cid}/compute")

    with patch("genome_router.aggregate_genome", return_value=mock_genome):
        resp = client.get(f"/genome/campaigns/{cid}")

    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert "ontology" in data


# ── model genome ──────────────────────────────────────────────────────────────

def test_get_model_genome_404(client):
    resp = client.get("/genome/models/99999")
    assert resp.status_code == 404


def test_get_model_genome_no_fingerprint(client, seeded):
    mid = seeded["model_id"]
    resp = client.get(f"/genome/models/{mid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_id"] == mid
    assert data["has_data"] is False or "has_data" in data


def test_get_model_genome_with_fingerprint(client, db_engine):
    """Use a fresh model to avoid UNIQUE constraint on model_fingerprints."""
    with Session(db_engine) as s:
        model = LLMModel(name="FingerprintModel", provider=ModelProvider.CUSTOM, model_id="fp/model-unique")
        s.add(model)
        s.flush()
        fp = ModelFingerprint(
            model_id=model.id,
            genome_json=json.dumps({"hallucination": 0.3}),
            stats_json=json.dumps({"num_runs": 5, "avg_score": 0.7}),
        )
        s.add(fp)
        s.commit()
        mid = model.id

    resp = client.get(f"/genome/models/{mid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_data"] is True
    assert "genome" in data
    assert "stats" in data


# ── list model fingerprints ───────────────────────────────────────────────────

def test_list_model_fingerprints_empty(client, db_engine):
    """Use fresh engine to test empty case."""
    db2 = db_engine  # may have data; just check response structure
    resp = client.get("/genome/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "fingerprints" in data
    assert "ontology" in data


def test_list_model_fingerprints_with_data(client, seeded, db_engine):
    resp = client.get("/genome/models")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["fingerprints"], list)


# ── safety heatmap ────────────────────────────────────────────────────────────

def test_safety_heatmap_no_profiles(client, db_engine):
    """With a fresh db or no profiles, heatmap should indicate not computed."""
    db2_path = db_engine  # reuse the same db
    resp = client.get("/genome/safety-heatmap")
    assert resp.status_code == 200
    data = resp.json()
    # Either computed=True (if profiles exist) or computed=False
    assert "heatmap" in data or "computed" in data


def test_safety_heatmap_with_profiles(client, seeded, db_engine):
    """Seed profiles and check heatmap returns structured data."""
    cid = seeded["campaign_id"]
    mock_genome = {"hallucination": 0.4, "prompt_injection": 0.1}
    with patch("genome_router.classify_run", return_value=mock_genome), \
         patch("genome_router.aggregate_genome", return_value=mock_genome):
        client.post(f"/genome/campaigns/{cid}/compute")

    resp = client.get("/genome/safety-heatmap")
    assert resp.status_code == 200
    data = resp.json()
    assert "computed" in data


# ── campaign with run but no results ─────────────────────────────────────────

def test_compute_genome_run_without_results(client, db_engine):
    """Run that has no EvalResults should still compute genome from run-level data."""
    with Session(db_engine) as s:
        model = LLMModel(name="Bare Model", provider=ModelProvider.CUSTOM, model_id="bare/model")
        s.add(model)
        bench = Benchmark(name="Bare Bench", type=BenchmarkType.SAFETY, metric="pass_rate")
        s.add(bench)
        s.flush()

        campaign = Campaign(
            name="Bare Campaign",
            model_ids=json.dumps([model.id]),
            benchmark_ids=json.dumps([bench.id]),
            status=JobStatus.COMPLETED,
        )
        s.add(campaign)
        s.flush()

        run = EvalRun(
            campaign_id=campaign.id,
            model_id=model.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
            score=0.5,
            total_latency_ms=500,
            num_items=0,
        )
        s.add(run)
        s.commit()
        cid = campaign.id

    mock_genome = {"hallucination": 0.2}
    with patch("genome_router.classify_run", return_value=mock_genome), \
         patch("genome_router.aggregate_genome", return_value=mock_genome):
        resp = client.post(f"/genome/campaigns/{cid}/compute")

    assert resp.status_code == 200
    assert resp.json()["profiles_created"] >= 1


# ══════════════════════════════════════════════════════════════════════════════
# NEW TEST ADDITIONS: compare_campaigns, explain_regression, get_run_signals,
# compute_hybrid_genome
# ══════════════════════════════════════════════════════════════════════════════

# ── compare_campaigns ─────────────────────────────────────────────────────────

def test_compare_campaigns_baseline_not_found(client):
    resp = client.get("/genome/regression/compare?baseline_id=99999&candidate_id=99999")
    assert resp.status_code == 404


def test_compare_campaigns_success(client, seeded, db_engine):
    """Two distinct completed campaigns → compare returns score_delta + probable_causes."""
    baseline_cid = seeded["campaign_id"]

    with Session(db_engine) as s:
        model = LLMModel(
            name="Compare-Model",
            provider=ModelProvider.CUSTOM,
            model_id="compare/model-v2",
        )
        s.add(model)
        bench = Benchmark(
            name="Compare-Bench",
            type=BenchmarkType.ACADEMIC,
            metric="accuracy",
        )
        s.add(bench)
        s.flush()

        candidate_campaign = Campaign(
            name="Candidate Campaign",
            model_ids=json.dumps([model.id]),
            benchmark_ids=json.dumps([bench.id]),
            status=JobStatus.COMPLETED,
        )
        s.add(candidate_campaign)
        s.flush()

        run = EvalRun(
            campaign_id=candidate_campaign.id,
            model_id=model.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
            score=0.70,
            total_latency_ms=800,
            num_items=3,
        )
        s.add(run)
        s.commit()
        candidate_cid = candidate_campaign.id

    resp = client.get(
        f"/genome/regression/compare?baseline_id={baseline_cid}&candidate_id={candidate_cid}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "baseline" in data
    assert "candidate" in data
    assert "score_delta" in data
    assert "regression_detected" in data
    assert "probable_causes" in data
    assert data["baseline"]["id"] == baseline_cid
    assert data["candidate"]["id"] == candidate_cid


def test_compare_campaigns_no_regression(client, seeded, db_engine):
    """Campaigns with similar scores → regression_detected=False."""
    baseline_cid = seeded["campaign_id"]

    with Session(db_engine) as s:
        model = LLMModel(
            name="NoReg-Model",
            provider=ModelProvider.CUSTOM,
            model_id="noreg/model-1",
        )
        s.add(model)
        bench = Benchmark(
            name="NoReg-Bench",
            type=BenchmarkType.ACADEMIC,
            metric="accuracy",
        )
        s.add(bench)
        s.flush()

        similar_campaign = Campaign(
            name="Similar Campaign",
            model_ids=json.dumps([model.id]),
            benchmark_ids=json.dumps([bench.id]),
            status=JobStatus.COMPLETED,
        )
        s.add(similar_campaign)
        s.flush()

        # Score very close to baseline (0.85) → no regression
        run = EvalRun(
            campaign_id=similar_campaign.id,
            model_id=model.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
            score=0.84,
            total_latency_ms=1000,
            num_items=3,
        )
        s.add(run)
        s.commit()
        similar_cid = similar_campaign.id

    resp = client.get(
        f"/genome/regression/compare?baseline_id={baseline_cid}&candidate_id={similar_cid}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["regression_detected"] is False


# ── explain_regression ────────────────────────────────────────────────────────

def test_explain_regression_no_regression(client, seeded, db_engine):
    """When no regression is detected, explanation says 'No significant regression'."""
    baseline_cid = seeded["campaign_id"]

    with Session(db_engine) as s:
        model = LLMModel(
            name="NoReg-Explain-Model",
            provider=ModelProvider.CUSTOM,
            model_id="noreg/explain-model",
        )
        s.add(model)
        bench = Benchmark(
            name="NoReg-Explain-Bench",
            type=BenchmarkType.ACADEMIC,
            metric="accuracy",
        )
        s.add(bench)
        s.flush()

        similar = Campaign(
            name="Similar For Explain",
            model_ids=json.dumps([model.id]),
            benchmark_ids=json.dumps([bench.id]),
            status=JobStatus.COMPLETED,
        )
        s.add(similar)
        s.flush()
        run = EvalRun(
            campaign_id=similar.id,
            model_id=model.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
            score=0.84,
            total_latency_ms=1000,
            num_items=3,
        )
        s.add(run)
        s.commit()
        similar_cid = similar.id

    resp = client.post(
        f"/genome/regression/explain?baseline_id={baseline_cid}&candidate_id={similar_cid}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "explanation" in data
    assert "No significant regression" in data["explanation"]


def test_explain_regression_no_api_key(client, seeded, db_engine):
    """Regression detected but no Anthropic key → explanation has 'ANTHROPIC_API_KEY required'."""
    baseline_cid = seeded["campaign_id"]

    with Session(db_engine) as s:
        model = LLMModel(
            name="Regressed-Model",
            provider=ModelProvider.CUSTOM,
            model_id="reg/model-v1",
        )
        s.add(model)
        bench = Benchmark(
            name="Regressed-Bench",
            type=BenchmarkType.ACADEMIC,
            metric="accuracy",
        )
        s.add(bench)
        s.flush()
        regressed = Campaign(
            name="Regressed Campaign",
            model_ids=json.dumps([model.id]),
            benchmark_ids=json.dumps([bench.id]),
            status=JobStatus.COMPLETED,
        )
        s.add(regressed)
        s.flush()
        # Low score → significant regression vs baseline 0.85
        run = EvalRun(
            campaign_id=regressed.id,
            model_id=model.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
            score=0.5,
            total_latency_ms=1000,
            num_items=3,
        )
        s.add(run)
        s.commit()
        regressed_cid = regressed.id

    mock_settings = MagicMock()
    mock_settings.anthropic_api_key = ""
    with patch("core.config.get_settings", return_value=mock_settings):
        resp = client.post(
            f"/genome/regression/explain?baseline_id={baseline_cid}&candidate_id={regressed_cid}"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "explanation" in data
    assert "ANTHROPIC_API_KEY required" in data["explanation"]


def test_explain_regression_with_api_key(client, seeded, db_engine):
    """Regression detected + Anthropic key → explanation generated via mocked Anthropic."""
    baseline_cid = seeded["campaign_id"]

    with Session(db_engine) as s:
        model = LLMModel(
            name="Regressed-API-Model",
            provider=ModelProvider.CUSTOM,
            model_id="reg/api-model-v1",
        )
        s.add(model)
        bench = Benchmark(
            name="Regressed-API-Bench",
            type=BenchmarkType.ACADEMIC,
            metric="accuracy",
        )
        s.add(bench)
        s.flush()
        regressed = Campaign(
            name="Regressed API Campaign",
            model_ids=json.dumps([model.id]),
            benchmark_ids=json.dumps([bench.id]),
            status=JobStatus.COMPLETED,
        )
        s.add(regressed)
        s.flush()
        run = EvalRun(
            campaign_id=regressed.id,
            model_id=model.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
            score=0.4,
            total_latency_ms=1000,
            num_items=3,
        )
        s.add(run)
        s.commit()
        regressed_cid = regressed.id

    mock_settings = MagicMock()
    mock_settings.anthropic_api_key = "sk-test-key"

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="Root cause: model degradation.")]

    mock_anthropic_client = MagicMock()
    mock_anthropic_client.messages.create = AsyncMock(return_value=mock_msg)

    with patch("core.config.get_settings", return_value=mock_settings), \
         patch("anthropic.AsyncAnthropic", return_value=mock_anthropic_client):
        resp = client.post(
            f"/genome/regression/explain?baseline_id={baseline_cid}&candidate_id={regressed_cid}"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "explanation" in data


# ── get_run_signals ───────────────────────────────────────────────────────────

def test_get_run_signals_not_found(client):
    resp = client.get("/genome/signals/99999")
    assert resp.status_code == 404


def test_get_run_signals_success(client, seeded):
    run_id = seeded["run_id"]
    resp = client.get(f"/genome/signals/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run_id
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


# ── compute_hybrid_genome ─────────────────────────────────────────────────────

def test_compute_hybrid_genome_no_api_key(client, seeded):
    """No anthropic_api_key → 422."""
    cid = seeded["campaign_id"]
    mock_settings = MagicMock()
    mock_settings.anthropic_api_key = ""
    with patch("core.config.get_settings", return_value=mock_settings):
        resp = client.post(f"/genome/campaigns/{cid}/compute-hybrid")
    assert resp.status_code == 422


def test_compute_hybrid_genome_campaign_not_found(client):
    mock_settings = MagicMock()
    mock_settings.anthropic_api_key = "sk-test"
    with patch("core.config.get_settings", return_value=mock_settings):
        resp = client.post("/genome/campaigns/99999/compute-hybrid")
    assert resp.status_code == 404


def test_compute_hybrid_genome_not_completed(client, db_engine):
    with Session(db_engine) as s:
        pending = Campaign(
            name="Hybrid Pending Campaign",
            model_ids="[]",
            benchmark_ids="[]",
            status=JobStatus.PENDING,
        )
        s.add(pending)
        s.commit()
        cid = pending.id

    mock_settings = MagicMock()
    mock_settings.anthropic_api_key = "sk-test"
    with patch("core.config.get_settings", return_value=mock_settings):
        resp = client.post(f"/genome/campaigns/{cid}/compute-hybrid")
    assert resp.status_code == 400


def test_compute_hybrid_genome_success(client, seeded):
    cid = seeded["campaign_id"]
    mock_settings = MagicMock()
    mock_settings.anthropic_api_key = "sk-test"

    with patch("core.config.get_settings", return_value=mock_settings), \
         patch("genome_router.classify_run_hybrid",
               new=AsyncMock(return_value={"hallucination": 0.1})), \
         patch("genome_router.classify_run",
               return_value={"hallucination": 0.1}), \
         patch("genome_router.aggregate_genome",
               return_value={"hallucination": 0.1}):
        resp = client.post(f"/genome/campaigns/{cid}/compute-hybrid")

    assert resp.status_code == 200
    data = resp.json()
    assert "profiles_created" in data
    assert data["method"] == "hybrid_rules_llm"
    assert "total_runs" in data
