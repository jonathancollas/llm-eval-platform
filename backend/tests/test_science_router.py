"""
Tests for api/routers/science.py
Covers all missing lines: helper functions, capability-propensity, mech-interp,
contamination, validity, compositional risk, failure clustering.
"""
import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

# ── Load module ────────────────────────────────────────────────────────────────

_spec = importlib.util.spec_from_file_location(
    "science_router",
    Path(__file__).parent.parent / "api" / "routers" / "science.py",
)
sci = importlib.util.module_from_spec(_spec)
sys.modules["science_router"] = sci
_spec.loader.exec_module(sci)

from core.models import (
    Benchmark, BenchmarkType, Campaign, EvalResult, EvalRun,
    FailureProfile, JobStatus, LLMModel, ModelFingerprint, ModelProvider,
)

# ── DB + App Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("sci") / "sci.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def seeded_db(db_engine):
    """Seed DB with model, benchmark, campaign, run, results."""
    with Session(db_engine) as s:
        model = LLMModel(name="TestModel", provider=ModelProvider.CUSTOM,
                         model_id="test/model-1")
        s.add(model)
        s.flush()

        bench = Benchmark(name="TestBench", type=BenchmarkType.SAFETY,
                          num_samples=50, source="public")
        s.add(bench)
        s.flush()

        bench_persuasion = Benchmark(name="persuasion-test",
                                     type=BenchmarkType.SAFETY,
                                     num_samples=30, source="inesia")
        s.add(bench_persuasion)
        s.flush()

        campaign = Campaign(name="TestCampaign", model_ids="[]", benchmark_ids="[]")
        s.add(campaign)
        s.flush()

        run = EvalRun(campaign_id=campaign.id, model_id=model.id,
                      benchmark_id=bench.id, status=JobStatus.COMPLETED,
                      score=0.75)
        s.add(run)
        s.flush()

        for i in range(5):
            s.add(EvalResult(
                run_id=run.id, item_index=i,
                prompt=f"What is question {i}?",
                response=f"Answer {i}", expected=f"Expected {i}",
                score=0.3 if i < 3 else 0.8,
            ))

        run_prop = EvalRun(campaign_id=campaign.id, model_id=model.id,
                           benchmark_id=bench.id, status=JobStatus.COMPLETED,
                           score=0.6, capability_score=0.8, propensity_score=0.6)
        s.add(run_prop)
        s.flush()
        s.commit()
        return {
            "model_id": model.id, "bench_id": bench.id,
            "bench_persuasion_id": bench_persuasion.id,
            "campaign_id": campaign.id, "run_id": run.id,
            "run_prop_id": run_prop.id,
        }


@pytest.fixture(scope="module")
def client(db_engine, seeded_db):
    def _get_session():
        with Session(db_engine) as s:
            yield s

    app = FastAPI()
    app.include_router(sci.router)
    app.dependency_overrides[sci.get_session] = _get_session
    with TestClient(app) as c:
        yield c


# ── Helper function tests ──────────────────────────────────────────────────────

def test_pattern_score_empty_text():
    """Line 52 — empty text returns 0.0."""
    assert sci._pattern_score("", sci._PERSUASION_PATTERNS) == 0.0


def test_pattern_score_with_matches():
    assert sci._pattern_score("you should act now", sci._PERSUASION_PATTERNS) > 0.0


def test_pattern_score_no_patterns():
    assert sci._pattern_score("some text", ()) == 0.0


def test_is_persuasion_benchmark_true_name():
    """Lines 58-60."""
    b = MagicMock()
    b.name = "persuasion-benchmark"
    b.dataset_path = ""
    assert sci._is_persuasion_benchmark(b) is True


def test_is_persuasion_benchmark_true_dataset():
    b = MagicMock()
    b.name = "other"
    b.dataset_path = "data/persuasion_v1.json"
    assert sci._is_persuasion_benchmark(b) is True


def test_is_persuasion_benchmark_false():
    b = MagicMock()
    b.name = "hellaswag"
    b.dataset_path = "hellaswag.json"
    assert sci._is_persuasion_benchmark(b) is False


def test_compute_persuasion_metrics_no_probes():
    """Line 72 — empty probes path."""
    report = MagicMock()
    report.probes = []
    result = sci._compute_persuasion_metrics(report)
    assert result["capability_score"] == 0.0
    assert result["propensity_score"] == 0.0
    assert "elicitation_variants" in result


def test_compute_persuasion_metrics_with_probes():
    report = MagicMock()
    p1 = MagicMock()
    p1.capability_response = "you should act now before it's too late"
    p1.propensity_response = "everyone agrees that you must do this now"
    report.probes = [p1]
    result = sci._compute_persuasion_metrics(report)
    assert "capability_score" in result
    assert "manipulation_score" in result
    assert "false_consensus_rate" in result
    assert "emotional_leverage_index" in result


# ── _get_questions ─────────────────────────────────────────────────────────────

def test_get_questions_from_db(db_engine, seeded_db):
    """Lines 112-126 — questions pulled from eval results."""
    with Session(db_engine) as s:
        bench = s.get(Benchmark, seeded_db["bench_id"])
        questions = sci._get_questions(bench, 5, s)
    assert len(questions) >= 1
    assert "question" in questions[0]


def test_get_questions_no_runs(db_engine):
    """Lines 128-144 — no runs, no dataset file → empty list."""
    with Session(db_engine) as s:
        bench = Benchmark(name="isolated-bench", type=BenchmarkType.CUSTOM)
        s.add(bench)
        s.flush()
        questions = sci._get_questions(bench, 5, s)
    assert questions == []


# ── POST /science/capability-propensity ───────────────────────────────────────

def _make_cap_prop_report():
    p = MagicMock()
    p.question = "Q?"
    p.capability_score = 0.9
    p.propensity_score = 0.6
    p.gap = 0.3
    p.category = "safety"
    p.capability_response = "you should act now"
    p.propensity_response = "everyone agrees"

    report = MagicMock()
    report.model_name = "TestModel"
    report.benchmark_name = "TestBench"
    report.n_probes = 1
    report.mean_capability = 0.9
    report.mean_propensity = 0.6
    report.mean_gap = 0.3
    report.gap_direction = "positive"
    report.gap_significance = "large"
    report.tail_propensity_p10 = 0.4
    report.tail_propensity_p5 = 0.3
    report.worst_case_gap = 0.5
    report.propensity_skew = 0.1
    report.capability_variance = 0.02
    report.propensity_variance = 0.04
    report.safety_concern = True
    report.safety_concern_reason = "High gap"
    report.probes = [p]
    report.total_tokens = 100
    report.total_cost_usd = 0.01
    return report


def test_capability_propensity_404_model(client):
    """Lines 173-175."""
    resp = client.post("/science/capability-propensity",
                       json={"model_id": 9999, "benchmark_id": 1})
    assert resp.status_code == 404


def test_capability_propensity_404_benchmark(client, seeded_db):
    """Lines 176-178."""
    resp = client.post("/science/capability-propensity",
                       json={"model_id": seeded_db["model_id"], "benchmark_id": 9999})
    assert resp.status_code == 404


def test_capability_propensity_422_no_questions(client, seeded_db):
    """Lines 180-182 — no questions for isolated benchmark."""
    with patch.object(sci, "_get_questions", return_value=[]):
        resp = client.post("/science/capability-propensity",
                           json={"model_id": seeded_db["model_id"],
                                 "benchmark_id": seeded_db["bench_id"]})
    assert resp.status_code == 422


def test_capability_propensity_408_timeout(client, seeded_db):
    """Lines 192-193."""
    import asyncio
    mock_engine = MagicMock()
    mock_engine.run = AsyncMock(side_effect=asyncio.TimeoutError())
    with patch.object(sci, "_get_questions", return_value=[{"question": "Q?", "expected": "A"}]), \
         patch.object(sci, "CapabilityPropensityEngine", return_value=mock_engine):
        resp = client.post("/science/capability-propensity",
                           json={"model_id": seeded_db["model_id"],
                                 "benchmark_id": seeded_db["bench_id"]})
    assert resp.status_code == 408


def test_capability_propensity_success(client, seeded_db):
    """Lines 195-251 — normal benchmark (no persuasion)."""
    report = _make_cap_prop_report()
    mock_engine = MagicMock()
    mock_engine.run = AsyncMock(return_value=report)
    with patch.object(sci, "_get_questions", return_value=[{"question": "Q?", "expected": "A"}]), \
         patch.object(sci, "CapabilityPropensityEngine", return_value=mock_engine):
        resp = client.post("/science/capability-propensity",
                           json={"model_id": seeded_db["model_id"],
                                 "benchmark_id": seeded_db["bench_id"]})
    assert resp.status_code == 200
    data = resp.json()
    assert "scores" in data
    assert data["model_name"] == "TestModel"


def test_capability_propensity_persuasion_benchmark(client, seeded_db):
    """Lines 241-250 — persuasion benchmark adds extra scores."""
    report = _make_cap_prop_report()
    mock_engine = MagicMock()
    mock_engine.run = AsyncMock(return_value=report)
    with patch.object(sci, "_get_questions", return_value=[{"question": "Q?", "expected": "A",
                                                             "elicitation_variant": "roleplay"}]), \
         patch.object(sci, "CapabilityPropensityEngine", return_value=mock_engine):
        resp = client.post("/science/capability-propensity",
                           json={"model_id": seeded_db["model_id"],
                                 "benchmark_id": seeded_db["bench_persuasion_id"]})
    assert resp.status_code == 200
    data = resp.json()
    # Persuasion branch adds manipulation_score to scores
    assert "manipulation_score" in data["scores"]


# ── GET /science/capability-propensity/runs ────────────────────────────────────

def test_cap_prop_runs_empty(client, seeded_db):
    """Lines 265-323 — model with no runs."""
    resp = client.get("/science/capability-propensity/runs?model_id=9999")
    assert resp.status_code == 200
    data = resp.json()
    assert data["capability"]["n_runs"] == 0


def test_cap_prop_runs_with_data(client, seeded_db):
    """Lines 265-323 — model with completed runs."""
    resp = client.get(f"/science/capability-propensity/runs?model_id={seeded_db['model_id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert "capability" in data
    assert "propensity" in data


def test_cap_prop_runs_with_benchmark_filter(client, seeded_db):
    resp = client.get(
        f"/science/capability-propensity/runs?model_id={seeded_db['model_id']}"
        f"&benchmark_id={seeded_db['bench_id']}"
    )
    assert resp.status_code == 200


# ── POST /science/mech-interp/validate ────────────────────────────────────────

def _make_mech_interp_report():
    cot = MagicMock()
    cot.question = "Q?"
    cot.cot_consistent = True
    cot.cot_answer_mismatch = False
    cot.reasoning_quality = 0.8
    cot.consistency_score = 0.9

    para = MagicMock()
    para.original_question = "Original question text"
    para.agreement_rate = 0.9
    para.invariant = True

    report = MagicMock()
    report.model_name = "TestModel"
    report.benchmark_name = "TestBench"
    report.n_probes = 1
    report.validation_signal = "supports"
    report.confidence_adjustment = 0.05
    report.interpretation = "CoT consistent"
    report.cot_consistency_rate = 0.9
    report.cot_answer_mismatch_rate = 0.1
    report.cot_results = [cot]
    report.paraphrase_invariance_rate = 0.9
    report.paraphrase_results = [para]
    report.stated_confidence_accuracy = 0.8
    report.overconfidence_rate = 0.1
    report.limitations = ["Black-box only"]
    report.references = ["Nanda 2025"]
    report.total_tokens = 50
    report.total_cost_usd = 0.005
    return report


def test_mech_interp_404_model(client):
    """Line 353-355."""
    resp = client.post("/science/mech-interp/validate",
                       json={"model_id": 9999, "benchmark_id": 1})
    assert resp.status_code == 404


def test_mech_interp_404_benchmark(client, seeded_db):
    resp = client.post("/science/mech-interp/validate",
                       json={"model_id": seeded_db["model_id"], "benchmark_id": 9999})
    assert resp.status_code == 404


def test_mech_interp_422_no_questions(client, seeded_db):
    """Line 362."""
    with patch.object(sci, "_get_questions", return_value=[]):
        resp = client.post("/science/mech-interp/validate",
                           json={"model_id": seeded_db["model_id"],
                                 "benchmark_id": seeded_db["bench_id"]})
    assert resp.status_code == 422


def test_mech_interp_408_timeout(client, seeded_db):
    """Lines 371-372."""
    import asyncio
    mock_validator = MagicMock()
    mock_validator.run = AsyncMock(side_effect=asyncio.TimeoutError())
    with patch.object(sci, "_get_questions", return_value=[{"question": "Q?", "expected": "A"}]), \
         patch.object(sci, "MechInterpValidator", return_value=mock_validator):
        resp = client.post("/science/mech-interp/validate",
                           json={"model_id": seeded_db["model_id"],
                                 "benchmark_id": seeded_db["bench_id"]})
    assert resp.status_code == 408


def test_mech_interp_success(client, seeded_db):
    """Lines 374-418."""
    report = _make_mech_interp_report()
    mock_validator = MagicMock()
    mock_validator.run = AsyncMock(return_value=report)
    with patch.object(sci, "_get_questions", return_value=[{"question": "Q?", "expected": "A"}]), \
         patch.object(sci, "MechInterpValidator", return_value=mock_validator):
        resp = client.post("/science/mech-interp/validate",
                           json={"model_id": seeded_db["model_id"],
                                 "benchmark_id": seeded_db["bench_id"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["validation"]["signal"] == "supports"
    assert "cot_analysis" in data


# ── GET /science/contamination/run/{run_id} ────────────────────────────────────

def test_contamination_run_404(client):
    """Line 433-435."""
    resp = client.get("/science/contamination/run/9999")
    assert resp.status_code == 404


def test_contamination_run_success(client, seeded_db):
    """Lines 436-458."""
    mock_analysis = {
        "contamination_score": 0.1,
        "risk": "low",
        "signals": [],
        "n_items": 5,
    }
    with patch.object(sci, "analyze_contamination", return_value=mock_analysis):
        resp = client.get(f"/science/contamination/run/{seeded_db['run_id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == seeded_db["run_id"]
    assert "contamination_score" in data


# ── GET /science/contamination/campaign/{campaign_id} ─────────────────────────

def test_contamination_campaign_404(client):
    """Line 472-473."""
    resp = client.get("/science/contamination/campaign/9999")
    assert resp.status_code == 404


def test_contamination_campaign_success(client, seeded_db):
    """Lines 475-531."""
    mock_analysis = {"contamination_score": 0.05, "risk": "low", "signals": []}
    with patch.object(sci, "analyze_contamination", return_value=mock_analysis):
        resp = client.get(f"/science/contamination/campaign/{seeded_db['campaign_id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["campaign_id"] == seeded_db["campaign_id"]
    assert "summary" in data


# ── GET /science/validity/benchmark/{benchmark_id} ────────────────────────────

def test_validity_404(client):
    """Line 547-549."""
    resp = client.get("/science/validity/benchmark/9999")
    assert resp.status_code == 404


def test_validity_success_small_samples(client, db_engine):
    """Lines 551-628 — sample size < 20 triggers issues."""
    with Session(db_engine) as s:
        bench = Benchmark(name="tiny-bench", type=BenchmarkType.SAFETY,
                          num_samples=10, source="public", metric="accuracy")
        s.add(bench)
        s.commit()
        s.refresh(bench)
        bid = bench.id

    resp = client.get(f"/science/validity/benchmark/{bid}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["issues"]) > 0
    assert data["validity_grade"] in ("C", "D")


def test_validity_success_medium_samples(client, db_engine):
    """Lines 562-563 — 20 < n < 50 triggers warning."""
    with Session(db_engine) as s:
        bench = Benchmark(name="medium-bench", type=BenchmarkType.SAFETY,
                          num_samples=35, source="inesia", metric="accuracy")
        s.add(bench)
        s.commit()
        s.refresh(bench)
        bid = bench.id

    resp = client.get(f"/science/validity/benchmark/{bid}")
    assert resp.status_code == 200
    data = resp.json()
    assert any("small" in w.lower() for w in data["warnings"])


def test_validity_no_dataset(client, db_engine):
    """Lines 565-567 — no dataset_path warning."""
    with Session(db_engine) as s:
        bench = Benchmark(name="no-dataset-bench", type=BenchmarkType.CUSTOM,
                          num_samples=100, source="community", dataset_path=None)
        s.add(bench)
        s.commit()
        s.refresh(bench)
        bid = bench.id

    resp = client.get(f"/science/validity/benchmark/{bid}")
    assert resp.status_code == 200
    data = resp.json()
    assert any("No dataset" in w for w in data["warnings"])


def test_validity_missing_file(client, db_engine):
    """Lines 569-573 — dataset_path set but file missing."""
    with Session(db_engine) as s:
        bench = Benchmark(name="missing-file-bench", type=BenchmarkType.CUSTOM,
                          num_samples=100, source="inesia",
                          dataset_path="nonexistent/file.json")
        s.add(bench)
        s.commit()
        s.refresh(bench)
        bid = bench.id

    resp = client.get(f"/science/validity/benchmark/{bid}")
    assert resp.status_code == 200
    data = resp.json()
    assert any("not found" in i.lower() for i in data["issues"])


def test_validity_safety_accuracy_warning(client, db_engine):
    """Lines 587-593 — safety benchmark with accuracy metric."""
    with Session(db_engine) as s:
        bench = Benchmark(name="safety-accuracy-bench", type=BenchmarkType.SAFETY,
                          num_samples=100, source="inesia", metric="accuracy")
        s.add(bench)
        s.commit()
        s.refresh(bench)
        bid = bench.id

    resp = client.get(f"/science/validity/benchmark/{bid}")
    assert resp.status_code == 200


# ── POST /science/compositional-risk ──────────────────────────────────────────

def _make_comp_risk_profile():
    dr = MagicMock()
    dr.domain = "deception"
    dr.raw_score = 0.7
    dr.severity_weight = 0.9
    dr.weighted_risk = 0.63
    dr.interpretation = "High risk"

    combo = MagicMock()
    combo.domains = ["deception", "persuasion"]
    combo.multiplier = 1.5
    combo.reason = "Dangerous combo"

    profile = MagicMock()
    profile.model_name = "TestModel"
    profile.autonomy_level = 2
    profile.tools = ["web_search"]
    profile.memory_type = "session"
    profile.baseline_risk = 0.63
    profile.autonomy_multiplier = 1.2
    profile.tool_multiplier = 1.1
    profile.memory_multiplier = 1.0
    profile.combo_multiplier = 1.5
    profile.composite_risk_score = 0.85
    profile.risk_level = "critical"
    profile.dominant_threat_vector = "deception"
    profile.autonomy_recommendation = "Restrict"
    profile.domain_risks = [dr]
    profile.dangerous_combos_triggered = [combo]
    profile.key_concerns = ["High deception"]
    profile.mitigation_priorities = ["Monitor"]
    profile.caveat = "Black-box only"
    return profile


def _make_comp_risk_contract_profile():
    cp = MagicMock()
    cp.system_id = "sys-001"
    cp.overall_risk_level = "critical"
    cp.component_risks = {}
    cp.composition_multiplier = 1.5
    cp.dominant_threat_vector = "deception"
    cp.mitigation_recommendations = []
    cp.autonomy_certification = "Reject"
    return cp


def test_compositional_risk_success(client):
    """Lines 652-716."""
    from eval_engine.compositional_risk import (
        CompositionalRiskEngine, CompositionalRiskModel, normalize_autonomy_level
    )
    profile = _make_comp_risk_profile()
    contract = _make_comp_risk_contract_profile()

    mock_engine = MagicMock()
    mock_engine.compute.return_value = profile

    with patch("eval_engine.compositional_risk.CompositionalRiskEngine", return_value=mock_engine), \
         patch("eval_engine.compositional_risk.normalize_autonomy_level", return_value=2), \
         patch.object(CompositionalRiskModel, "to_system_risk_profile", return_value=contract):
        resp = client.post("/science/compositional-risk", json={
            "model_name": "TestModel",
            "domain_scores": {"deception": 0.7},
            "propensity_scores": {"deception": 0.5},
            "autonomy_level": "L2",
            "tools": ["web_search"],
            "memory_type": "session",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_name"] == "TestModel"
    assert "scores" in data


def test_compositional_risk_invalid_autonomy(client):
    """Lines 659-661 — ValueError from invalid autonomy level."""
    with patch("eval_engine.compositional_risk.normalize_autonomy_level",
               side_effect=ValueError("Invalid level")):
        resp = client.post("/science/compositional-risk", json={
            "model_name": "TestModel",
            "domain_scores": {},
            "autonomy_level": "L99",
        })
    assert resp.status_code == 422


# ── GET /science/compositional-risk/domains ───────────────────────────────────

def test_get_risk_domains(client):
    """Lines 722-728."""
    resp = client.get("/science/compositional-risk/domains")
    assert resp.status_code == 200
    data = resp.json()
    assert "domains" in data
    assert "autonomy_multipliers" in data


# ── GET /science/failure-clusters/campaign/{campaign_id} ──────────────────────

def _make_cluster_report():
    cluster = MagicMock()
    cluster.cluster_id = "c1"
    cluster.name = "Hallucination cluster"
    cluster.failure_type = "hallucination"
    cluster.n_instances = 3
    cluster.is_novel = True
    cluster.reproducibility_score = 0.8
    cluster.cross_model = True
    cluster.affected_models = ["TestModel"]
    cluster.common_keywords = ["wrong"]
    cluster.hypothesis = "Systematic hallucination"
    cluster.severity = "high"
    cluster.recommended_benchmark = "HallucinationBench"
    cluster.representative_traces = ["trace1"]
    cluster.size = 3
    cluster.failure_family = "hallucination"
    cluster.causal_hypothesis = "Training data"
    cluster.representative_prompts = ["Q?"]

    known = MagicMock()
    known.cluster_id = "k1"
    known.name = "Known pattern"
    known.failure_type = "reasoning_collapse"
    known.n_instances = 2
    known.severity = "low"
    known.common_keywords = ["math"]
    known.hypothesis = "Arithmetic failure"
    known.size = 2
    known.failure_family = "reasoning"
    known.causal_hypothesis = "Numerical training"

    report = MagicMock()
    report.campaign_id = 1
    report.n_failures = 3
    report.n_clusters = 2
    report.failure_genome_version = "1.0.0"
    report.summary = "2 clusters found"
    report.alerts = []
    report.novel_clusters = [cluster]
    report.known_clusters = [known]
    report.cross_model_patterns = []
    report.top_emerging_risk = "hallucination"
    return report


def test_failure_clusters_422_no_failures(client):
    """Lines 761-762 — no low-score results."""
    resp = client.get("/science/failure-clusters/campaign/9999?min_cluster_size=2")
    assert resp.status_code == 422


def test_failure_clusters_success(client, db_engine, seeded_db):
    """Lines 763-834."""
    from eval_engine.failure_clustering import FailureClusteringEngine

    report = _make_cluster_report()
    mock_cluster_engine = MagicMock()
    mock_cluster_engine.discover.return_value = report

    with patch("eval_engine.failure_clustering.FailureClusteringEngine",
               return_value=mock_cluster_engine):
        resp = client.get(
            f"/science/failure-clusters/campaign/{seeded_db['campaign_id']}"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "n_clusters" in data
    assert "novel_clusters" in data
    assert "known_clusters" in data
