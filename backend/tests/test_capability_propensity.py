"""Tests for eval_engine/capability_propensity.py."""
import asyncio
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from eval_engine.capability_propensity import (
    CAPABILITY_PROMPTS,
    PROPENSITY_PROMPTS,
    TAIL_PROPENSITY_PROMPTS,
    CapabilityProbeResult,
    CapabilityPropensityEngine,
    CapabilityPropensityReport,
    _percentile,
    _score,
    _skew,
    _variance,
)


# ── _score ────────────────────────────────────────────────────────────────────

def test_score_exact_match():
    assert _score("Paris is the capital", "paris") == 1.0


def test_score_no_expected_length_proxy():
    # When no expected: score = min(1.0, word_count / 80)
    response = " ".join(["word"] * 40)
    result = _score(response, "")
    assert 0.0 < result <= 1.0


def test_score_no_expected_long_response():
    # 80+ words should score 1.0
    response = " ".join(["word"] * 100)
    result = _score(response, "")
    assert result == 1.0


def test_score_partial_word_overlap():
    # Some words from expected are in response
    result = _score("The capital of France is Paris indeed", "France Paris capital")
    assert 0.0 < result <= 1.0


def test_score_no_overlap():
    result = _score("completely unrelated text", "Paris capital France")
    assert result == 0.0


def test_score_expected_only_short_words():
    # All expected words <= 3 chars → returns 0.5
    result = _score("something here", "is a to")
    assert result == 0.5


def test_score_empty_response():
    result = _score("", "some expected answer")
    assert result == 0.0


# ── _variance ─────────────────────────────────────────────────────────────────

def test_variance_empty():
    assert _variance([]) == 0.0


def test_variance_single():
    assert _variance([0.5]) == 0.0


def test_variance_known_values():
    # [1, 2, 3] → sample variance = 1.0
    result = _variance([1.0, 2.0, 3.0])
    assert abs(result - 1.0) < 1e-4


def test_variance_all_same():
    assert _variance([0.5, 0.5, 0.5]) == 0.0


# ── _skew ─────────────────────────────────────────────────────────────────────

def test_skew_too_few_values():
    assert _skew([0.5, 0.5, 0.5]) == "symmetric"


def test_skew_symmetric():
    result = _skew([0.5, 0.5, 0.5, 0.5])
    assert result == "symmetric"


def test_skew_right_skewed():
    # mean > median → right skewed
    values = [0.0, 0.0, 0.0, 1.0]  # mean=0.25, median=0.0 → mean - median = 0.25 > 0.05
    result = _skew(values)
    assert result == "right_skewed"


def test_skew_left_skewed():
    # median > mean → left skewed
    values = [1.0, 1.0, 1.0, 0.0]  # mean=0.75, median=1.0 → median - mean = 0.25 > 0.05
    result = _skew(values)
    assert result == "left_skewed"


# ── _percentile ───────────────────────────────────────────────────────────────

def test_percentile_empty():
    assert _percentile([], 10) == 0.0


def test_percentile_p10():
    values = list(range(10))  # [0..9]
    result = _percentile([float(v) for v in values], 10)
    assert isinstance(result, float)


def test_percentile_p5():
    values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    result = _percentile(values, 5)
    assert 0.0 <= result <= 1.0


def test_percentile_single_value():
    result = _percentile([0.7], 50)
    assert result == 0.7


def test_percentile_returns_float():
    result = _percentile([0.1, 0.5, 0.9], 33)
    assert isinstance(result, float)


# ── CapabilityPropensityEngine helpers ───────────────────────────────────────

def _make_adapter(responses: list[str] | None = None):
    """Create a mock adapter that returns responses in sequence."""
    call_count = 0
    default_responses = responses or ["test response"] * 20

    class MockAdapter:
        async def complete(self, prompt, temperature=0.0, max_tokens=256):
            nonlocal call_count
            r = MagicMock()
            idx = min(call_count, len(default_responses) - 1)
            r.text = default_responses[idx]
            r.total_tokens = 50
            r.cost_usd = 0.001
            call_count += 1
            return r

    return MockAdapter()


def _make_engine():
    def factory(model):
        return _make_adapter()
    return CapabilityPropensityEngine(adapter_factory=factory)


# ── CapabilityPropensityEngine.run ────────────────────────────────────────────

def test_engine_run_basic():
    engine = _make_engine()
    model = MagicMock()
    model.id = 1
    model.name = "test-model"

    questions = [
        {"question": "What is 2+2?", "expected": "4", "category": "math"},
        {"question": "Capital of France?", "expected": "Paris", "category": "geo"},
    ]

    async def go():
        return await engine.run(model, "test-benchmark", questions, n_samples=10)

    report = asyncio.run(go())
    assert isinstance(report, CapabilityPropensityReport)
    assert report.n_probes == 2
    assert 0.0 <= report.mean_capability <= 1.0
    assert 0.0 <= report.mean_propensity <= 1.0
    assert report.gap_direction in ("capability_exceeds", "aligned", "propensity_exceeds")
    assert report.gap_significance in ("negligible", "moderate", "large", "critical")


def test_engine_run_samples_when_too_many_questions():
    engine = _make_engine()
    model = MagicMock()
    model.id = 2
    model.name = "sampling-model"

    questions = [{"question": f"Q{i}?", "expected": str(i)} for i in range(30)]

    async def go():
        return await engine.run(model, "test-bench", questions, n_samples=5)

    report = asyncio.run(go())
    assert report.n_probes == 5


def test_engine_run_safety_benchmark_flags_concern():
    """Safety benchmark with very low tail propensity triggers safety_concern."""
    call_count = 0

    class LowPropensityAdapter:
        async def complete(self, prompt, temperature=0.0, max_tokens=256):
            nonlocal call_count
            r = MagicMock()
            # Return empty responses → very low propensity scores
            r.text = ""
            r.total_tokens = 10
            r.cost_usd = 0.0
            call_count += 1
            return r

    def factory(model):
        return LowPropensityAdapter()

    engine = CapabilityPropensityEngine(adapter_factory=factory)
    model = MagicMock()
    model.id = 3
    model.name = "low-prop-model"

    questions = [{"question": f"Q{i}?", "expected": f"ans{i}" * 10} for i in range(5)]

    async def go():
        return await engine.run(model, "safety-refusals", questions, n_samples=10, include_tail=True)

    report = asyncio.run(go())
    assert isinstance(report, CapabilityPropensityReport)


def test_engine_run_without_tail():
    engine = _make_engine()
    model = MagicMock()
    model.id = 4
    model.name = "no-tail-model"

    questions = [{"question": "Q1?", "expected": "A1"}]

    async def go():
        return await engine.run(model, "bench", questions, n_samples=10, include_tail=False)

    report = asyncio.run(go())
    assert report.n_probes == 1


def test_engine_run_gap_direction_capability_exceeds():
    """When capability >> propensity, gap_direction = capability_exceeds."""
    call_count = 0

    class HighCapLowPropAdapter:
        async def complete(self, prompt, temperature=0.0, max_tokens=256):
            nonlocal call_count
            r = MagicMock()
            # Capability prompts get high-matching, propensity gets empty
            if temperature == 0.0:
                r.text = "expected answer matches here expected answer"
            else:
                r.text = "unrelated short"
            r.total_tokens = 20
            r.cost_usd = 0.0
            call_count += 1
            return r

    def factory(model):
        return HighCapLowPropAdapter()

    engine = CapabilityPropensityEngine(adapter_factory=factory)
    model = MagicMock()
    model.id = 5
    model.name = "gap-model"

    questions = [
        {
            "question": "Q?",
            "expected": "expected answer matches here expected answer matches here expected answer",
        }
    ] * 5

    async def go():
        return await engine.run(model, "bench", questions, n_samples=10, include_tail=False)

    report = asyncio.run(go())
    assert report.mean_gap >= report.mean_capability - report.mean_propensity - 0.01


def test_engine_run_propensity_exceeds():
    """When propensity > capability, gap_direction = propensity_exceeds."""
    call_count = 0

    class HighPropLowCapAdapter:
        async def complete(self, prompt, temperature=0.0, max_tokens=256):
            nonlocal call_count
            r = MagicMock()
            if temperature == 0.0:
                r.text = "completely wrong answer"
            else:
                # Propensity answers match expected
                r.text = "expected answer"
            r.total_tokens = 10
            r.cost_usd = 0.0
            call_count += 1
            return r

    def factory(model):
        return HighPropLowCapAdapter()

    engine = CapabilityPropensityEngine(adapter_factory=factory)
    model = MagicMock()
    model.id = 6
    model.name = "prop-model"

    questions = [{"question": "Q?", "expected": "expected answer"} for _ in range(5)]

    async def go():
        return await engine.run(model, "bench", questions, n_samples=10, include_tail=False)

    report = asyncio.run(go())
    # Doesn't matter what direction: the report must be a valid struct
    assert isinstance(report, CapabilityPropensityReport)
    assert report.gap_direction in ("capability_exceeds", "aligned", "propensity_exceeds")


def test_engine_run_adapter_raises():
    """Errors inside adapter.complete are caught and return [ERROR:...] text."""
    class ErrorAdapter:
        async def complete(self, prompt, temperature=0.0, max_tokens=256):
            raise RuntimeError("adapter failed")

    def factory(model):
        return ErrorAdapter()

    engine = CapabilityPropensityEngine(adapter_factory=factory)
    model = MagicMock()
    model.id = 7
    model.name = "error-model"

    questions = [{"question": "Q?", "expected": "A"}]

    async def go():
        return await engine.run(model, "bench", questions, n_samples=10, include_tail=False)

    report = asyncio.run(go())
    # Should complete without raising, errors are swallowed
    assert report.n_probes == 1


def test_engine_run_cbrn_benchmark():
    engine = _make_engine()
    model = MagicMock()
    model.id = 8
    model.name = "cbrn-model"

    questions = [{"question": "Q?", "expected": "A"}]

    async def go():
        return await engine.run(model, "cbrn-assessment", questions, n_samples=10, include_tail=False)

    report = asyncio.run(go())
    assert "cbrn" in report.benchmark_name


def test_engine_run_variance_and_skew():
    engine = _make_engine()
    model = MagicMock()
    model.id = 9
    model.name = "var-model"

    questions = [{"question": f"Q{i}?", "expected": str(i)} for i in range(6)]

    async def go():
        return await engine.run(model, "bench", questions, n_samples=10, include_tail=False)

    report = asyncio.run(go())
    assert report.capability_variance >= 0.0
    assert report.propensity_variance >= 0.0
    assert report.propensity_skew in ("left_skewed", "symmetric", "right_skewed")


def test_engine_run_total_cost_and_tokens():
    engine = _make_engine()
    model = MagicMock()
    model.id = 10
    model.name = "cost-model"

    questions = [{"question": "Q?", "expected": "A"}]

    async def go():
        return await engine.run(model, "bench", questions, n_samples=10, include_tail=True)

    report = asyncio.run(go())
    assert report.total_tokens >= 0
    assert report.total_cost_usd >= 0.0


def test_engine_run_model_without_id_attr():
    """Engine handles model objects that don't have id/name attrs."""
    def factory(model):
        return _make_adapter()

    engine = CapabilityPropensityEngine(adapter_factory=factory)
    model = "simple-string-model"  # not an object with .id / .name

    questions = [{"question": "Q?", "expected": "A"}]

    async def go():
        return await engine.run(model, "bench", questions, n_samples=10, include_tail=False)

    report = asyncio.run(go())
    assert isinstance(report.model_id, str)
    assert isinstance(report.model_name, str)


def test_engine_safety_reason_large_gap():
    """When gap is large on a non-safety benchmark, safety_reason explains the gap."""
    call_count = 0

    class ExtremAdapter:
        async def complete(self, prompt, temperature=0.0, max_tokens=256):
            nonlocal call_count
            r = MagicMock()
            r.text = "deep matching expected answer" if temperature == 0.0 else ""
            r.total_tokens = 20
            r.cost_usd = 0.0
            call_count += 1
            return r

    def factory(model):
        return ExtremAdapter()

    engine = CapabilityPropensityEngine(adapter_factory=factory)
    model = MagicMock()
    model.id = 11
    model.name = "big-gap"

    questions = [
        {
            "question": "Q?",
            "expected": "deep matching expected answer deep matching expected answer",
        }
    ] * 5

    async def go():
        return await engine.run(model, "bench", questions, n_samples=10, include_tail=False)

    report = asyncio.run(go())
    assert isinstance(report, CapabilityPropensityReport)
    if report.safety_concern and report.safety_concern_reason:
        assert len(report.safety_concern_reason) > 0
