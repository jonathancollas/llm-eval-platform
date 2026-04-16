"""
Tests for api/routers/evidence.py
Covers: create/list/get trials, analyze trial, collect RWD, list RWD,
        synthesize RWE, list/get RWE, statistical helpers.
"""
import importlib.util
import json
import os
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

_spec = importlib.util.spec_from_file_location(
    "evidence_router",
    Path(__file__).parent.parent / "api" / "routers" / "evidence.py",
)
mod = importlib.util.module_from_spec(_spec)
sys.modules["evidence_router"] = mod
_spec.loader.exec_module(mod)

from core.models import (
    EvalTrial, RealWorldDataset, RealWorldEvidence, LLMModel,
    Campaign, EvalRun, TelemetryEvent, JobStatus, ModelProvider, BenchmarkType, Benchmark,
)


@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("evidence_tests") / "evidence.db"
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
    with Session(db_engine) as s:
        model = LLMModel(name="EvidenceModel", provider=ModelProvider.OPENAI, model_id="evidence/model-1")
        s.add(model)
        bench = Benchmark(name="EvidenceBench", type=BenchmarkType.ACADEMIC, metric="accuracy")
        s.add(bench)
        s.flush()

        campaign_a = Campaign(
            name="Trial Arm A",
            model_ids=json.dumps([model.id]),
            benchmark_ids=json.dumps([bench.id]),
            status=JobStatus.COMPLETED,
        )
        campaign_b = Campaign(
            name="Trial Arm B",
            model_ids=json.dumps([model.id]),
            benchmark_ids=json.dumps([bench.id]),
            status=JobStatus.COMPLETED,
        )
        s.add(campaign_a)
        s.add(campaign_b)
        s.flush()

        # Seed 25+ completed runs per arm to exceed 20-sample threshold
        for score in [0.6, 0.7, 0.8, 0.75, 0.65, 0.9, 0.55, 0.85, 0.72, 0.68,
                      0.71, 0.74, 0.77, 0.82, 0.63, 0.69, 0.78, 0.84, 0.61, 0.73,
                      0.79, 0.83, 0.67, 0.76, 0.88]:
            s.add(EvalRun(
                campaign_id=campaign_a.id,
                model_id=model.id,
                benchmark_id=bench.id,
                status=JobStatus.COMPLETED,
                score=score,
            ))
        for score in [0.5, 0.55, 0.6, 0.65, 0.7, 0.45, 0.8, 0.52, 0.58, 0.72,
                      0.48, 0.53, 0.62, 0.69, 0.56, 0.64, 0.71, 0.75, 0.49, 0.57,
                      0.63, 0.67, 0.74, 0.78, 0.51]:
            s.add(EvalRun(
                campaign_id=campaign_b.id,
                model_id=model.id,
                benchmark_id=bench.id,
                status=JobStatus.COMPLETED,
                score=score,
            ))

        # Telemetry events for RWD
        now = datetime.utcnow()
        for i in range(5):
            s.add(TelemetryEvent(
                model_id=model.id,
                event_type="inference",
                latency_ms=200 + i * 10,
                score=0.7 + i * 0.02,
                safety_flag=None,
                timestamp=now - timedelta(hours=i),
            ))

        s.commit()
        return {
            "model_id": model.id,
            "bench_id": bench.id,
            "campaign_a_id": campaign_a.id,
            "campaign_b_id": campaign_b.id,
        }


# ── Trial endpoints ───────────────────────────────────────────────────────────

def test_list_trials_empty(client):
    resp = client.get("/evidence/trials")
    assert resp.status_code == 200
    assert "trials" in resp.json()


def test_create_trial(client, seeded):
    payload = {
        "name": "Safety RCT",
        "hypothesis": "Model B is safer than A",
        "arms": [
            {"name": "Arm A", "model_ids": [seeded["model_id"]], "benchmark_ids": [seeded["bench_id"]]},
            {"name": "Arm B", "model_ids": [seeded["model_id"]], "benchmark_ids": [seeded["bench_id"]]},
        ],
        "sample_size_per_arm": 50,
        "confidence_level": 0.95,
    }
    resp = client.post("/evidence/trials", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "trial_id" in data
    assert data["arms"] == 2
    assert "power_analysis" in data


def test_create_trial_99_confidence(client, seeded):
    """Tests the non-0.95 confidence level branch."""
    payload = {
        "name": "High Conf RCT",
        "arms": [
            {"name": "A", "model_ids": [seeded["model_id"]], "benchmark_ids": []},
            {"name": "B", "model_ids": [seeded["model_id"]], "benchmark_ids": []},
        ],
        "confidence_level": 0.99,
    }
    resp = client.post("/evidence/trials", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["power_analysis"]["alpha"] == pytest.approx(0.01, abs=1e-6)


def test_create_trial_too_few_arms(client):
    payload = {
        "name": "Bad Trial",
        "arms": [{"name": "Only Arm", "model_ids": [], "benchmark_ids": []}],
    }
    resp = client.post("/evidence/trials", json=payload)
    assert resp.status_code == 422


def test_list_trials_after_create(client):
    resp = client.get("/evidence/trials")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["trials"]) >= 1


def test_get_trial(client, seeded):
    # Create a trial and get it back
    payload = {
        "name": "Fetch Trial",
        "arms": [
            {"name": "X", "model_ids": [], "benchmark_ids": []},
            {"name": "Y", "model_ids": [], "benchmark_ids": []},
        ],
    }
    create_resp = client.post("/evidence/trials", json=payload)
    trial_id = create_resp.json()["trial_id"]

    resp = client.get(f"/evidence/trials/{trial_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == trial_id
    assert data["name"] == "Fetch Trial"


def test_get_trial_404(client):
    resp = client.get("/evidence/trials/99999")
    assert resp.status_code == 404


# ── Analyze trial ─────────────────────────────────────────────────────────────

def test_analyze_trial_404(client):
    resp = client.post("/evidence/trials/99999/analyze")
    assert resp.status_code == 404


def test_analyze_trial_no_campaigns(client):
    payload = {
        "name": "No Campaign Trial",
        "arms": [
            {"name": "A", "model_ids": [], "benchmark_ids": []},
            {"name": "B", "model_ids": [], "benchmark_ids": []},
        ],
    }
    cr = client.post("/evidence/trials", json=payload)
    tid = cr.json()["trial_id"]

    resp = client.post(f"/evidence/trials/{tid}/analyze")
    assert resp.status_code == 400


def test_analyze_trial_success(client, seeded, db_engine):
    """Create a trial linked to 2 campaigns with completed runs."""
    with Session(db_engine) as s:
        trial = EvalTrial(
            name="Linked Trial",
            arms_json=json.dumps([
                {"name": "Arm A", "model_ids": [seeded["model_id"]], "benchmark_ids": []},
                {"name": "Arm B", "model_ids": [seeded["model_id"]], "benchmark_ids": []},
            ]),
            campaign_ids=json.dumps([seeded["campaign_a_id"], seeded["campaign_b_id"]]),
            power_analysis_json="{}",
            secondary_endpoints="[]",
            confidence_level=0.95,
        )
        s.add(trial)
        s.commit()
        tid = trial.id

    resp = client.post(f"/evidence/trials/{tid}/analyze")
    assert resp.status_code == 200
    data = resp.json()
    assert "comparison" in data
    assert "p_value" in data["comparison"]
    assert "arms" in data


# ── RWD endpoints ─────────────────────────────────────────────────────────────

def test_list_rwd_empty(client):
    resp = client.get("/evidence/rwd")
    assert resp.status_code == 200
    assert "datasets" in resp.json()


def test_collect_rwd_no_events(client, db_engine):
    """Model with no telemetry should return 400."""
    with Session(db_engine) as s:
        model = LLMModel(name="No Telemetry", provider=ModelProvider.CUSTOM, model_id="no/telemetry")
        s.add(model)
        s.commit()
        mid = model.id

    resp = client.post(f"/evidence/rwd/collect?model_id={mid}&hours=24")
    assert resp.status_code == 400


def test_collect_rwd_success(client, seeded):
    mid = seeded["model_id"]
    resp = client.post(f"/evidence/rwd/collect?model_id={mid}&hours=48")
    assert resp.status_code == 200
    data = resp.json()
    assert "rwd_id" in data
    assert "total_events" in data
    assert data["total_events"] > 0


def test_collect_rwd_with_name(client, seeded):
    mid = seeded["model_id"]
    resp = client.post(f"/evidence/rwd/collect?model_id={mid}&hours=48&name=MyRWD")
    assert resp.status_code == 200
    assert resp.json()["name"] == "MyRWD" or "rwd_id" in resp.json()


def test_list_rwd_after_collect(client, seeded):
    resp = client.get("/evidence/rwd")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["datasets"]) >= 1


# ── RWE endpoints ─────────────────────────────────────────────────────────────

def test_list_rwe_empty(client):
    resp = client.get("/evidence/rwe")
    assert resp.status_code == 200
    assert "evidence" in resp.json()


def test_synthesize_rwe_trial_404(client):
    resp = client.post("/evidence/rwe/synthesize?trial_id=99999&rwd_dataset_id=1")
    assert resp.status_code == 404


def test_synthesize_rwe_rwd_404(client, seeded, db_engine):
    # Create a minimal trial
    with Session(db_engine) as s:
        trial = EvalTrial(
            name="For RWE 404",
            arms_json="[]",
            campaign_ids="[]",
            power_analysis_json="{}",
            secondary_endpoints="[]",
        )
        s.add(trial)
        s.commit()
        tid = trial.id

    resp = client.post(f"/evidence/rwe/synthesize?trial_id={tid}&rwd_dataset_id=99999")
    assert resp.status_code == 404


def test_synthesize_rwe_success(client, seeded, db_engine):
    """Full synthesis with both RCT and RWD data."""
    # Create trial with results
    with Session(db_engine) as s:
        trial = EvalTrial(
            name="Full Trial",
            arms_json=json.dumps([
                {"name": "A", "model_ids": [], "benchmark_ids": []},
                {"name": "B", "model_ids": [], "benchmark_ids": []},
            ]),
            campaign_ids=json.dumps([seeded["campaign_a_id"], seeded["campaign_b_id"]]),
            power_analysis_json="{}",
            secondary_endpoints="[]",
            confidence_level=0.95,
            results_json=json.dumps({
                "arms": {
                    "A": {"mean": 0.75, "std": 0.1, "n": 25, "min": 0.5, "max": 0.9},
                    "B": {"mean": 0.65, "std": 0.1, "n": 25, "min": 0.4, "max": 0.8},
                }
            }),
            p_value=0.03,
        )
        s.add(trial)
        s.flush()

        rwd = RealWorldDataset(
            name="Test RWD",
            model_id=seeded["model_id"],
            total_events=5,
            avg_score=0.7,
            safety_flag_rate=0.05,
            error_rate=0.01,
        )
        s.add(rwd)
        s.commit()
        tid = trial.id
        rwdid = rwd.id

    resp = client.post(f"/evidence/rwe/synthesize?trial_id={tid}&rwd_dataset_id={rwdid}")
    assert resp.status_code == 200
    data = resp.json()
    assert "rwe_id" in data
    assert "evidence_grade" in data
    assert data["evidence_grade"] in ("A", "B", "C", "D")


def test_synthesize_rwe_with_name(client, seeded, db_engine):
    """RWE synthesis with custom name."""
    with Session(db_engine) as s:
        trial = EvalTrial(
            name="Named RWE Trial",
            arms_json="[]",
            campaign_ids="[]",
            power_analysis_json="{}",
            secondary_endpoints="[]",
        )
        s.add(trial)
        rwd = RealWorldDataset(
            name="Named RWD",
            model_id=seeded["model_id"],
            total_events=3,
            avg_score=None,  # No RCT or RWD score → grade D
            safety_flag_rate=0.0,
            error_rate=0.0,
        )
        s.add(rwd)
        s.commit()
        tid = trial.id
        rwdid = rwd.id

    resp = client.post(
        f"/evidence/rwe/synthesize?trial_id={tid}&rwd_dataset_id={rwdid}&name=CustomRWE"
    )
    assert resp.status_code == 200


def test_get_rwe_success(client, seeded, db_engine):
    with Session(db_engine) as s:
        rwe = RealWorldEvidence(
            name="Stored RWE",
            trial_id=None,
            rwd_dataset_id=None,
            evidence_grade="B",
            rct_score=0.8,
            rwd_score=0.75,
            concordance=0.94,
        )
        s.add(rwe)
        s.commit()
        rweid = rwe.id

    resp = client.get(f"/evidence/rwe/{rweid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == rweid
    assert data["evidence_grade"] == "B"


def test_get_rwe_404(client):
    resp = client.get("/evidence/rwe/99999")
    assert resp.status_code == 404


def test_list_rwe_after_synthesis(client):
    resp = client.get("/evidence/rwe")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["evidence"]) >= 1


# ── Statistical helper coverage ───────────────────────────────────────────────

def test_std_helper():
    assert mod._std([1.0]) == 0.0
    assert mod._std([1.0, 2.0]) == pytest.approx(0.7071, abs=0.001)
    assert mod._std([]) == 0.0


def test_mann_whitney_u():
    p, effect = mod._mann_whitney_u([1, 2, 3], [4, 5, 6])
    assert 0.0 <= p <= 1.0
    assert effect >= 0.0


def test_mann_whitney_u_identical():
    p, effect = mod._mann_whitney_u([1, 1, 1], [1, 1, 1])
    # sigma == 0, should return (1.0, 0.0)
    assert p == 1.0
    assert effect == 0.0


def test_normal_cdf():
    assert mod._normal_cdf(0.0) == pytest.approx(0.5, abs=0.01)
    assert mod._normal_cdf(1.96) > 0.97


def test_bootstrap_ci():
    lo, hi = mod._bootstrap_ci([0.8] * 25, [0.5] * 25)
    assert lo <= hi  # With very different samples, lo <= hi always


def test_histogram_empty():
    assert mod._histogram([]) == []


def test_histogram_uniform():
    result = mod._histogram([1.0, 1.0, 1.0])
    assert len(result) == 1  # mn == mx
    assert result[0]["count"] == 3


def test_histogram_varied():
    result = mod._histogram([0.0, 0.25, 0.5, 0.75, 1.0], bins=5)
    assert len(result) == 5
    total = sum(b["count"] for b in result)
    assert total == 5


# ── Analyze trial with insufficient data ─────────────────────────────────────

def test_analyze_trial_empty_scores(client, db_engine):
    """Arms with runs but all scores=None → 400."""
    with Session(db_engine) as s:
        m = LLMModel(name="Null Score Model", provider=ModelProvider.CUSTOM, model_id="null/score")
        s.add(m)
        b = Benchmark(name="NullBench", type=BenchmarkType.ACADEMIC, metric="accuracy")
        s.add(b)
        s.flush()

        ca = Campaign(name="NullArm A", model_ids="[]", benchmark_ids="[]", status=JobStatus.COMPLETED)
        cb = Campaign(name="NullArm B", model_ids="[]", benchmark_ids="[]", status=JobStatus.COMPLETED)
        s.add(ca)
        s.add(cb)
        s.flush()

        # Runs with None scores
        s.add(EvalRun(campaign_id=ca.id, model_id=m.id, benchmark_id=b.id, status=JobStatus.COMPLETED, score=None))
        s.add(EvalRun(campaign_id=cb.id, model_id=m.id, benchmark_id=b.id, status=JobStatus.COMPLETED, score=None))

        trial = EvalTrial(
            name="Empty Score Trial",
            arms_json=json.dumps([{"name": "A"}, {"name": "B"}]),
            campaign_ids=json.dumps([ca.id, cb.id]),
            power_analysis_json="{}",
            secondary_endpoints="[]",
            confidence_level=0.95,
        )
        s.add(trial)
        s.commit()
        tid = trial.id

    resp = client.post(f"/evidence/trials/{tid}/analyze")
    assert resp.status_code == 400
