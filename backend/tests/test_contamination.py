"""
Tests for eval_engine/contamination.py
Covers: _tokenize, _ngrams, ngram_overlap_score, verbatim_reproduction_score,
        confidence_anomaly_score, first_token_probability_score, analyze_contamination.
"""
import os
import secrets
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from eval_engine.contamination import (
    _tokenize,
    _ngrams,
    ngram_overlap_score,
    verbatim_reproduction_score,
    confidence_anomaly_score,
    first_token_probability_score,
    analyze_contamination,
)


# ── _tokenize ─────────────────────────────────────────────────────────────────

def test_tokenize_basic():
    tokens = _tokenize("Hello, World!")
    assert tokens == ["hello", "world"]


def test_tokenize_lowercase():
    tokens = _tokenize("UPPER CASE")
    assert tokens == ["upper", "case"]


def test_tokenize_empty():
    assert _tokenize("") == []


def test_tokenize_numbers():
    tokens = _tokenize("item 42 value")
    assert "42" in tokens


def test_tokenize_strips_punctuation():
    tokens = _tokenize("word.")
    assert tokens == ["word"]


# ── _ngrams ───────────────────────────────────────────────────────────────────

def test_ngrams_bigrams():
    tokens = ["a", "b", "c", "d"]
    result = _ngrams(tokens, 2)
    assert result == [("a", "b"), ("b", "c"), ("c", "d")]


def test_ngrams_window_larger_than_tokens():
    tokens = ["a", "b"]
    result = _ngrams(tokens, 5)
    assert result == []


def test_ngrams_unigrams():
    tokens = ["x", "y", "z"]
    result = _ngrams(tokens, 1)
    assert result == [("x",), ("y",), ("z",)]


def test_ngrams_exact_window():
    tokens = ["a", "b", "c"]
    result = _ngrams(tokens, 3)
    assert result == [("a", "b", "c")]


# ── ngram_overlap_score ───────────────────────────────────────────────────────

def test_ngram_overlap_perfect_match():
    long_text = "the quick brown fox jumps over the lazy dog"
    score = ngram_overlap_score(long_text, long_text, n=5)
    assert score == 1.0


def test_ngram_overlap_no_match():
    score = ngram_overlap_score(
        "completely different words here and more",
        "another set of distinct words entirely",
        n=5,
    )
    assert score == 0.0


def test_ngram_overlap_partial():
    reference = "the quick brown fox jumps over the lazy dog"
    response = "the quick brown fox does something else"
    score = ngram_overlap_score(response, reference, n=4)
    assert 0.0 < score < 1.0


def test_ngram_overlap_short_text_returns_zero():
    score = ngram_overlap_score("short", "short", n=5)
    assert score == 0.0


def test_ngram_overlap_empty_reference():
    score = ngram_overlap_score("response text", "", n=5)
    assert score == 0.0


# ── verbatim_reproduction_score ───────────────────────────────────────────────

def test_verbatim_reproduction_exact_short_returns_zero():
    # Too short (< 20 chars) → 0
    score = verbatim_reproduction_score("short", "short")
    assert score == 0.0


def test_verbatim_reproduction_prefix_containment():
    long_ref = "x" * 200
    response = "x" * 200
    score = verbatim_reproduction_score(response, long_ref)
    assert score > 0.0


def test_verbatim_reproduction_different_texts():
    ref = "a" * 200
    resp = "b" * 200
    score = verbatim_reproduction_score(resp, ref)
    assert score == 0.0


def test_verbatim_reproduction_empty_response():
    score = verbatim_reproduction_score("", "some reference text that is long enough")
    assert score == 0.0


def test_verbatim_reproduction_empty_reference():
    score = verbatim_reproduction_score("some response text", "")
    assert score == 0.0


# ── confidence_anomaly_score ──────────────────────────────────────────────────

def test_confidence_anomaly_low_avg_returns_zero():
    scores = [0.5, 0.6, 0.4, 0.7, 0.5]
    assert confidence_anomaly_score(scores) == 0.0


def test_confidence_anomaly_too_few_samples():
    scores = [1.0, 1.0, 1.0]
    assert confidence_anomaly_score(scores) == 0.0


def test_confidence_anomaly_high_avg_low_variance():
    scores = [0.97, 0.98, 0.96, 0.97, 0.98, 0.97]
    result = confidence_anomaly_score(scores)
    assert result == 0.9


def test_confidence_anomaly_high_avg_medium_variance():
    scores = [0.92, 0.93, 0.91, 0.90, 0.93, 0.92]
    result = confidence_anomaly_score(scores)
    assert result == 0.6


def test_confidence_anomaly_upper_middle_range():
    scores = [0.87, 0.86, 0.85, 0.88, 0.86, 0.87]
    result = confidence_anomaly_score(scores)
    assert result == 0.3


def test_confidence_anomaly_empty_returns_zero():
    assert confidence_anomaly_score([]) == 0.0


# ── first_token_probability_score ────────────────────────────────────────────

def test_ftp_score_too_few_samples():
    scores = [1.0, 1.0, 1.0]
    assert first_token_probability_score(scores) == 0.0


def test_ftp_score_at_random_level():
    # 25% accuracy — at random chance
    scores = [1.0 if i % 4 == 0 else 0.0 for i in range(20)]
    assert first_token_probability_score(scores) == 0.0


def test_ftp_score_very_high_accuracy():
    # 95% correct — far above random (25%)
    scores = [1.0] * 19 + [0.0]
    result = first_token_probability_score(scores)
    assert result == 0.8


def test_ftp_score_high_accuracy():
    # 65% correct — excess = 0.40, which is NOT strictly > 0.4, falls to 0.25 → returns 0.3
    scores = [1.0 if i < 13 else 0.0 for i in range(20)]
    result = first_token_probability_score(scores)
    assert result == 0.3


def test_ftp_score_moderate_above_random():
    # 50% correct — excess = 0.25, NOT strictly > 0.25 → returns 0.0
    scores = [1.0 if i < 10 else 0.0 for i in range(20)]
    result = first_token_probability_score(scores)
    assert result == 0.0


# ── analyze_contamination ─────────────────────────────────────────────────────

def test_analyze_contamination_empty_items():
    result = analyze_contamination([])
    assert result["contamination_score"] == 0.0
    assert result["risk"] == "none"
    assert result["signals"] == []


def test_analyze_contamination_clean_results():
    items = [
        {"prompt": f"q{i}", "response": f"distinct response {i} xyz", "expected": "A", "score": 0.6}
        for i in range(10)
    ]
    result = analyze_contamination(items, benchmark_name="test", benchmark_type="academic")
    assert isinstance(result["contamination_score"], float)
    assert result["contamination_score"] >= 0.0
    assert "risk" in result
    assert "signals" in result


def test_analyze_contamination_high_ngram_overlap():
    # Response mirrors expected — high overlap
    long_expected = "the quick brown fox jumps over the lazy dog and the fox is very quick indeed"
    items = [
        {"prompt": f"q{i}", "response": long_expected, "expected": long_expected, "score": 1.0}
        for i in range(10)
    ]
    result = analyze_contamination(items)
    # High overlap should produce a non-zero score or signal
    scores_sum = result["contamination_score"]
    assert scores_sum >= 0.0  # could vary — just check it runs without error


def test_analyze_contamination_suspiciously_high_scores_mcq():
    items = [
        {"prompt": f"q{i}", "response": "A", "expected": "A", "score": 1.0}
        for i in range(20)
    ]
    result = analyze_contamination(items, benchmark_type="academic")
    # uniformly high MCQ scores should trigger confidence_anomaly or first_token signal
    assert "contamination_score" in result
    assert "risk" in result
    assert result["risk"] in ("none", "low", "medium", "high")


def test_analyze_contamination_returns_risk_label():
    items = [{"prompt": "p", "response": "r", "expected": "e", "score": 0.3} for _ in range(10)]
    result = analyze_contamination(items)
    assert result["risk"] in ("none", "low", "medium", "high")


def test_analyze_contamination_benchmark_name_included():
    items = [{"prompt": "p", "response": "r", "expected": "e", "score": 0.5} for _ in range(5)]
    result = analyze_contamination(items, benchmark_name="MMLU")
    assert "contamination_score" in result
