"""
Comprehensive tests for Milestone 1 — Statistical Rigor.
Covers statistical_tests, reproducibility_engine, and human_calibration.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import pytest

from eval_engine.statistical_tests import (
    mcnemar_test,
    permutation_test,
    bonferroni_correction,
    benjamini_hochberg_correction,
    cohens_d,
    power_analysis,
    compare_runs,
    _mean,
    _std,
)
from eval_engine.reproducibility_engine import (
    hash_config,
    hash_dataset,
    generate_fingerprint,
    validate_reproducibility,
    capture_environment,
)
from eval_engine.human_calibration import (
    AnnotationItem,
    cohens_kappa,
    fleiss_kappa,
    krippendorff_alpha_ordinal,
    spearman_correlation,
    compute_calibration_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_mean_empty(self):
        assert _mean([]) == 0.0

    def test_mean_values(self):
        assert _mean([1, 2, 3]) == 2.0

    def test_std_single(self):
        assert _std([5]) == 0.0

    def test_std_values(self):
        result = _std([2, 4, 4, 4, 5, 5, 7, 9])
        assert abs(result - 2.138) < 0.01


# ---------------------------------------------------------------------------
# McNemar test
# ---------------------------------------------------------------------------

class TestMcnemarTest:
    def test_perfect_agreement_not_significant(self):
        # Both models identical → no discordant pairs
        scores_a = [0.9, 0.8, 0.7, 0.6, 0.55]
        scores_b = [0.9, 0.8, 0.7, 0.6, 0.55]
        result = mcnemar_test(scores_a, scores_b)
        assert result["b"] == 0
        assert result["c"] == 0
        assert result["p_value"] == 1.0
        assert result["significant"] is False
        assert "No discordant pairs" in result["interpretation"]

    def test_large_discordance_significant(self):
        # A always correct, B always wrong → large discordance
        scores_a = [0.9] * 50
        scores_b = [0.1] * 50
        result = mcnemar_test(scores_a, scores_b)
        assert result["significant"] is True
        assert result["p_value"] < 0.05
        assert result["b"] == 50
        assert result["c"] == 0

    def test_returns_required_keys(self):
        result = mcnemar_test([0.8, 0.2], [0.2, 0.8])
        for key in ("statistic", "p_value", "b", "c", "significant", "interpretation"):
            assert key in result

    def test_moderate_discordance(self):
        # b=10, c=2 → should be significant
        a = [0.9] * 10 + [0.1] * 2 + [0.9] * 8
        b = [0.1] * 10 + [0.9] * 2 + [0.9] * 8
        result = mcnemar_test(a, b)
        assert result["b"] == 10
        assert result["c"] == 2

    def test_threshold_custom(self):
        scores_a = [0.6, 0.4]
        scores_b = [0.4, 0.6]
        result = mcnemar_test(scores_a, scores_b, threshold=0.5)
        assert result["b"] == 1
        assert result["c"] == 1


# ---------------------------------------------------------------------------
# Permutation test
# ---------------------------------------------------------------------------

class TestPermutationTest:
    def test_identical_distributions_not_significant(self):
        scores = [0.5, 0.6, 0.7, 0.8, 0.4, 0.55, 0.65, 0.75]
        result = permutation_test(scores, scores, n_permutations=500, seed=0)
        assert result["significant"] is False
        # p_value should be high for identical distributions
        assert result["p_value"] >= 0.5

    def test_very_different_distributions_significant(self):
        scores_a = [0.9, 0.95, 0.85, 0.92, 0.88, 0.91, 0.93, 0.87]
        scores_b = [0.1, 0.05, 0.15, 0.08, 0.12, 0.09, 0.07, 0.13]
        result = permutation_test(scores_a, scores_b, n_permutations=1000, seed=42)
        assert result["significant"] is True
        assert result["p_value"] < 0.05

    def test_returns_required_keys(self):
        result = permutation_test([0.5, 0.6], [0.4, 0.5])
        for key in ("observed_diff", "p_value", "n_permutations", "significant", "interpretation"):
            assert key in result

    def test_observed_diff_correct(self):
        a = [1.0, 1.0]
        b = [0.0, 0.0]
        result = permutation_test(a, b, n_permutations=100, seed=1)
        assert result["observed_diff"] == 1.0

    def test_seed_deterministic(self):
        a = [0.7, 0.6, 0.8]
        b = [0.4, 0.5, 0.3]
        r1 = permutation_test(a, b, seed=99)
        r2 = permutation_test(a, b, seed=99)
        assert r1["p_value"] == r2["p_value"]


# ---------------------------------------------------------------------------
# Bonferroni correction
# ---------------------------------------------------------------------------

class TestBonferroniCorrection:
    def test_five_p_values_small_rejected(self):
        p_values = [0.001, 0.01, 0.03, 0.04, 0.5]
        result = bonferroni_correction(p_values, alpha=0.05)
        # corrected_alpha = 0.05/5 = 0.01
        assert abs(result["corrected_alpha"] - 0.01) < 1e-9
        assert result["rejected"][0] is True   # 0.001 <= 0.01
        assert result["rejected"][1] is True   # 0.01 <= 0.01
        assert result["rejected"][2] is False  # 0.03 > 0.01
        assert result["rejected"][3] is False
        assert result["rejected"][4] is False
        assert result["n_rejected"] == 2

    def test_adjusted_p_values_capped_at_1(self):
        p_values = [0.5, 0.8]
        result = bonferroni_correction(p_values, alpha=0.05)
        assert all(p <= 1.0 for p in result["adjusted_p_values"])

    def test_returns_required_keys(self):
        result = bonferroni_correction([0.01, 0.05])
        for key in ("corrected_alpha", "rejected", "adjusted_p_values", "n_rejected"):
            assert key in result

    def test_all_significant(self):
        p_values = [0.001, 0.002]
        result = bonferroni_correction(p_values, alpha=0.05)
        assert result["n_rejected"] == 2


# ---------------------------------------------------------------------------
# Benjamini-Hochberg correction
# ---------------------------------------------------------------------------

class TestBenjaminiHochbergCorrection:
    def test_more_rejections_than_bonferroni(self):
        p_values = [0.001, 0.008, 0.039, 0.041, 0.5]
        bh = benjamini_hochberg_correction(p_values, alpha=0.05)
        bonf = bonferroni_correction(p_values, alpha=0.05)
        assert bh["n_rejected"] >= bonf["n_rejected"]

    def test_returns_required_keys(self):
        result = benjamini_hochberg_correction([0.01, 0.05])
        for key in ("rejected", "adjusted_p_values", "n_rejected", "fdr_threshold"):
            assert key in result

    def test_adjusted_p_capped_at_1(self):
        p_values = [0.9, 0.95, 0.99]
        result = benjamini_hochberg_correction(p_values, alpha=0.05)
        assert all(p <= 1.0 for p in result["adjusted_p_values"])

    def test_small_p_rejected(self):
        p_values = [0.001, 0.8, 0.9]
        result = benjamini_hochberg_correction(p_values, alpha=0.05)
        assert result["rejected"][0] is True

    def test_none_rejected_when_all_large(self):
        p_values = [0.5, 0.6, 0.7]
        result = benjamini_hochberg_correction(p_values, alpha=0.05)
        assert result["n_rejected"] == 0


# ---------------------------------------------------------------------------
# Cohen's d
# ---------------------------------------------------------------------------

class TestCohensD:
    def test_large_effect(self):
        # Proper large effect: groups with clear separation and within-group variance
        a = [0.9, 0.85, 0.92, 0.88, 0.91, 0.87, 0.93, 0.86, 0.90, 0.89]
        b = [0.1, 0.15, 0.08, 0.12, 0.09, 0.13, 0.07, 0.14, 0.11, 0.10]
        result = cohens_d(a, b)
        assert result["magnitude"] == "large"
        assert abs(result["d"]) > 0.8

    def test_negligible_effect_same_scores(self):
        scores = [0.5, 0.6, 0.7, 0.8, 0.55]
        result = cohens_d(scores, scores)
        assert result["d"] == 0.0
        assert result["magnitude"] == "negligible"

    def test_returns_required_keys(self):
        result = cohens_d([0.8, 0.9, 0.7], [0.2, 0.3, 0.1])
        for key in ("d", "magnitude", "interpretation"):
            assert key in result

    def test_small_effect(self):
        # Wide variance → pooled std dominates → small effect size
        a = [0.3, 0.5, 0.7, 0.2, 0.8, 0.4, 0.6, 0.1, 0.9, 0.5]
        b = [0.2, 0.4, 0.6, 0.1, 0.7, 0.3, 0.5, 0.0, 0.8, 0.4]
        result = cohens_d(a, b)
        assert result["magnitude"] in ("small", "negligible")

    def test_negative_d_when_b_greater(self):
        result = cohens_d([0.3, 0.3, 0.3], [0.7, 0.7, 0.7])
        assert result["d"] < 0


# ---------------------------------------------------------------------------
# Power analysis
# ---------------------------------------------------------------------------

class TestPowerAnalysis:
    def test_effect_size_0_5_in_range(self):
        result = power_analysis(0.5)
        assert 20 <= result["required_n"] <= 200

    def test_zero_effect_returns_9999(self):
        result = power_analysis(0.0)
        assert result["required_n"] == 9999

    def test_large_effect_needs_fewer_samples(self):
        small = power_analysis(0.2)
        large = power_analysis(0.8)
        assert large["required_n"] < small["required_n"]

    def test_returns_required_keys(self):
        result = power_analysis(0.5)
        for key in ("required_n", "effect_size", "alpha", "power", "interpretation"):
            assert key in result

    def test_interpretation_contains_n(self):
        result = power_analysis(0.5)
        assert str(result["required_n"]) in result["interpretation"]


# ---------------------------------------------------------------------------
# compare_runs
# ---------------------------------------------------------------------------

class TestCompareRuns:
    def test_returns_overall_verdict_key(self):
        a = [0.9] * 20
        b = [0.1] * 20
        result = compare_runs(a, b)
        assert "overall_verdict" in result

    def test_significant_when_very_different(self):
        a = [0.95] * 30
        b = [0.05] * 30
        result = compare_runs(a, b)
        assert result["overall_verdict"] == "significant"

    def test_not_significant_when_same(self):
        scores = [0.5, 0.6, 0.7, 0.55, 0.65, 0.45, 0.5, 0.6, 0.7, 0.55]
        result = compare_runs(scores, scores)
        assert result["overall_verdict"] == "not_significant"

    def test_contains_all_test_results(self):
        a = [0.8, 0.7, 0.9, 0.6]
        b = [0.2, 0.3, 0.1, 0.4]
        result = compare_runs(a, b)
        assert "mcnemar" in result
        assert "permutation" in result
        assert "effect_size" in result


# ---------------------------------------------------------------------------
# hash_config / hash_dataset
# ---------------------------------------------------------------------------

class TestHashing:
    def test_hash_config_deterministic(self):
        cfg = {"model": "gpt-4", "temperature": 0.7, "max_tokens": 256}
        assert hash_config(cfg) == hash_config(cfg)

    def test_hash_config_different_inputs(self):
        cfg_a = {"model": "gpt-4"}
        cfg_b = {"model": "claude-3"}
        assert hash_config(cfg_a) != hash_config(cfg_b)

    def test_hash_config_key_order_invariant(self):
        cfg_a = {"a": 1, "b": 2}
        cfg_b = {"b": 2, "a": 1}
        assert hash_config(cfg_a) == hash_config(cfg_b)

    def test_hash_dataset_deterministic(self):
        items = [{"id": 1, "text": "hello"}, {"id": 2, "text": "world"}]
        assert hash_dataset(items) == hash_dataset(items)

    def test_hash_dataset_different_inputs(self):
        a = [{"id": 1}]
        b = [{"id": 2}]
        assert hash_dataset(a) != hash_dataset(b)

    def test_hash_is_64_char_hex(self):
        h = hash_config({"key": "value"})
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# generate_fingerprint / validate_reproducibility
# ---------------------------------------------------------------------------

class TestFingerprint:
    def _make_fp(self, seed=42, temperature=0.0):
        return generate_fingerprint(
            campaign_config={"name": "test"},
            model_configs=[{"model": "gpt-4"}],
            benchmark_configs=[{"bench": "mmlu"}],
            seed=seed,
            temperature=temperature,
        )

    def test_fingerprint_hash_is_64_char_hex(self):
        fp = self._make_fp()
        assert len(fp.fingerprint_hash) == 64
        assert all(c in "0123456789abcdef" for c in fp.fingerprint_hash)

    def test_same_config_same_hash(self):
        fp_a = self._make_fp()
        fp_b = self._make_fp()
        assert fp_a.config_hash == fp_b.config_hash
        assert fp_a.dataset_hash == fp_b.dataset_hash
        assert fp_a.prompt_hash == fp_b.prompt_hash

    def test_validate_same_fingerprints_reproducible(self):
        fp_a = self._make_fp()
        fp_b = self._make_fp()
        result = validate_reproducibility(fp_a, fp_b)
        assert result["reproducible"] is True
        assert result["identical"] is True
        assert result["differences"] == []

    def test_validate_different_seed_not_reproducible(self):
        fp_a = self._make_fp(seed=42)
        fp_b = self._make_fp(seed=99)
        result = validate_reproducibility(fp_a, fp_b)
        assert result["reproducible"] is False
        assert "seed" in result["differences"]

    def test_validate_different_temperature_not_reproducible(self):
        fp_a = self._make_fp(temperature=0.0)
        fp_b = self._make_fp(temperature=0.7)
        result = validate_reproducibility(fp_a, fp_b)
        assert result["reproducible"] is False
        assert "temperature" in result["differences"]

    def test_fingerprint_stores_seed_and_temperature(self):
        fp = self._make_fp(seed=123, temperature=0.5)
        assert fp.seed == 123
        assert fp.temperature == 0.5


# ---------------------------------------------------------------------------
# Human calibration — cohens_kappa
# ---------------------------------------------------------------------------

class TestCohensKappa:
    def test_perfect_agreement(self):
        scores = [0.1, 0.3, 0.5, 0.7, 0.9]
        assert cohens_kappa(scores, scores) == 1.0

    def test_opposite_ratings_low_kappa(self):
        a = [0.9, 0.9, 0.9, 0.9, 0.9]
        b = [0.1, 0.1, 0.1, 0.1, 0.1]
        result = cohens_kappa(a, b)
        assert result <= 0.0

    def test_empty_returns_zero(self):
        assert cohens_kappa([], []) == 0.0

    def test_partial_agreement(self):
        a = [0.9, 0.1, 0.9, 0.1]
        b = [0.9, 0.9, 0.1, 0.1]
        result = cohens_kappa(a, b)
        assert -1.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# Human calibration — fleiss_kappa
# ---------------------------------------------------------------------------

class TestFleissKappa:
    def test_perfect_agreement(self):
        matrix = [[0.9, 0.9, 0.9], [0.1, 0.1, 0.1], [0.5, 0.5, 0.5]]
        result = fleiss_kappa(matrix)
        assert result == 1.0

    def test_empty_returns_zero(self):
        assert fleiss_kappa([]) == 0.0

    def test_result_in_range(self):
        matrix = [[0.9, 0.1], [0.5, 0.6], [0.3, 0.7]]
        result = fleiss_kappa(matrix)
        assert -1.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# Human calibration — krippendorff_alpha_ordinal
# ---------------------------------------------------------------------------

class TestKrippendorffAlpha:
    def test_identical_ratings_returns_1(self):
        matrix = [[0.5, 0.5, 0.5], [0.8, 0.8, 0.8], [0.2, 0.2, 0.2]]
        result = krippendorff_alpha_ordinal(matrix)
        assert result == 1.0

    def test_empty_returns_zero(self):
        assert krippendorff_alpha_ordinal([]) == 0.0

    def test_result_in_range(self):
        matrix = [[0.9, 0.1], [0.5, 0.6], [0.3, 0.7]]
        result = krippendorff_alpha_ordinal(matrix)
        assert result <= 1.0


# ---------------------------------------------------------------------------
# Human calibration — spearman_correlation
# ---------------------------------------------------------------------------

class TestSpearmanCorrelation:
    def test_monotone_increasing_approx_1(self):
        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]
        result = spearman_correlation(x, y)
        assert abs(result - 1.0) < 1e-6

    def test_reversed_approx_minus_1(self):
        x = [1, 2, 3, 4, 5]
        y = [5, 4, 3, 2, 1]
        result = spearman_correlation(x, y)
        assert abs(result - (-1.0)) < 1e-6

    def test_single_element_returns_zero(self):
        assert spearman_correlation([1], [1]) == 0.0

    def test_result_in_range(self):
        x = [0.1, 0.5, 0.3, 0.9, 0.7]
        y = [0.4, 0.2, 0.8, 0.6, 0.1]
        result = spearman_correlation(x, y)
        assert -1.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# compute_calibration_report
# ---------------------------------------------------------------------------

class TestComputeCalibrationReport:
    def _make_items(self):
        return [
            AnnotationItem("i1", "p1", "r1", "e1", {"ann1": 0.9, "ann2": 0.85}),
            AnnotationItem("i2", "p2", "r2", "e2", {"ann1": 0.3, "ann2": 0.35}),
            AnnotationItem("i3", "p3", "r3", "e3", {"ann1": 0.7, "ann2": 0.75}),
            AnnotationItem("i4", "p4", "r4", "e4", {"ann1": 0.5, "ann2": 0.55}),
        ]

    def test_empty_items_returns_empty_report(self):
        report = compute_calibration_report([], {})
        assert report.n_items == 0
        assert report.reliability_grade == "D"

    def test_high_agreement_grade_a(self):
        items = [
            AnnotationItem(f"i{i}", "", "", "", {"ann1": 0.9, "ann2": 0.9})
            for i in range(5)
        ]
        llm = {f"i{i}": 0.9 for i in range(5)}
        report = compute_calibration_report(items, llm)
        assert report.reliability_grade == "A"
        assert report.cohens_kappa == 1.0

    def test_report_has_correct_n_items(self):
        items = self._make_items()
        report = compute_calibration_report(items, {})
        assert report.n_items == 4
        assert report.n_annotators == 2

    def test_recommendations_for_low_agreement(self):
        items = [
            AnnotationItem("i1", "", "", "", {"ann1": 0.9, "ann2": 0.1}),
            AnnotationItem("i2", "", "", "", {"ann1": 0.1, "ann2": 0.9}),
        ]
        report = compute_calibration_report(items, {"i1": 0.5, "i2": 0.5})
        assert any("training" in r.lower() for r in report.recommendations)

    def test_spearman_high_when_llm_matches_humans(self):
        items = self._make_items()
        llm_scores = {"i1": 0.87, "i2": 0.32, "i3": 0.72, "i4": 0.52}
        report = compute_calibration_report(items, llm_scores)
        assert report.spearman_human_llm > 0.9


# ---------------------------------------------------------------------------
# Security: safe_bench_path path containment
# ---------------------------------------------------------------------------

class TestSafeBenchPath:
    def test_normal_path_is_allowed(self, tmp_path):
        from core.security import safe_bench_path
        result = safe_bench_path(str(tmp_path), "custom/dataset.json")
        assert str(result).startswith(str(tmp_path.resolve()))

    def test_path_traversal_is_rejected(self, tmp_path):
        from fastapi import HTTPException
        from core.security import safe_bench_path
        with pytest.raises(HTTPException) as exc_info:
            safe_bench_path(str(tmp_path), "../../../etc/passwd")
        assert exc_info.value.status_code == 400

    def test_double_dot_in_subdirectory_is_rejected(self, tmp_path):
        from fastapi import HTTPException
        from core.security import safe_bench_path
        with pytest.raises(HTTPException):
            safe_bench_path(str(tmp_path), "custom/../../etc/shadow")

    def test_simple_subpath_allowed(self, tmp_path):
        from core.security import safe_bench_path
        result = safe_bench_path(str(tmp_path), "benchmarks/mmlu.json")
        assert "mmlu.json" in str(result)


# ---------------------------------------------------------------------------
# Confidence engine: correct two-arg call
# ---------------------------------------------------------------------------

class TestConfidenceEngine:
    def test_compute_confidence_requires_run_id_and_scores(self):
        from eval_engine.confidence_engine import compute_confidence
        result = compute_confidence(42, [0.8, 0.9, 0.7, 0.85, 0.75])
        assert result.run_id == 42
        assert 0.0 <= result.ci_lower <= result.ci_upper <= 1.0
        assert result.reliability_grade in ("A", "B", "C", "D")

    def test_compute_confidence_raises_on_empty_scores(self):
        from eval_engine.confidence_engine import compute_confidence
        with pytest.raises(ValueError):
            compute_confidence(1, [])


# ---------------------------------------------------------------------------
# Reproducibility endpoint logic (unit-level, no DB)
# ---------------------------------------------------------------------------

class TestReproducibilityFingerprint:
    def test_same_inputs_produce_same_fingerprint(self):
        cfg = {"model": "gpt-4", "benchmark": "mmlu"}
        models = [{"id": 1, "name": "gpt-4", "provider": "openai"}]
        benches = [{"id": 1, "name": "mmlu", "metric": "accuracy"}]
        fp1 = generate_fingerprint(cfg, models, benches, seed=42, temperature=0.0)
        fp2 = generate_fingerprint(cfg, models, benches, seed=42, temperature=0.0)
        assert fp1.fingerprint_hash == fp2.fingerprint_hash

    def test_different_seed_produces_different_fingerprint(self):
        cfg = {"model": "gpt-4"}
        fp1 = generate_fingerprint(cfg, [], [], seed=42, temperature=0.0)
        fp2 = generate_fingerprint(cfg, [], [], seed=99, temperature=0.0)
        assert fp1.fingerprint_hash != fp2.fingerprint_hash

    def test_validate_identical_reproducible(self):
        cfg = {"x": 1}
        fp_a = generate_fingerprint(cfg, [], [], seed=42, temperature=0.0)
        fp_b = generate_fingerprint(cfg, [], [], seed=42, temperature=0.0)
        result = validate_reproducibility(fp_a, fp_b)
        assert result["reproducible"] is True
        assert result["differences"] == []

    def test_validate_different_reports_differences(self):
        cfg_a = {"x": 1}
        cfg_b = {"x": 2}
        fp_a = generate_fingerprint(cfg_a, [], [], seed=42, temperature=0.0)
        fp_b = generate_fingerprint(cfg_b, [], [], seed=42, temperature=0.0)
        result = validate_reproducibility(fp_a, fp_b)
        assert result["reproducible"] is False
        assert len(result["differences"]) > 0
