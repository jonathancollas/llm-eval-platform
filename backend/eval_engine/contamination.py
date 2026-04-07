"""
Contamination Detection — CATALOG-1
Detect if a model has seen benchmark test data during training.
Uses n-gram overlap, permutation testing, and response confidence analysis.
"""
import re
import math
import logging
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer."""
    return re.findall(r'\b\w+\b', text.lower())


def _ngrams(tokens: list[str], n: int) -> list[tuple]:
    return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]


def ngram_overlap_score(response: str, reference: str, n: int = 5) -> float:
    """Compute n-gram overlap between response and reference text.
    High overlap suggests the model may have memorized the content.
    Returns 0-1 (1 = perfect overlap).
    """
    resp_tokens = _tokenize(response)
    ref_tokens = _tokenize(reference)

    if len(resp_tokens) < n or len(ref_tokens) < n:
        return 0.0

    resp_ngrams = set(_ngrams(resp_tokens, n))
    ref_ngrams = set(_ngrams(ref_tokens, n))

    if not ref_ngrams:
        return 0.0

    overlap = resp_ngrams & ref_ngrams
    return len(overlap) / len(ref_ngrams)


def verbatim_reproduction_score(response: str, reference: str) -> float:
    """Detect verbatim reproduction of reference text.
    Checks for longest common substring as a ratio.
    """
    resp = response.lower().strip()
    ref = reference.lower().strip()

    if not resp or not ref:
        return 0.0

    # Longest common substring (simplified for performance)
    min_len = min(len(resp), len(ref))
    if min_len < 20:
        return 0.0

    # Check for direct containment
    if ref[:100] in resp or resp[:100] in ref:
        return 0.8

    # Sliding window match
    window = 50
    matches = 0
    total = 0
    for i in range(0, len(ref) - window, window):
        chunk = ref[i:i+window]
        total += 1
        if chunk in resp:
            matches += 1

    return matches / max(total, 1)


def confidence_anomaly_score(scores: list[float]) -> float:
    """Detect suspiciously high accuracy that suggests contamination.
    A model scoring >95% on diverse benchmarks is suspicious.
    Returns 0-1 (1 = very suspicious).
    """
    if not scores or len(scores) < 5:
        return 0.0

    avg = sum(scores) / len(scores)
    if avg < 0.85:
        return 0.0

    # Variance: contaminated models often have uniformly high scores
    variance = sum((s - avg) ** 2 for s in scores) / len(scores)
    std = math.sqrt(variance)

    # Suspicious: high average + low variance
    if avg > 0.95 and std < 0.05:
        return 0.9
    if avg > 0.90 and std < 0.08:
        return 0.6
    if avg > 0.85 and std < 0.10:
        return 0.3

    return 0.0


def first_token_probability_score(scores: list[float], expected_random: float = 0.25) -> float:
    """For MCQ benchmarks: if the model's accuracy on first attempt is
    significantly above random chance AND very consistent, it may have
    memorized the answers. Returns 0-1."""
    if not scores or len(scores) < 10:
        return 0.0

    correct_rate = sum(1 for s in scores if s >= 0.5) / len(scores)

    # Compare to expected random baseline
    if correct_rate <= expected_random + 0.1:
        return 0.0  # Within noise

    # How far above random?
    excess = correct_rate - expected_random
    if excess > 0.6:
        return 0.8
    if excess > 0.4:
        return 0.5
    if excess > 0.25:
        return 0.3

    return 0.0


def analyze_contamination(
    items: list[dict],
    benchmark_name: str = "",
    benchmark_type: str = "",
) -> dict:
    """Full contamination analysis on a set of eval results.

    Each item should have: prompt, response, expected, score
    """
    if not items:
        return {"contamination_score": 0.0, "signals": [], "risk": "none"}

    signals = []

    # 1. N-gram overlap (response vs expected)
    ngram_scores = []
    for item in items[:50]:  # Sample for performance
        resp = item.get("response", "")
        expected = item.get("expected", "")
        if expected and len(expected) > 20:
            overlap = ngram_overlap_score(resp, expected, n=5)
            ngram_scores.append(overlap)

    if ngram_scores:
        avg_ngram = sum(ngram_scores) / len(ngram_scores)
        if avg_ngram > 0.3:
            signals.append({
                "type": "ngram_overlap",
                "score": round(avg_ngram, 3),
                "detail": f"Avg 5-gram overlap with expected answers: {avg_ngram:.1%}",
                "severity": "high" if avg_ngram > 0.5 else "medium",
            })

    # 2. Verbatim reproduction
    verbatim_scores = []
    for item in items[:30]:
        resp = item.get("response", "")
        expected = item.get("expected", "")
        if expected and len(expected) > 30:
            v = verbatim_reproduction_score(resp, expected)
            verbatim_scores.append(v)

    if verbatim_scores:
        avg_verbatim = sum(verbatim_scores) / len(verbatim_scores)
        if avg_verbatim > 0.2:
            signals.append({
                "type": "verbatim_reproduction",
                "score": round(avg_verbatim, 3),
                "detail": f"Verbatim reproduction rate: {avg_verbatim:.1%}",
                "severity": "high" if avg_verbatim > 0.4 else "medium",
            })

    # 3. Confidence anomaly
    scores = [item.get("score", 0) for item in items]
    conf_score = confidence_anomaly_score(scores)
    if conf_score > 0.2:
        signals.append({
            "type": "confidence_anomaly",
            "score": round(conf_score, 3),
            "detail": f"Suspiciously high + uniform accuracy (avg={sum(scores)/len(scores):.1%})",
            "severity": "high" if conf_score > 0.6 else "medium",
        })

    # 4. First-token probability (MCQ)
    if benchmark_type in ("academic",) or any(
        item.get("expected", "").strip().upper() in ["A", "B", "C", "D"] for item in items[:5]
    ):
        ftp = first_token_probability_score(scores, expected_random=0.25)
        if ftp > 0.2:
            signals.append({
                "type": "first_token_probability",
                "score": round(ftp, 3),
                "detail": f"MCQ accuracy far above random chance ({sum(1 for s in scores if s >= 0.5)/len(scores):.1%} vs 25% random)",
                "severity": "high" if ftp > 0.5 else "medium",
            })

    # Composite contamination score
    if not signals:
        composite = 0.0
    else:
        composite = sum(s["score"] for s in signals) / len(signals)

    risk = "high" if composite > 0.5 else "medium" if composite > 0.2 else "low" if composite > 0.05 else "none"

    return {
        "contamination_score": round(composite, 3),
        "risk": risk,
        "signals": signals,
        "items_analyzed": len(items),
        "benchmark": benchmark_name,
    }
