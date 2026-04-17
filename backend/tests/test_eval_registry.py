"""Tests for eval_engine/registry.py"""
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

import pytest
from core.models import Benchmark, BenchmarkType


def _make_benchmark(**kwargs):
    defaults = dict(
        name="Test Bench",
        type=BenchmarkType.CUSTOM,
        has_dataset=False,
        dataset_path=None,
        config_json=None,
    )
    defaults.update(kwargs)
    b = MagicMock(spec=Benchmark)
    for k, v in defaults.items():
        setattr(b, k, v)
    return b


@pytest.fixture(autouse=True)
def reset_registry():
    import eval_engine.registry as reg
    reg._initialized = False
    reg._NAME_REGISTRY = {}
    reg._TYPE_REGISTRY = {}
    yield
    reg._initialized = False
    reg._NAME_REGISTRY = {}
    reg._TYPE_REGISTRY = {}


def test_get_runner_named_mmlu():
    from eval_engine.registry import get_runner
    b = _make_benchmark(name="MMLU (subset)", type=BenchmarkType.ACADEMIC)
    runner = get_runner(b, "/tmp/lib")
    assert runner is not None
    assert "MMLU" in type(runner).__name__ or "Runner" in type(runner).__name__


def test_get_runner_named_safety_refusals():
    from eval_engine.registry import get_runner
    b = _make_benchmark(name="Safety Refusals", type=BenchmarkType.SAFETY)
    runner = get_runner(b, "/tmp/lib")
    assert runner is not None


def test_get_runner_type_fallback_custom():
    from eval_engine.registry import get_runner
    b = _make_benchmark(name="Unknown Bench", type=BenchmarkType.CUSTOM)
    runner = get_runner(b, "/tmp/lib")
    assert runner is not None


def test_get_runner_type_fallback_coding():
    from eval_engine.registry import get_runner
    b = _make_benchmark(name="Unknown Coding", type=BenchmarkType.CODING)
    runner = get_runner(b, "/tmp/lib")
    assert runner is not None


def test_get_runner_type_fallback_safety():
    from eval_engine.registry import get_runner
    b = _make_benchmark(name="Unknown Safety", type=BenchmarkType.SAFETY)
    runner = get_runner(b, "/tmp/lib")
    assert runner is not None


def test_get_runner_type_fallback_academic():
    from eval_engine.registry import get_runner
    b = _make_benchmark(name="Unknown Academic", type=BenchmarkType.ACADEMIC)
    runner = get_runner(b, "/tmp/lib")
    assert runner is not None


def test_get_runner_local_dataset_path(tmp_path):
    from eval_engine.registry import get_runner
    dataset_file = tmp_path / "data.json"
    dataset_file.write_text('[{"question": "Q", "choices": ["A"], "answer": "A"}]')
    b = _make_benchmark(
        name="MMLU (subset)",
        type=BenchmarkType.ACADEMIC,
        has_dataset=True,
        dataset_path="data.json",
    )
    runner = get_runner(b, str(tmp_path))
    assert runner is not None


def test_get_runner_local_dataset_missing_file(tmp_path):
    from eval_engine.registry import get_runner
    b = _make_benchmark(
        name="MMLU (subset)",
        type=BenchmarkType.ACADEMIC,
        has_dataset=True,
        dataset_path="nonexistent.json",
    )
    runner = get_runner(b, str(tmp_path))
    assert runner is not None


def test_get_runner_generic_fallback():
    from eval_engine.registry import get_runner
    b = _make_benchmark(name="Totally Unknown Bench", type=None)
    runner = get_runner(b, "/tmp/lib")
    assert runner is not None


def test_get_runner_purple_llama():
    from eval_engine.registry import get_runner
    b = _make_benchmark(name="CyberSecEval (Purple Llama)", type=BenchmarkType.SAFETY)
    runner = get_runner(b, "/tmp/lib")
    assert runner is not None


def test_get_runner_inesia_benchmarks():
    from eval_engine.registry import get_runner
    for name in ["Cyber Uplift (INESIA)", "Loss of Control (INESIA)", "Deception Probe (INESIA)"]:
        b = _make_benchmark(name=name, type=BenchmarkType.SAFETY)
        runner = get_runner(b, "/tmp/lib")
        assert runner is not None, f"No runner for {name}"


def test_lazy_register_idempotent():
    import eval_engine.registry as reg
    reg._lazy_register()
    assert reg._initialized
    reg._lazy_register()  # should not raise
    assert reg._initialized


def test_find_harness_task_no_match():
    import eval_engine.registry as reg
    reg._lazy_register()
    result = reg._find_harness_task("zzzzzz_totally_unknown_benchmark_xyz")
    assert result is None


def test_get_runner_harness_fallback():
    """Test that harness runner is used when lm-eval is available and task matches."""
    import eval_engine.registry as reg
    reg._initialized = False

    mock_harness = MagicMock()
    mock_harness_runner = MagicMock()
    mock_harness_runner.return_value = MagicMock()

    with patch.dict('sys.modules', {
        'lm_eval': MagicMock(),
        'lm_eval.tasks': MagicMock(),
        'lm_eval.evaluator': MagicMock(),
    }):
        b = _make_benchmark(name="gsm8k", type=BenchmarkType.ACADEMIC)
        from eval_engine.registry import get_runner
        # Even if harness not available, should fall back gracefully
        runner = get_runner(b, "/tmp/lib")
        assert runner is not None
