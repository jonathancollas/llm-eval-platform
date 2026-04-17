"""Tests for Capability Taxonomy, Trajectory Analysis, and Cross-Benchmark modules."""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from eval_engine.capability_taxonomy import (
    CAPABILITY_ONTOLOGY,
    CapabilityTaxonomyEngine,
    CapabilityScore,
    CapabilityNode,
    CapabilityProfile,
)
from eval_engine.trajectory_analysis import (
    TrajectoryAnalysisEngine,
    TrajectoryAnalysisResult,
    LoopDetection,
)
from eval_engine.cross_benchmark import (
    CrossBenchmarkAnalyzer,
    NormalizedScore,
    GeneralizationReport,
    z_normalize,
    percentile_rank,
    generalization_index,
    pearson_correlation,
)


# ---------------------------------------------------------------------------
# CAPABILITY_ONTOLOGY structure
# ---------------------------------------------------------------------------

def test_ontology_has_7_domains():
    assert len(CAPABILITY_ONTOLOGY) == 7

def test_each_domain_has_sub_capabilities():
    for domain, data in CAPABILITY_ONTOLOGY.items():
        assert "sub_capabilities" in data, f"Domain '{domain}' missing sub_capabilities"
        assert len(data["sub_capabilities"]) > 0


# ---------------------------------------------------------------------------
# CapabilityTaxonomyEngine
# ---------------------------------------------------------------------------

def test_get_node_existing():
    engine = CapabilityTaxonomyEngine()
    node = engine.get_node("reasoning", "capability", "logical")
    assert node is not None
    assert isinstance(node, CapabilityNode)
    assert node.domain == "reasoning"
    assert node.sub_capability == "logical"

def test_get_node_missing_returns_none():
    engine = CapabilityTaxonomyEngine()
    node = engine.get_node("nonexistent_domain", "capability", "foo")
    assert node is None

def test_list_domains_returns_7():
    engine = CapabilityTaxonomyEngine()
    domains = engine.list_domains()
    assert len(domains) == 7

def test_infer_capabilities_safety_refusals():
    engine = CapabilityTaxonomyEngine()
    results = engine.infer_capabilities_from_benchmark("Safety Refusals")
    domains_found = [r[0] for r in results]
    assert "safety" in domains_found

def test_compute_profile_coverage_pct():
    engine = CapabilityTaxonomyEngine()
    scores = [
        CapabilityScore(model_name="m1", domain="reasoning", capability="reasoning", sub_capability="logical", score=0.8),
        CapabilityScore(model_name="m1", domain="safety", capability="safety", sub_capability="refusal", score=0.9),
        CapabilityScore(model_name="m1", domain="knowledge", capability="knowledge", sub_capability="factual", score=0.7),
    ]
    profile = engine.compute_profile("m1", scores)
    assert isinstance(profile, CapabilityProfile)
    assert profile.coverage_pct > 0

def test_compute_profile_strongest_weakest():
    engine = CapabilityTaxonomyEngine()
    scores = [
        CapabilityScore(model_name="m1", domain="reasoning", capability="reasoning", sub_capability="logical", score=0.9),
        CapabilityScore(model_name="m1", domain="safety", capability="safety", sub_capability="refusal", score=0.3),
    ]
    profile = engine.compute_profile("m1", scores)
    assert profile.strongest_domain == "reasoning"
    assert profile.weakest_domain == "safety"

def test_find_coverage_gaps_partial_scores():
    engine = CapabilityTaxonomyEngine()
    # Only cover one sub-capability — rest are gaps
    scores = [
        CapabilityScore(model_name="m1", domain="reasoning", capability="reasoning", sub_capability="logical", score=0.8),
    ]
    gaps = engine.find_coverage_gaps("m1", scores)
    assert isinstance(gaps, list)
    assert len(gaps) > 0
    # "reasoning/logical" should NOT be in gaps
    gap_keys = {(g.domain, g.sub_capability) for g in gaps}
    assert ("reasoning", "logical") not in gap_keys
    # Some other sub-cap should be present
    assert any(g.domain == "safety" for g in gaps)


# ---------------------------------------------------------------------------
# TrajectoryAnalysisEngine
# ---------------------------------------------------------------------------

def test_detect_loops_no_loop():
    engine = TrajectoryAnalysisEngine()
    steps = [
        {"input_text": "step1", "tool_name": "tool_a"},
        {"input_text": "step2", "tool_name": "tool_b"},
        {"input_text": "step3", "tool_name": "tool_c"},
    ]
    result = engine.detect_loops(steps)
    assert result.detected is False

def test_detect_loops_with_loop():
    engine = TrajectoryAnalysisEngine()
    steps = [
        {"input_text": "do something", "tool_name": "search"},
        {"input_text": "do other", "tool_name": "calc"},
        {"input_text": "do something", "tool_name": "search"},  # repeat of step 0
    ]
    result = engine.detect_loops(steps)
    assert result.detected is True
    assert result.loop_type == "exact"

def test_detect_retry_patterns():
    engine = TrajectoryAnalysisEngine()
    steps = [
        {"tool_name": "api_call", "tool_success": False, "error_type": "timeout"},
        {"tool_name": "api_call", "tool_success": False, "error_type": "timeout"},
        {"tool_name": "api_call", "tool_success": True},
    ]
    retries = engine.detect_retry_patterns(steps)
    assert len(retries) > 0
    assert retries[0].detected is True
    assert retries[0].n_retries >= 1

def test_compute_autonomy_all_success():
    engine = TrajectoryAnalysisEngine()
    steps = [{"tool_success": True} for _ in range(5)]
    score = engine.compute_autonomy_score(steps)
    assert score == 1.0

def test_compute_autonomy_all_fail():
    engine = TrajectoryAnalysisEngine()
    steps = [{"tool_success": False, "error_type": "err"} for _ in range(5)]
    score = engine.compute_autonomy_score(steps)
    assert score == 0.0

def test_compute_adaptivity_error_then_success():
    engine = TrajectoryAnalysisEngine()
    steps = [
        {"tool_success": False},
        {"tool_success": True},
    ]
    score = engine.compute_adaptivity_score(steps)
    assert score > 0

def test_analyze_steps_returns_result():
    engine = TrajectoryAnalysisEngine()
    steps = [
        {"input_text": "task1", "tool_name": "search", "tool_success": True},
        {"input_text": "task2", "tool_name": "calc", "tool_success": True},
    ]
    result = engine.analyze_steps(steps)
    assert isinstance(result, TrajectoryAnalysisResult)
    assert result.steps_analyzed == 2
    assert hasattr(result, "loop_detection")
    assert hasattr(result, "autonomy_score")
    assert hasattr(result, "adaptivity_score")
    assert hasattr(result, "efficiency_score")
    assert hasattr(result, "overall_quality_score")
    assert hasattr(result, "failure_types")
    assert hasattr(result, "recommendations")


# ---------------------------------------------------------------------------
# Cross-Benchmark functions
# ---------------------------------------------------------------------------

def test_z_normalize_mean_near_zero():
    scores = {"a": 0.5, "b": 0.7, "c": 0.9, "d": 0.3}
    zs = z_normalize(scores)
    mean_z = sum(zs.values()) / len(zs)
    assert abs(mean_z) < 1e-9

def test_percentile_rank_top_score():
    all_scores = [0.1, 0.3, 0.5, 0.7, 0.9]
    pr = percentile_rank(0.9, all_scores)
    assert pr == 100.0

def test_generalization_index_identical_scores():
    scores = [0.8, 0.8, 0.8, 0.8]
    gi = generalization_index(scores)
    assert gi >= 0.99

def test_pearson_correlation_monotone():
    x = [1, 2, 3, 4, 5]
    y = [2, 4, 6, 8, 10]
    r = pearson_correlation(x, y)
    assert abs(r - 1.0) < 1e-4


# ---------------------------------------------------------------------------
# CrossBenchmarkAnalyzer
# ---------------------------------------------------------------------------

def test_normalize_scores_returns_normalized_score_list():
    analyzer = CrossBenchmarkAnalyzer()
    runs = [
        {"model_name": "gpt4", "benchmark_name": "MMLU", "score": 0.85},
        {"model_name": "claude", "benchmark_name": "MMLU", "score": 0.78},
        {"model_name": "llama", "benchmark_name": "MMLU", "score": 0.65},
    ]
    result = analyzer.normalize_scores(runs)
    assert len(result) == 3
    assert all(isinstance(r, NormalizedScore) for r in result)
    assert all(hasattr(r, "z_score") for r in result)
    assert all(hasattr(r, "percentile_rank") for r in result)

def test_generate_report_returns_generalization_report():
    analyzer = CrossBenchmarkAnalyzer()
    runs = [
        {"model_name": "gpt4", "benchmark_name": "MMLU", "score": 0.85},
        {"model_name": "gpt4", "benchmark_name": "GSM8K", "score": 0.80},
        {"model_name": "gpt4", "benchmark_name": "ARC", "score": 0.90},
    ]
    report = analyzer.generate_report("gpt4", runs)
    assert isinstance(report, GeneralizationReport)
    assert report.model_name == "gpt4"
    assert len(report.benchmarks_evaluated) == 3
    assert 0.0 <= report.generalization_index <= 1.0
    assert report.best_benchmark == "ARC"
    assert report.worst_benchmark == "GSM8K"
