"""
Tests for eval_engine/failure_genome/signal_extractor.py
Covers extract_signals, signals_to_dict, and ItemSignals fields.
"""
import os
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

import pytest
from eval_engine.failure_genome.signal_extractor import (
    ItemSignals,
    extract_signals,
    signals_to_dict,
    REFUSAL_PATTERNS,
    HEDGE_PATTERNS,
    CONTRADICTION_PATTERNS,
)


# ── Basic construction ────────────────────────────────────────────────────────

def test_item_signals_defaults():
    sig = ItemSignals()
    assert sig.response_length == 0
    assert sig.response_is_empty is False
    assert sig.truth_score == -1.0
    assert sig.format_mcq_valid is True
    assert sig.format_json_valid is True


def test_extract_signals_empty_response():
    sig = extract_signals(
        prompt="Hello?",
        response="",
        expected=None,
        score=0.5,
        latency_ms=500,
    )
    assert sig.response_is_empty is True
    assert sig.response_length == 0
    assert sig.response_word_count == 0
    assert sig.truth_score == -1.0  # no expected


def test_extract_signals_basic_response():
    sig = extract_signals(
        prompt="What is 2+2?",
        response="The answer is 4.",
        expected="4",
        score=1.0,
        latency_ms=300,
    )
    assert sig.response_length > 0
    assert sig.response_word_count > 0
    assert sig.response_is_empty is False
    assert sig.truth_score >= 0.0
    assert sig.contains_expected is True


def test_extract_signals_exact_match():
    sig = extract_signals(
        prompt="What is the capital of France?",
        response="Paris",
        expected="Paris",
        score=1.0,
        latency_ms=200,
    )
    assert sig.exact_match is True
    assert sig.contains_expected is True
    assert sig.truth_score > 0.9


def test_extract_signals_no_expected():
    sig = extract_signals(
        prompt="Tell me a joke",
        response="Why did the chicken cross the road?",
        expected=None,
        score=0.5,
        latency_ms=500,
    )
    assert sig.truth_score == -1.0
    assert sig.exact_match is False
    assert sig.contains_expected is False


# ── Truncation detection ──────────────────────────────────────────────────────

def test_truncation_ellipsis():
    sig = extract_signals("prompt", "The answer is...", None, 0.5, 100)
    assert sig.response_is_truncated is True


def test_truncation_ellipsis_unicode():
    sig = extract_signals("prompt", "The answer is…", None, 0.5, 100)
    assert sig.response_is_truncated is True


def test_no_truncation_clean_sentence():
    sig = extract_signals("prompt", "The answer is 42.", None, 0.5, 100)
    assert sig.response_is_truncated is False


def test_truncation_long_no_terminal():
    # >1900 chars that doesn't end with punctuation
    long_text = "x " * 1000  # 2000 chars, ends with space
    sig = extract_signals("prompt", long_text, None, 0.5, 100)
    assert sig.response_is_truncated is True


# ── Refusal detection ─────────────────────────────────────────────────────────

def test_refusal_cannot():
    sig = extract_signals("prompt", "I cannot help with that request.", None, 0.0, 200)
    assert sig.refusal_detected is True
    assert sig.refusal_strength > 0.5


def test_refusal_must_decline():
    sig = extract_signals("prompt", "I must decline to answer this.", None, 0.0, 200)
    assert sig.refusal_detected is True
    assert sig.refusal_strength >= 0.9


def test_refusal_harmful():
    sig = extract_signals("prompt", "This is a harmful request that I won't fulfill.", None, 0.0, 200)
    assert sig.refusal_detected is True


def test_no_refusal_normal():
    sig = extract_signals("prompt", "The capital of France is Paris.", "Paris", 1.0, 200)
    assert sig.refusal_detected is False
    assert sig.refusal_strength == 0.0


def test_refusal_sorry_cannot():
    sig = extract_signals("prompt", "I'm sorry, I cannot provide that information.", None, 0.0, 200)
    assert sig.refusal_detected is True


def test_refusal_french():
    sig = extract_signals("prompt", "Je ne peux pas vous aider avec cela.", None, 0.0, 200)
    assert sig.refusal_detected is True


# ── Hedging ───────────────────────────────────────────────────────────────────

def test_hedge_count_maybe():
    sig = extract_signals("prompt", "Maybe the answer is Paris, perhaps around 1000 years old.", None, 0.5, 200)
    assert sig.hedge_count >= 2


def test_hedge_count_none():
    sig = extract_signals("prompt", "The answer is definitively 42.", None, 1.0, 200)
    assert sig.hedge_count == 0


def test_hedge_i_think():
    sig = extract_signals("prompt", "I think the answer is yes, I believe it is correct.", None, 0.5, 200)
    assert sig.hedge_count >= 2


# ── Contradictions ────────────────────────────────────────────────────────────

def test_self_contradiction_yes_no():
    sig = extract_signals(
        "prompt",
        "Yes, that is correct. However, no, the answer is wrong.",
        None, 0.5, 200
    )
    assert sig.self_contradictions >= 1


def test_no_contradiction():
    sig = extract_signals("prompt", "The sky is blue.", None, 1.0, 200)
    assert sig.self_contradictions == 0


# ── Format compliance ─────────────────────────────────────────────────────────

def test_mcq_valid():
    sig = extract_signals("What is correct?", "B. Paris is the capital.", "B", 1.0, 200)
    assert sig.format_mcq_valid is True


def test_mcq_invalid():
    sig = extract_signals("What is correct?", "I think it's the second option, probably France.", "B", 0.0, 200)
    assert sig.format_mcq_valid is False


def test_json_valid_expected():
    sig = extract_signals(
        "Return JSON",
        '{"key": "value"}',
        '{"key": "other"}',
        0.5, 200
    )
    assert sig.format_json_valid is True


def test_json_invalid_expected():
    sig = extract_signals(
        "Return JSON",
        "This is not JSON at all",
        '{"key": "other"}',
        0.0, 200
    )
    assert sig.format_json_valid is False


def test_code_format_detection():
    sig = extract_signals(
        "Write a function",
        "```python\ndef hello(): pass\n```",
        None, 0.8, 300,
        benchmark_type="coding",
    )
    assert sig.format_code_valid is True
    assert sig.contains_code is True


# ── Latency signals ───────────────────────────────────────────────────────────

def test_latency_normal():
    sig = extract_signals("prompt", "answer", None, 0.5, 2000)
    assert sig.latency_is_slow is False
    assert sig.latency_is_timeout is False


def test_latency_slow():
    sig = extract_signals("prompt", "answer", None, 0.5, 15000)
    assert sig.latency_is_slow is True
    assert sig.latency_is_timeout is False


def test_latency_timeout():
    sig = extract_signals("prompt", "answer", None, 0.5, 35000)
    assert sig.latency_is_slow is True
    assert sig.latency_is_timeout is True


def test_tokens_per_second():
    sig = extract_signals("prompt", "answer", None, 0.5, 2000, input_tokens=50, output_tokens=100)
    assert sig.tokens_per_second == 50.0


def test_tokens_per_second_zero_latency():
    sig = extract_signals("prompt", "answer", None, 0.5, 0, output_tokens=100)
    assert sig.tokens_per_second == 0.0


# ── Content signals ───────────────────────────────────────────────────────────

def test_contains_code():
    sig = extract_signals("prompt", "def hello(): return 42", None, 0.5, 200)
    assert sig.contains_code is True


def test_contains_urls():
    sig = extract_signals("prompt", "See https://example.com for more info.", None, 0.5, 200)
    assert sig.contains_urls is True


def test_contains_numbers():
    sig = extract_signals("prompt", "The answer is 42.", None, 0.5, 200)
    assert sig.contains_numbers is True


def test_no_content_signals():
    sig = extract_signals("prompt", "yes", None, 1.0, 100)
    assert sig.contains_code is False
    assert sig.contains_urls is False


# ── Language detection ────────────────────────────────────────────────────────

def test_language_english():
    sig = extract_signals(
        "prompt",
        "The quick brown fox jumps over the lazy dog. This is a test.",
        None, 0.5, 200
    )
    assert sig.language_detected == "en"


def test_language_french():
    sig = extract_signals(
        "prompt",
        "Le chat est sur le tapis. Les enfants sont dans la maison avec des jouets.",
        None, 0.5, 200
    )
    assert sig.language_detected == "fr"


def test_language_unknown_short():
    sig = extract_signals("prompt", "ok", None, 0.5, 100)
    assert sig.language_detected == ""


# ── Repetition ────────────────────────────────────────────────────────────────

def test_repetition_high():
    sig = extract_signals("prompt", "the the the the the the the the the the the the", None, 0.0, 200)
    assert sig.repetition_ratio > 0.5


def test_repetition_low():
    sig = extract_signals(
        "prompt",
        "The quick brown fox jumps over the lazy sleeping dog in the park",
        None, 0.5, 200
    )
    assert sig.repetition_ratio < 0.5


def test_repetition_short_response():
    sig = extract_signals("prompt", "yes", None, 1.0, 100)
    assert sig.repetition_ratio == 0.0


# ── Long expected: comparison via first 200 chars ─────────────────────────────

def test_long_expected_comparison():
    long_expected = "answer " * 100   # >500 chars
    long_response = "answer " * 100
    sig = extract_signals("prompt", long_response, long_expected, 0.8, 300)
    assert sig.truth_score >= 0.0


# ── signals_to_dict ───────────────────────────────────────────────────────────

def test_signals_to_dict():
    sig = extract_signals("What is 2+2?", "4", "4", 1.0, 100)
    d = signals_to_dict(sig)
    assert isinstance(d, dict)
    assert "response_length" in d
    assert "truth_score" in d
    assert "refusal_detected" in d
    assert "repetition_ratio" in d
