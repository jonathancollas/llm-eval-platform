"""
Tests for eval_engine/harness_runner.py
Covers: get_available_harness_tasks (lm_eval present/absent),
        get_catalog_for_api, HarnessRunner.run (success + error path),
        HarnessRunner._run_sync with fully mocked evaluator.
"""
import os
import secrets
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

# Mock lm_eval before any imports of harness_runner
mock_lm_eval = MagicMock()
mock_lm_eval_tasks = MagicMock()
mock_lm_eval_evaluator = MagicMock()
mock_lm_eval_models = MagicMock()
mock_lm_eval_models_openai = MagicMock()

sys.modules.setdefault("lm_eval", mock_lm_eval)
sys.modules.setdefault("lm_eval.tasks", mock_lm_eval_tasks)
sys.modules.setdefault("lm_eval.evaluator", mock_lm_eval_evaluator)
sys.modules.setdefault("lm_eval.models", mock_lm_eval_models)
sys.modules.setdefault("lm_eval.models.openai_completions", mock_lm_eval_models_openai)

from eval_engine.harness_runner import (
    HARNESS_CATALOG,
    HarnessRunner,
    _task_display_name,
    get_available_harness_tasks,
    get_catalog_for_api,
)
import eval_engine.harness_runner as harness_mod


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_available_tasks():
    """Reset module-level cache between tests."""
    harness_mod._available_tasks = None
    yield
    harness_mod._available_tasks = None


def _make_model(name="gpt-4o", context_length=4096):
    m = MagicMock()
    m.name = name
    m.model_id = "openai/gpt-4o"
    m.context_length = context_length
    m.api_key_encrypted = None
    m.api_base = None
    return m


def _make_benchmark(task_name="hellaswag"):
    b = MagicMock()
    b.name = task_name
    b.dataset_path = None
    return b


# ══════════════════════════════════════════════════════════════════════════════
# get_available_harness_tasks
# ══════════════════════════════════════════════════════════════════════════════

def test_get_available_tasks_lm_eval_present():
    """When lm_eval TaskManager is importable, use its task list."""
    mock_tm = MagicMock()
    mock_tm.all_tasks = ["hellaswag", "arc_easy", "mmlu"]
    mock_lm_eval_tasks.TaskManager.return_value = mock_tm

    tasks = get_available_harness_tasks()
    assert "hellaswag" in tasks
    assert isinstance(tasks, set)


def test_get_available_tasks_lm_eval_unavailable():
    """When lm_eval raises on import, falls back to HARNESS_CATALOG keys."""
    with patch.dict("sys.modules", {"lm_eval.tasks": None}):
        harness_mod._available_tasks = None
        # Force TaskManager to raise
        original = sys.modules.get("lm_eval.tasks")
        sys.modules["lm_eval.tasks"] = None
        try:
            harness_mod._available_tasks = None
            tasks = get_available_harness_tasks()
            assert isinstance(tasks, set)
            assert len(tasks) > 0
        finally:
            sys.modules["lm_eval.tasks"] = original


def test_get_available_tasks_cached():
    """Second call returns same cached set."""
    mock_tm = MagicMock()
    mock_tm.all_tasks = ["hellaswag"]
    mock_lm_eval_tasks.TaskManager.return_value = mock_tm

    t1 = get_available_harness_tasks()
    t2 = get_available_harness_tasks()
    assert t1 is t2


def test_get_available_tasks_task_manager_raises():
    """When TaskManager() itself raises, falls back to HARNESS_CATALOG."""
    mock_lm_eval_tasks.TaskManager.side_effect = RuntimeError("broken")
    try:
        tasks = get_available_harness_tasks()
        assert isinstance(tasks, set)
        assert len(tasks) > 0
    finally:
        mock_lm_eval_tasks.TaskManager.side_effect = None


# ══════════════════════════════════════════════════════════════════════════════
# get_catalog_for_api
# ══════════════════════════════════════════════════════════════════════════════

def test_get_catalog_for_api_returns_list():
    harness_mod._available_tasks = set(HARNESS_CATALOG.keys())
    catalog = get_catalog_for_api()
    assert isinstance(catalog, list)
    assert len(catalog) > 0


def test_get_catalog_for_api_structure():
    harness_mod._available_tasks = set(HARNESS_CATALOG.keys())
    catalog = get_catalog_for_api()
    item = catalog[0]
    for key in ("key", "name", "domain", "metric", "few_shot", "description", "source", "is_frontier"):
        assert key in item, f"Missing key: {key}"


def test_get_catalog_for_api_filters_unavailable():
    """Only tasks in available set appear in catalog."""
    harness_mod._available_tasks = {"hellaswag"}
    catalog = get_catalog_for_api()
    keys = {c["key"] for c in catalog}
    assert keys == {"hellaswag"}


def test_get_catalog_for_api_sorted_by_domain_name():
    harness_mod._available_tasks = {"hellaswag", "mmlu", "gsm8k"}
    catalog = get_catalog_for_api()
    pairs = [(c["domain"], c["name"]) for c in catalog]
    assert pairs == sorted(pairs)


def test_get_catalog_for_api_is_frontier_flag():
    harness_mod._available_tasks = set(HARNESS_CATALOG.keys())
    catalog = get_catalog_for_api()
    for item in catalog:
        assert isinstance(item["is_frontier"], bool)


# ══════════════════════════════════════════════════════════════════════════════
# _task_display_name
# ══════════════════════════════════════════════════════════════════════════════

def test_task_display_name_known_task():
    assert _task_display_name("hellaswag") == "HellaSwag"
    assert _task_display_name("mmlu") == "MMLU"
    assert _task_display_name("gsm8k") == "GSM8K"


def test_task_display_name_unknown_task_title_case():
    result = _task_display_name("some_custom_task")
    assert result == "Some Custom Task"


def test_task_display_name_wmdp():
    assert _task_display_name("wmdp_bio") == "WMDP — Biologie (CBRN)"


# ══════════════════════════════════════════════════════════════════════════════
# HarnessRunner.build_prompt / score_item
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_harness_runner_build_prompt_returns_empty():
    bench = _make_benchmark()
    runner = HarnessRunner(bench, "/bench", "hellaswag")
    result = await runner.build_prompt({}, [])
    assert result == ""


def test_harness_runner_score_item_returns_zero():
    bench = _make_benchmark()
    runner = HarnessRunner(bench, "/bench", "hellaswag")
    assert runner.score_item("any response", {}) == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# HarnessRunner.run — success path
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_harness_runner_run_success():
    bench = _make_benchmark("hellaswag")
    runner = HarnessRunner(bench, "/bench", "hellaswag")
    model = _make_model()

    fake_summary = MagicMock()
    fake_summary.score = 0.75
    fake_summary.metrics = {"acc,none": 0.75}
    fake_summary.total_cost_usd = 0.0
    fake_summary.total_latency_ms = 1000
    fake_summary.num_items = 10
    fake_summary.item_results = []

    with patch.object(runner, "_run_sync", return_value=fake_summary):
        result = await runner.run(model, max_samples=10, seed=42, temperature=0.0)
    assert result.score == 0.75


@pytest.mark.asyncio
async def test_harness_runner_run_error_path():
    """When _run_sync raises, run() returns error RunSummary with score=0."""
    bench = _make_benchmark("hellaswag")
    runner = HarnessRunner(bench, "/bench", "hellaswag")
    model = _make_model()

    with patch.object(runner, "_run_sync", side_effect=RuntimeError("lm_eval crashed")):
        result = await runner.run(model, max_samples=5, seed=0, temperature=0.0)
    assert result.score == 0.0
    assert "error" in result.metrics
    assert "lm_eval crashed" in result.metrics["error"]


# ══════════════════════════════════════════════════════════════════════════════
# HarnessRunner._run_sync
# ══════════════════════════════════════════════════════════════════════════════

def test_harness_runner_run_sync_basic():
    """_run_sync with fully mocked evaluator and LocalCompletionsAPI."""
    bench = _make_benchmark("hellaswag")
    runner = HarnessRunner(bench, "/bench", "hellaswag")
    model = _make_model()

    mock_lm_instance = MagicMock()
    mock_lm_eval_models_openai.LocalCompletionsAPI.return_value = mock_lm_instance

    fake_results = {
        "results": {"hellaswag": {"acc,none": 0.82}},
        "samples": {"hellaswag": [
            {"doc": {"query": "test question"}, "resps": [["answer"]], "target": "ans", "acc": 0.82},
        ]},
    }
    mock_lm_eval_evaluator.simple_evaluate.return_value = fake_results

    with patch("eval_engine.harness_runner.evaluator", mock_lm_eval_evaluator), \
         patch("eval_engine.harness_runner.LocalCompletionsAPI", mock_lm_eval_models_openai.LocalCompletionsAPI), \
         patch("eval_engine.litellm_client._build_litellm_model_str", return_value="openai/gpt-4o"), \
         patch("eval_engine.litellm_client._build_kwargs", return_value={"api_key": "sk-test", "api_base": "https://api.openai.com/v1"}), \
         patch("eval_engine.harness_runner.get_settings") as mock_settings:
        mock_settings.return_value.bench_library_path = "/bench"
        result = runner._run_sync(model, max_samples=5, seed=42, temperature=0.0)

    assert result.score == pytest.approx(0.82, abs=0.01)
    assert result.num_items == 1


def test_harness_runner_run_sync_wmdp_inverted():
    """WMDP tasks invert the score (1.0 - score)."""
    bench = _make_benchmark("wmdp_bio")
    runner = HarnessRunner(bench, "/bench", "wmdp_bio")
    model = _make_model()

    mock_lm_instance = MagicMock()
    mock_lm_eval_models_openai.LocalCompletionsAPI.return_value = mock_lm_instance

    fake_results = {
        "results": {"wmdp_bio": {"acc,none": 0.3}},
        "samples": {},
    }
    mock_lm_eval_evaluator.simple_evaluate.return_value = fake_results

    with patch("eval_engine.harness_runner.evaluator", mock_lm_eval_evaluator), \
         patch("eval_engine.harness_runner.LocalCompletionsAPI", mock_lm_eval_models_openai.LocalCompletionsAPI), \
         patch("eval_engine.litellm_client._build_litellm_model_str", return_value="openai/gpt-4o"), \
         patch("eval_engine.litellm_client._build_kwargs", return_value={"api_key": "sk-test"}), \
         patch("eval_engine.harness_runner.get_settings") as mock_settings:
        mock_settings.return_value.bench_library_path = "/bench"
        result = runner._run_sync(model, max_samples=5, seed=42, temperature=0.0)

    assert result.score == pytest.approx(0.7, abs=0.01)


def test_harness_runner_run_sync_no_api_key():
    """When api_key is empty, os.environ is not set."""
    bench = _make_benchmark("mmlu")
    runner = HarnessRunner(bench, "/bench", "mmlu")
    model = _make_model()

    mock_lm_eval_models_openai.LocalCompletionsAPI.return_value = MagicMock()
    fake_results = {"results": {"mmlu": {"acc,none": 0.6}}, "samples": {}}
    mock_lm_eval_evaluator.simple_evaluate.return_value = fake_results

    with patch("eval_engine.harness_runner.evaluator", mock_lm_eval_evaluator), \
         patch("eval_engine.harness_runner.LocalCompletionsAPI", mock_lm_eval_models_openai.LocalCompletionsAPI), \
         patch("eval_engine.litellm_client._build_litellm_model_str", return_value="openai/gpt-4o"), \
         patch("eval_engine.litellm_client._build_kwargs", return_value={}), \
         patch("eval_engine.harness_runner.get_settings") as mock_settings:
        mock_settings.return_value.bench_library_path = "/bench"
        result = runner._run_sync(model, max_samples=None, seed=0, temperature=0.0)

    assert result.score == pytest.approx(0.6, abs=0.01)
