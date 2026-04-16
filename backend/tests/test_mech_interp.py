"""
Tests for eval_engine/mech_interp.py
Covers: _extract_cot_and_answer (all formats), _check_cot_answer_consistency,
        _score_reasoning_quality, _extract_confidence, PARAPHRASE_TEMPLATES,
        MechInterpValidator._make_interpretation (all signal branches).
"""
import os
import secrets
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from eval_engine.mech_interp import (
    _extract_cot_and_answer,
    _check_cot_answer_consistency,
    _score_reasoning_quality,
    _extract_confidence,
    PARAPHRASE_TEMPLATES,
    MechInterpValidator,
    CoTConsistencyResult,
    ParaphraseInvarianceResult,
    MechInterpValidationReport,
)


# ══════════════════════════════════════════════════════════════════════════════
# _extract_cot_and_answer
# ══════════════════════════════════════════════════════════════════════════════

def test_extract_cot_think_tags():
    response = "<think>Let me reason step by step.</think>The answer is Paris."
    cot, answer = _extract_cot_and_answer(response)
    assert "reason" in cot.lower()
    assert "paris" in answer.lower()


def test_extract_cot_think_tags_empty_after():
    response = "<think>some reasoning</think>"
    cot, answer = _extract_cot_and_answer(response)
    assert "some reasoning" in cot
    assert answer == ""


def test_extract_cot_therefore_marker():
    response = "I know that France is a country in Europe. Therefore: Paris is the capital."
    cot, answer = _extract_cot_and_answer(response)
    assert "europe" in cot.lower()
    assert "therefore" in answer.lower()


def test_extract_cot_answer_marker():
    response = "Considering all factors, this is the case. Answer: B"
    cot, answer = _extract_cot_and_answer(response)
    assert "answer" in answer.lower()


def test_extract_cot_in_conclusion_marker():
    response = "Many factors suggest X. In conclusion: X is correct."
    cot, answer = _extract_cot_and_answer(response)
    assert "in conclusion" in answer.lower()


def test_extract_cot_fallback_last_sentence():
    # Trailing "." makes last split token empty — use no trailing period
    response = "First we know A. Then we know B. Therefore the answer is C"
    cot, answer = _extract_cot_and_answer(response)
    assert len(cot) > 0
    assert len(answer) > 0


def test_extract_cot_short_response_no_split():
    response = "Paris"
    cot, answer = _extract_cot_and_answer(response)
    assert answer == "Paris"


def test_extract_cot_so_the_answer_is_marker():
    response = "After thinking about it. So the answer is: 42"
    cot, answer = _extract_cot_and_answer(response)
    assert "42" in answer


# ══════════════════════════════════════════════════════════════════════════════
# _check_cot_answer_consistency
# ══════════════════════════════════════════════════════════════════════════════

def test_check_consistency_no_cot_always_consistent():
    consistent, mismatch = _check_cot_answer_consistency("", "Paris", "Paris")
    assert consistent is True
    assert mismatch is False


def test_check_consistency_cot_mentions_expected():
    cot = "France's capital has been Paris for centuries."
    consistent, mismatch = _check_cot_answer_consistency(cot, "Paris", "Paris")
    assert consistent is True


def test_check_consistency_cot_missing_expected():
    cot = "The capital of Germany is Berlin."
    consistent, mismatch = _check_cot_answer_consistency(cot, "Berlin", "Paris")
    # expected "Paris" not in cot → inconsistent
    assert consistent is False


def test_check_consistency_contradiction_word_triggers_mismatch():
    cot = "I thought it was A, but actually no it is B."
    consistent, mismatch = _check_cot_answer_consistency(cot, "B", "A")
    assert mismatch is True


def test_check_consistency_however_triggers_mismatch():
    cot = "We assume X. However, the data shows Y."
    consistent, mismatch = _check_cot_answer_consistency(cot, "Y", "X")
    assert mismatch is True


def test_check_consistency_no_contradiction_no_mismatch():
    cot = "The answer is clearly Paris based on geography."
    consistent, mismatch = _check_cot_answer_consistency(cot, "Paris", "Paris")
    assert mismatch is False


def test_check_consistency_empty_expected_always_mentioned():
    cot = "Something about the question."
    consistent, mismatch = _check_cot_answer_consistency(cot, "some answer", "")
    assert consistent is True


# ══════════════════════════════════════════════════════════════════════════════
# _score_reasoning_quality
# ══════════════════════════════════════════════════════════════════════════════

def test_score_reasoning_empty_returns_low():
    assert _score_reasoning_quality("") == 0.1


def test_score_reasoning_short_returns_low():
    assert _score_reasoning_quality("Yes.") == 0.1


def test_score_reasoning_minimal_structure():
    cot = "Because the data shows this, therefore we conclude that answer is A."
    score = _score_reasoning_quality(cot)
    assert score > 0.1


def test_score_reasoning_rich_structure():
    cot = (
        "First, we note that France is in Europe. "
        "Second, its history shows Paris as capital. "
        "Given that all references confirm this, it follows that Paris is correct. "
        "Thus the answer is Paris. "
        "1. Historical evidence. 2. Geographic data. 3. Modern confirmation."
    )
    score = _score_reasoning_quality(cot)
    assert score > 0.3


def test_score_reasoning_max_is_1():
    very_long = " ".join(
        ["First, because, since, given that, therefore, thus, if A then B. 1. Step one."] * 20
    )
    score = _score_reasoning_quality(very_long)
    assert score <= 1.0


def test_score_reasoning_length_bonus():
    short_cot = "Because of facts."
    long_cot = short_cot + " " + "a" * 500
    short_score = _score_reasoning_quality(short_cot)
    long_score = _score_reasoning_quality(long_cot)
    assert long_score >= short_score


# ══════════════════════════════════════════════════════════════════════════════
# _extract_confidence
# ══════════════════════════════════════════════════════════════════════════════

def test_extract_confidence_percent_high():
    conf = _extract_confidence("I am 95% confidence in this answer.")
    assert conf == 0.9


def test_extract_confidence_percent_moderate():
    # Pattern matches "X% confidence" (not "confident"); "80" triggers 0.7 branch
    conf = _extract_confidence("I have 80% confidence in this answer.")
    assert conf == 0.7


def test_extract_confidence_percent_low():
    conf = _extract_confidence("I am 60% sure.")
    assert conf == 0.5


def test_extract_confidence_very_confident_words():
    conf = _extract_confidence("I'm very confident this is correct.")
    assert conf == 0.9


def test_extract_confidence_quite_confident():
    conf = _extract_confidence("I am quite confident.")
    assert conf == 0.7


def test_extract_confidence_moderate_explicit():
    conf = _extract_confidence("With moderate confidence, the answer is B.")
    assert conf == 0.7


def test_extract_confidence_none_when_no_pattern():
    conf = _extract_confidence("The answer is Paris.")
    assert conf is None


def test_extract_confidence_empty_string():
    assert _extract_confidence("") is None


# ══════════════════════════════════════════════════════════════════════════════
# PARAPHRASE_TEMPLATES
# ══════════════════════════════════════════════════════════════════════════════

def test_paraphrase_templates_contain_placeholder():
    for tpl in PARAPHRASE_TEMPLATES:
        assert "{question}" in tpl, f"Template missing {{question}}: {tpl!r}"


def test_paraphrase_templates_format_with_question():
    q = "What is the capital of France?"
    for tpl in PARAPHRASE_TEMPLATES:
        result = tpl.format(question=q)
        assert q in result


# ══════════════════════════════════════════════════════════════════════════════
# MechInterpValidator._make_interpretation
# ══════════════════════════════════════════════════════════════════════════════

def test_make_interpretation_supports_signal():
    text = MechInterpValidator._make_interpretation(
        "supports", cot_rate=0.9, mismatch_rate=0.0,
        invariance_rate=0.9, overconf_rate=0.0, conf_adj=0.1,
    )
    assert "SUPPORTS" in text


def test_make_interpretation_undermines_signal():
    text = MechInterpValidator._make_interpretation(
        "undermines", cot_rate=0.3, mismatch_rate=0.5,
        invariance_rate=0.3, overconf_rate=0.5, conf_adj=-0.2,
    )
    assert "UNDERMINES" in text


def test_make_interpretation_neutral_signal():
    text = MechInterpValidator._make_interpretation(
        "neutral", cot_rate=0.7, mismatch_rate=0.1,
        invariance_rate=0.7, overconf_rate=0.1, conf_adj=0.0,
    )
    assert "NEUTRAL" in text


def test_make_interpretation_low_cot_rate_warns():
    text = MechInterpValidator._make_interpretation(
        "neutral", cot_rate=0.3, mismatch_rate=0.0,
        invariance_rate=0.8, overconf_rate=0.0, conf_adj=0.0,
    )
    assert "CoT consistency" in text


def test_make_interpretation_high_mismatch_warns():
    text = MechInterpValidator._make_interpretation(
        "neutral", cot_rate=0.8, mismatch_rate=0.4,
        invariance_rate=0.8, overconf_rate=0.0, conf_adj=0.0,
    )
    assert "mismatch" in text.lower()


def test_make_interpretation_low_invariance_warns():
    text = MechInterpValidator._make_interpretation(
        "neutral", cot_rate=0.8, mismatch_rate=0.0,
        invariance_rate=0.4, overconf_rate=0.0, conf_adj=0.0,
    )
    assert "paraphrase" in text.lower()


def test_make_interpretation_high_overconfidence_warns():
    text = MechInterpValidator._make_interpretation(
        "neutral", cot_rate=0.8, mismatch_rate=0.0,
        invariance_rate=0.8, overconf_rate=0.4, conf_adj=0.0,
    )
    assert "overconfidence" in text.lower()


def test_make_interpretation_confidence_adj_positive_in_text():
    text = MechInterpValidator._make_interpretation(
        "supports", cot_rate=0.9, mismatch_rate=0.0,
        invariance_rate=0.9, overconf_rate=0.0, conf_adj=0.12,
    )
    assert "+0.12" in text


def test_make_interpretation_returns_non_empty_string():
    text = MechInterpValidator._make_interpretation(
        "neutral", cot_rate=0.5, mismatch_rate=0.1,
        invariance_rate=0.5, overconf_rate=0.1, conf_adj=0.0,
    )
    assert isinstance(text, str)
    assert len(text) > 20
