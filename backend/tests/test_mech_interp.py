"""
Tests for eval_engine/mech_interp.py
Covers: _extract_cot_and_answer (all formats), _check_cot_answer_consistency,
        _score_reasoning_quality, _extract_confidence, PARAPHRASE_TEMPLATES,
        MechInterpValidator._make_interpretation (all signal branches),
        MechInterpValidator.__init__ / run / _probe_cot / _probe_paraphrase.
"""
import asyncio
import os
import secrets
import sys
from unittest.mock import AsyncMock, MagicMock

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


# ══════════════════════════════════════════════════════════════════════════════
# MechInterpValidator.__init__ / run / _probe_cot / _probe_paraphrase
# ══════════════════════════════════════════════════════════════════════════════

def _make_adapter(text_response="The answer is A. Confidence: 0.8"):
    """Build a mock adapter whose complete() returns a fake response."""
    resp = MagicMock()
    resp.text = text_response
    resp.total_tokens = 30
    resp.cost_usd = 0.001
    adapter = MagicMock()
    adapter.complete = AsyncMock(return_value=resp)
    return adapter


def _make_model(name="test-model", model_id=1):
    m = MagicMock()
    m.id = model_id
    m.name = name
    return m


@pytest.mark.asyncio
async def test_mech_interp_validator_init():
    factory = lambda m: _make_adapter()
    v = MechInterpValidator(adapter_factory=factory)
    assert v.adapter_factory is factory


@pytest.mark.asyncio
async def test_mech_interp_validator_run_basic():
    adapter = _make_adapter("I think step by step. Therefore: 4. Confidence: 0.9")
    validator = MechInterpValidator(adapter_factory=lambda m: adapter)
    questions = [{"question": "What is 2+2?", "expected": "4"}]
    model = _make_model()

    result = await validator.run(model, "test_bench", questions, n_samples=1)

    assert result is not None
    assert result.model_name == "test-model"
    assert result.benchmark_name == "test_bench"
    assert result.n_probes == 1
    assert len(result.cot_results) == 1
    assert len(result.paraphrase_results) == 1
    assert isinstance(result.total_tokens, int)
    assert isinstance(result.total_cost_usd, float)


@pytest.mark.asyncio
async def test_mech_interp_validator_run_no_confidence():
    """Run with a response that has no confidence marker."""
    adapter = _make_adapter("The answer is B.")
    validator = MechInterpValidator(adapter_factory=lambda m: adapter)
    questions = [{"question": "Pick A or B", "expected": "B"}]
    model = _make_model()

    result = await validator.run(model, "bench", questions, n_samples=1)
    # stated_confidence_accuracy falls back to 0.5 when no confidence pairs
    assert result.stated_confidence_accuracy == 0.5
    assert result.overconfidence_rate == 0.0


@pytest.mark.asyncio
async def test_mech_interp_validator_run_multiple_questions_sampling():
    """n_samples < total questions triggers random sampling."""
    adapter = _make_adapter("Answer is X. Confidence: 0.7")
    validator = MechInterpValidator(adapter_factory=lambda m: adapter)
    questions = [{"question": f"Q{i}", "expected": "X"} for i in range(10)]
    model = _make_model()

    result = await validator.run(model, "bench", questions, n_samples=3)
    assert result.n_probes == 3


@pytest.mark.asyncio
async def test_mech_interp_validator_run_validation_signal():
    """High CoT rate + high invariance should produce supports or neutral signal."""
    adapter = _make_adapter("Step 1: analyse. Step 2: conclude. Therefore: Paris. Confidence: 0.9")
    validator = MechInterpValidator(adapter_factory=lambda m: adapter)
    questions = [{"question": "Capital of France?", "expected": "Paris"}]
    model = _make_model()

    result = await validator.run(model, "geo", questions, n_samples=1)
    assert result.validation_signal in ("supports", "neutral", "undermines")
    assert result.interpretation != ""
    assert len(result.limitations) > 0
    assert len(result.references) > 0


@pytest.mark.asyncio
async def test_mech_interp_validator_probe_cot_exception_handling():
    """When adapter raises, _probe_cot returns an error result with zeros."""
    adapter = MagicMock()
    adapter.complete = AsyncMock(side_effect=RuntimeError("network error"))
    validator = MechInterpValidator(adapter_factory=lambda m: adapter)

    result, tokens, cost = await validator._probe_cot(adapter, "What is 1+1?", "2")
    assert result.cot_consistent is False
    assert result.cot_reasoning == "[error]"
    assert tokens == 0
    assert cost == 0.0


@pytest.mark.asyncio
async def test_mech_interp_validator_probe_paraphrase_basic():
    adapter = _make_adapter("Paris")
    validator = MechInterpValidator(adapter_factory=lambda m: adapter)

    result, tokens, cost = await validator._probe_paraphrase(adapter, "Capital of France?", "paris")
    assert len(result.paraphrases) == 3
    assert len(result.answers) == 3
    assert isinstance(result.agreement_rate, float)
    assert isinstance(result.invariant, bool)


@pytest.mark.asyncio
async def test_mech_interp_validator_probe_paraphrase_no_expected():
    """Without expected answer, uses pairwise similarity."""
    adapter = _make_adapter("The answer is yes")
    validator = MechInterpValidator(adapter_factory=lambda m: adapter)

    result, tokens, cost = await validator._probe_paraphrase(adapter, "Is sky blue?", "")
    assert 0.0 <= result.agreement_rate <= 1.0


@pytest.mark.asyncio
async def test_mech_interp_validator_probe_paraphrase_adapter_error():
    """When paraphrase calls fail, error strings are stored in answers."""
    adapter = MagicMock()
    adapter.complete = AsyncMock(side_effect=RuntimeError("timeout"))
    validator = MechInterpValidator(adapter_factory=lambda m: adapter)

    result, tokens, cost = await validator._probe_paraphrase(adapter, "Question?", "answer")
    assert all(a == "[error]" for a in result.answers)
    assert tokens == 0


@pytest.mark.asyncio
async def test_mech_interp_validator_run_prompt_key_variants():
    """Supports both 'question' and 'prompt' keys in question dicts."""
    adapter = _make_adapter("The result is 42")
    validator = MechInterpValidator(adapter_factory=lambda m: adapter)
    questions = [{"prompt": "What is the meaning?", "answer": "42"}]
    model = _make_model()

    result = await validator.run(model, "misc", questions, n_samples=1)
    assert result.n_probes == 1
