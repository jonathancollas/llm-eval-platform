"""
Statistical Significance Testing — M1 Research Foundation
McNemar, permutation, Bonferroni, BH-FDR, Cohen's d, power analysis.
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass


def _mean(lst: list) -> float:
    return sum(lst) / len(lst) if lst else 0.0


def _std(lst: list) -> float:
    if len(lst) < 2:
        return 0.0
    m = _mean(lst)
    return math.sqrt(sum((x - m) ** 2 for x in lst) / (len(lst) - 1))


def _chi2_sf_1df(stat: float) -> float:
    """Survival function of chi-squared distribution with 1 degree of freedom."""
    return math.erfc(math.sqrt(stat / 2))


def mcnemar_test(results_a: list, results_b: list, threshold: float = 0.5) -> dict:
    """McNemar's test for paired nominal data with continuity correction."""
    correct_a = [r > threshold for r in results_a]
    correct_b = [r > threshold for r in results_b]

    b = sum(1 for a, bb in zip(correct_a, correct_b) if a and not bb)
    c = sum(1 for a, bb in zip(correct_a, correct_b) if not a and bb)

    if b + c == 0:
        return {
            "statistic": 0,
            "p_value": 1.0,
            "b": 0,
            "c": 0,
            "significant": False,
            "interpretation": "No discordant pairs",
        }

    stat = (abs(b - c) - 1) ** 2 / (b + c)
    p_value = _chi2_sf_1df(stat)
    significant = p_value < 0.05

    interpretation = (
        f"Model A is significantly better (p={p_value:.4f})"
        if significant and b > c
        else f"Model B is significantly better (p={p_value:.4f})"
        if significant
        else f"No significant difference (p={p_value:.4f})"
    )

    return {
        "statistic": stat,
        "p_value": p_value,
        "b": b,
        "c": c,
        "significant": significant,
        "interpretation": interpretation,
    }


def permutation_test(
    scores_a: list, scores_b: list, n_permutations: int = 1000, seed: int = 42
) -> dict:
    """Permutation test for difference in means."""
    observed_diff = _mean(scores_a) - _mean(scores_b)
    pooled = list(scores_a) + list(scores_b)
    n_a = len(scores_a)

    rng = random.Random(seed)
    count = 0
    for _ in range(n_permutations):
        rng.shuffle(pooled)
        perm_diff = _mean(pooled[:n_a]) - _mean(pooled[n_a:])
        if abs(perm_diff) >= abs(observed_diff):
            count += 1

    p_value = count / n_permutations
    significant = p_value < 0.05

    return {
        "observed_diff": observed_diff,
        "p_value": p_value,
        "n_permutations": n_permutations,
        "significant": significant,
        "interpretation": (
            f"Significant difference (p={p_value:.4f})"
            if significant
            else f"No significant difference (p={p_value:.4f})"
        ),
    }


def bonferroni_correction(p_values: list, alpha: float = 0.05) -> dict:
    """Bonferroni multiple-testing correction."""
    n = len(p_values)
    corrected_alpha = alpha / n
    rejected = [p <= corrected_alpha for p in p_values]
    adjusted_p_values = [min(p * n, 1.0) for p in p_values]

    return {
        "corrected_alpha": corrected_alpha,
        "rejected": rejected,
        "adjusted_p_values": adjusted_p_values,
        "n_rejected": sum(rejected),
    }


def benjamini_hochberg_correction(p_values: list, alpha: float = 0.05) -> dict:
    """Benjamini-Hochberg FDR correction (step-up procedure)."""
    n = len(p_values)
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    rejected = [False] * n
    fdr_threshold = 0.0

    for rank, (orig_idx, p) in enumerate(indexed, start=1):
        threshold = (rank / n) * alpha
        if p <= threshold:
            fdr_threshold = threshold
            rejected[orig_idx] = True

    # BH-adjusted p-values
    adjusted = [0.0] * n
    min_adj = 1.0
    for rank in range(n, 0, -1):
        orig_idx, p = indexed[rank - 1]
        adj = min(p * n / rank, 1.0)
        min_adj = min(min_adj, adj)
        adjusted[orig_idx] = min_adj

    return {
        "rejected": rejected,
        "adjusted_p_values": adjusted,
        "n_rejected": sum(rejected),
        "fdr_threshold": fdr_threshold,
    }


def cohens_d(scores_a: list, scores_b: list) -> dict:
    """Cohen's d effect size with pooled standard deviation."""
    n1, n2 = len(scores_a), len(scores_b)
    mean_a, mean_b = _mean(scores_a), _mean(scores_b)
    std1, std2 = _std(scores_a), _std(scores_b)

    if n1 + n2 - 2 == 0:
        return {"d": 0.0, "magnitude": "negligible", "interpretation": "Effect size d=0.0000 (negligible)"}
    pooled_var = ((n1 - 1) * std1 ** 2 + (n2 - 1) * std2 ** 2) / (n1 + n2 - 2)
    pooled_std = math.sqrt(pooled_var)

    if pooled_std == 0:
        d = 0.0
    else:
        d = (mean_a - mean_b) / pooled_std

    abs_d = abs(d)
    if abs_d < 0.2:
        magnitude = "negligible"
    elif abs_d < 0.5:
        magnitude = "small"
    elif abs_d < 0.8:
        magnitude = "medium"
    else:
        magnitude = "large"

    return {
        "d": d,
        "magnitude": magnitude,
        "interpretation": f"Effect size d={d:.4f} ({magnitude})",
    }


def power_analysis(
    effect_size: float, alpha: float = 0.05, power: float = 0.8
) -> dict:
    """Sample size estimation for two-sample test."""
    z_alpha = 1.96
    z_beta = 0.842

    if effect_size > 0:
        required_n = math.ceil(((z_alpha + z_beta) / effect_size) ** 2 * 2)
    else:
        required_n = 9999

    return {
        "required_n": required_n,
        "effect_size": effect_size,
        "alpha": alpha,
        "power": power,
        "interpretation": (
            f"Need {required_n} samples per group to detect effect size {effect_size:.3f}"
        ),
    }


def compare_runs(run_a_scores: list, run_b_scores: list) -> dict:
    """Compare two evaluation runs with multiple statistical tests."""
    mc = mcnemar_test(run_a_scores, run_b_scores)
    perm = permutation_test(run_a_scores, run_b_scores)
    cd = cohens_d(run_a_scores, run_b_scores)

    significant = mc["p_value"] < 0.05 or perm["p_value"] < 0.05
    overall_verdict = "significant" if significant else "not_significant"

    return {
        "mcnemar": mc,
        "permutation": perm,
        "effect_size": cd,
        "overall_verdict": overall_verdict,
    }
