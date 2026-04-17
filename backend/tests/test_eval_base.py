"""Tests for eval_engine/base.py — BaseBenchmarkRunner, _load_dataset_cached, run()."""
import asyncio
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from eval_engine.base import (
    BaseBenchmarkRunner,
    ItemResult,
    RunSummary,
    _load_dataset_cached,
)
from core.models import Benchmark, BenchmarkType, LLMModel, ModelProvider


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_benchmark(**kwargs) -> Benchmark:
    defaults = dict(
        name="test-bench",
        type=BenchmarkType.ACADEMIC,
        dataset_path=None,
        config_json="{}",
        metric="accuracy",
    )
    defaults.update(kwargs)
    return Benchmark(**defaults)


def _make_model() -> LLMModel:
    return LLMModel(
        name="test-model",
        model_id="openai/gpt-test",
        provider=ModelProvider.OPENAI,
        cost_input_per_1k=0.001,
        cost_output_per_1k=0.002,
    )


class ConcreteRunner(BaseBenchmarkRunner):
    """Minimal concrete implementation for testing."""

    async def build_prompt(self, item: dict, few_shot_examples: list[dict]) -> str:
        return item.get("question", "q")

    def score_item(self, response: str, item: dict) -> float:
        return 1.0 if response == item.get("answer", "") else 0.0


# ── _load_dataset_cached ──────────────────────────────────────────────────────

def test_load_dataset_cached_list_file(tmp_path):
    _load_dataset_cached.cache_clear()
    dataset = [{"question": "Q1", "answer": "A1"}, {"question": "Q2", "answer": "A2"}]
    f = tmp_path / "ds.json"
    f.write_text(json.dumps(dataset))

    result = _load_dataset_cached(str(f))
    assert len(result) == 2
    assert result[0]["question"] == "Q1"
    _load_dataset_cached.cache_clear()


def test_load_dataset_cached_dict_with_items(tmp_path):
    _load_dataset_cached.cache_clear()
    dataset = {"items": [{"question": "Q1"}, {"question": "Q2"}], "metadata": {}}
    f = tmp_path / "ds2.json"
    f.write_text(json.dumps(dataset))

    result = _load_dataset_cached(str(f))
    assert len(result) == 2
    _load_dataset_cached.cache_clear()


def test_load_dataset_cached_missing_file():
    _load_dataset_cached.cache_clear()
    result = _load_dataset_cached("/nonexistent/path/dataset.json")
    assert result == []
    _load_dataset_cached.cache_clear()


def test_load_dataset_cached_invalid_json(tmp_path):
    _load_dataset_cached.cache_clear()
    f = tmp_path / "bad.json"
    f.write_text("NOT VALID JSON {{{")

    result = _load_dataset_cached(str(f))
    assert result == []
    _load_dataset_cached.cache_clear()


def test_load_dataset_cached_is_cached(tmp_path):
    _load_dataset_cached.cache_clear()
    dataset = [{"question": "Q1"}]
    f = tmp_path / "cached.json"
    f.write_text(json.dumps(dataset))

    r1 = _load_dataset_cached(str(f))
    r2 = _load_dataset_cached(str(f))
    assert r1 is r2  # same object from cache
    _load_dataset_cached.cache_clear()


# ── invalidate_dataset_cache ──────────────────────────────────────────────────

def test_invalidate_dataset_cache(tmp_path):
    _load_dataset_cached.cache_clear()
    dataset = [{"q": "q1"}]
    f = tmp_path / "inv.json"
    f.write_text(json.dumps(dataset))

    _load_dataset_cached(str(f))
    BaseBenchmarkRunner.invalidate_dataset_cache(str(f))
    # After invalidation, calling again should reload (not raise)
    r = _load_dataset_cached(str(f))
    assert len(r) == 1
    _load_dataset_cached.cache_clear()


# ── load_dataset ──────────────────────────────────────────────────────────────

def test_load_dataset_no_path(tmp_path):
    bench = _make_benchmark(dataset_path=None)
    runner = ConcreteRunner(bench, str(tmp_path))
    assert runner.load_dataset() == []


def test_load_dataset_file_not_found(tmp_path):
    bench = _make_benchmark(dataset_path="no/such/file.json")
    runner = ConcreteRunner(bench, str(tmp_path))
    result = runner.load_dataset()
    assert result == []


def test_load_dataset_file_found(tmp_path):
    _load_dataset_cached.cache_clear()
    items = [{"question": "What?", "answer": "Yes"}]
    ds_dir = tmp_path / "sub"
    ds_dir.mkdir()
    (ds_dir / "data.json").write_text(json.dumps(items))

    bench = _make_benchmark(dataset_path="sub/data.json")
    runner = ConcreteRunner(bench, str(tmp_path))
    result = runner.load_dataset()
    assert len(result) == 1
    _load_dataset_cached.cache_clear()


# ── sample_items ──────────────────────────────────────────────────────────────

def test_sample_items_fewer_than_max():
    bench = _make_benchmark()
    runner = ConcreteRunner(bench, "/")
    items = [{"q": i} for i in range(5)]
    result = runner.sample_items(items, max_samples=10, seed=42)
    assert len(result) == 5


def test_sample_items_more_than_max():
    bench = _make_benchmark()
    runner = ConcreteRunner(bench, "/")
    items = [{"q": i} for i in range(20)]
    result = runner.sample_items(items, max_samples=5, seed=42)
    assert len(result) == 5


def test_sample_items_deterministic():
    bench = _make_benchmark()
    runner = ConcreteRunner(bench, "/")
    items = [{"q": i} for i in range(50)]
    r1 = runner.sample_items(items, max_samples=10, seed=99)
    r2 = runner.sample_items(items, max_samples=10, seed=99)
    assert r1 == r2


def test_sample_items_zero_max():
    bench = _make_benchmark()
    runner = ConcreteRunner(bench, "/")
    items = [{"q": i} for i in range(5)]
    result = runner.sample_items(items, max_samples=0, seed=42)
    assert len(result) == 5  # 0 means no limit


# ── compute_summary_metrics ───────────────────────────────────────────────────

def test_compute_summary_metrics_empty():
    bench = _make_benchmark()
    runner = ConcreteRunner(bench, "/")
    assert runner.compute_summary_metrics([]) == {}


def test_compute_summary_metrics_accuracy():
    bench = _make_benchmark()
    runner = ConcreteRunner(bench, "/")
    results = [
        ItemResult(0, "p", "r", "e", 1.0, 0, 0, 0, 0.0),
        ItemResult(1, "p", "r", "e", 0.5, 0, 0, 0, 0.0),
        ItemResult(2, "p", "r", "e", 0.0, 0, 0, 0, 0.0),
    ]
    metrics = runner.compute_summary_metrics(results)
    assert abs(metrics["accuracy"] - 0.5) < 1e-9


# ── run() — no dataset ────────────────────────────────────────────────────────

def test_run_no_dataset(tmp_path):
    bench = _make_benchmark(dataset_path="nonexistent.json")
    runner = ConcreteRunner(bench, str(tmp_path))
    model = _make_model()

    async def go():
        return await runner.run(model, max_samples=10, seed=42, temperature=0.0)

    summary = asyncio.run(go())
    assert summary.score == 0.0
    assert summary.num_items == 0
    assert summary.metrics.get("error") == "no_dataset"


# ── run() — with dataset ──────────────────────────────────────────────────────

def test_run_with_dataset_success(tmp_path):
    _load_dataset_cached.cache_clear()
    items = [
        {"question": "1+1?", "answer": "2"},
        {"question": "2+2?", "answer": "4"},
    ]
    ds_file = tmp_path / "test.json"
    ds_file.write_text(json.dumps(items))

    bench = _make_benchmark(dataset_path="test.json", metric="accuracy")
    runner = ConcreteRunner(bench, str(tmp_path))
    model = _make_model()

    fake_result = MagicMock()
    fake_result.text = "2"
    fake_result.latency_ms = 100
    fake_result.input_tokens = 10
    fake_result.output_tokens = 5
    fake_result.cost_usd = 0.001

    async def go():
        with patch("eval_engine.litellm_client.complete", AsyncMock(return_value=fake_result)):
            return await runner.run(model, max_samples=10, seed=42, temperature=0.0)

    summary = asyncio.run(go())
    assert summary.num_items == 2
    assert isinstance(summary.score, float)
    _load_dataset_cached.cache_clear()


def test_run_with_progress_callback(tmp_path):
    _load_dataset_cached.cache_clear()
    items = [{"question": "Q?", "answer": "A"}]
    ds_file = tmp_path / "progress.json"
    ds_file.write_text(json.dumps(items))

    bench = _make_benchmark(dataset_path="progress.json")
    runner = ConcreteRunner(bench, str(tmp_path))
    model = _make_model()

    callback_calls = []

    def progress_cb(current, total, item_result):
        callback_calls.append((current, total))

    fake_result = MagicMock()
    fake_result.text = "A"
    fake_result.latency_ms = 50
    fake_result.input_tokens = 5
    fake_result.output_tokens = 3
    fake_result.cost_usd = 0.0

    async def go():
        with patch("eval_engine.litellm_client.complete", AsyncMock(return_value=fake_result)):
            return await runner.run(
                model,
                max_samples=10,
                seed=42,
                temperature=0.0,
                progress_callback=progress_cb,
            )

    asyncio.run(go())
    assert len(callback_calls) == 1
    assert callback_calls[0] == (1, 1)
    _load_dataset_cached.cache_clear()


def test_run_item_raises_exception(tmp_path):
    """When complete() raises, the item gets score=0 and an error metadata entry."""
    _load_dataset_cached.cache_clear()
    items = [{"question": "Q?", "answer": "A"}]
    ds_file = tmp_path / "err.json"
    ds_file.write_text(json.dumps(items))

    bench = _make_benchmark(dataset_path="err.json")
    runner = ConcreteRunner(bench, str(tmp_path))
    model = _make_model()

    async def go():
        with patch("eval_engine.litellm_client.complete", AsyncMock(side_effect=RuntimeError("LLM down"))):
            return await runner.run(model, max_samples=10, seed=42, temperature=0.0)

    summary = asyncio.run(go())
    assert summary.num_items == 1
    assert summary.item_results[0].score == 0.0
    assert "error" in summary.item_results[0].metadata
    _load_dataset_cached.cache_clear()


def test_run_uses_few_shot_examples(tmp_path):
    """Few-shot examples are sampled from pool when configured."""
    _load_dataset_cached.cache_clear()
    items = [{"question": f"Q{i}?", "answer": str(i)} for i in range(20)]
    ds_file = tmp_path / "fewshot.json"
    ds_file.write_text(json.dumps(items))

    bench = _make_benchmark(
        dataset_path="fewshot.json",
        config_json=json.dumps({"few_shot": 3, "max_tokens": 64}),
    )
    runner = ConcreteRunner(bench, str(tmp_path))
    model = _make_model()

    fake_result = MagicMock()
    fake_result.text = "0"
    fake_result.latency_ms = 10
    fake_result.input_tokens = 5
    fake_result.output_tokens = 2
    fake_result.cost_usd = 0.0

    async def go():
        with patch("eval_engine.litellm_client.complete", AsyncMock(return_value=fake_result)):
            return await runner.run(model, max_samples=5, seed=42, temperature=0.0)

    summary = asyncio.run(go())
    assert summary.num_items == 5
    _load_dataset_cached.cache_clear()


def test_run_custom_metric_from_config(tmp_path):
    """Primary score is pulled from benchmark.metric key if present."""
    _load_dataset_cached.cache_clear()

    class CustomMetricRunner(BaseBenchmarkRunner):
        async def build_prompt(self, item, few_shot):
            return "q"

        def score_item(self, response, item):
            return 0.9

        def compute_summary_metrics(self, results):
            return {"pass@1": 0.75, "accuracy": 0.5}

    items = [{"question": "x"}]
    ds_file = tmp_path / "custom.json"
    ds_file.write_text(json.dumps(items))

    bench = _make_benchmark(dataset_path="custom.json", metric="pass@1")
    runner = CustomMetricRunner(bench, str(tmp_path))
    model = _make_model()

    fake_result = MagicMock()
    fake_result.text = "resp"
    fake_result.latency_ms = 10
    fake_result.input_tokens = 5
    fake_result.output_tokens = 2
    fake_result.cost_usd = 0.0

    async def go():
        with patch("eval_engine.litellm_client.complete", AsyncMock(return_value=fake_result)):
            return await runner.run(model, max_samples=10, seed=42, temperature=0.0)

    summary = asyncio.run(go())
    assert summary.score == 0.75
    _load_dataset_cached.cache_clear()
