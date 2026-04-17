"""Tests for eval_engine/academic/mmlu.py"""
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

import pytest
from eval_engine.academic.mmlu import MMLURunner, _format_question, CHOICES
from eval_engine.base import ItemResult


def _make_benchmark(**kwargs):
    b = MagicMock()
    b.name = kwargs.get("name", "MMLU (subset)")
    b.dataset_path = kwargs.get("dataset_path", None)
    b.has_dataset = kwargs.get("has_dataset", False)
    b.num_items = kwargs.get("num_items", 10)
    b.config = kwargs.get("config", {})
    b.config_json = kwargs.get("config_json", None)
    return b


def _make_runner():
    b = _make_benchmark()
    return MMLURunner(benchmark=b, bench_library_path="/tmp")


def test_format_question_no_answer():
    item = {"question": "What is 2+2?", "choices": ["1", "2", "3", "4"], "answer": "D"}
    result = _format_question(item, include_answer=False)
    assert "What is 2+2?" in result
    assert "(A)" in result
    assert "(D)" in result
    assert "Answer:" in result
    assert "Answer: D" not in result


def test_format_question_with_answer():
    item = {"question": "What is 2+2?", "choices": ["1", "2", "3", "4"], "answer": "D"}
    result = _format_question(item, include_answer=True)
    assert "Answer: D" in result


def test_score_item_correct_a():
    runner = _make_runner()
    item = {"question": "Q", "choices": ["opt1", "opt2", "opt3", "opt4"], "answer": "A"}
    assert runner.score_item("A", item) == 1.0


def test_score_item_correct_b():
    runner = _make_runner()
    item = {"question": "Q", "choices": ["opt1", "opt2", "opt3", "opt4"], "answer": "B"}
    assert runner.score_item("B is correct", item) == 1.0


def test_score_item_correct_c():
    runner = _make_runner()
    item = {"answer": "C"}
    assert runner.score_item("The answer is C.", item) == 1.0


def test_score_item_correct_d():
    runner = _make_runner()
    item = {"answer": "D"}
    assert runner.score_item("D", item) == 1.0


def test_score_item_wrong():
    runner = _make_runner()
    item = {"answer": "A"}
    assert runner.score_item("B", item) == 0.0


def test_score_item_no_letter():
    runner = _make_runner()
    item = {"answer": "A"}
    assert runner.score_item("I don't know", item) == 0.0


def test_score_item_first_char_fallback():
    runner = _make_runner()
    item = {"answer": "C"}
    # "Correct".upper() = "CORRECT", no \bC\b match but first char is C → matches
    assert runner.score_item("Correct", item) == 1.0


def test_score_item_exact_letter_start():
    runner = _make_runner()
    item = {"answer": "B"}
    assert runner.score_item("B", item) == 1.0


def test_compute_summary_metrics_empty():
    runner = _make_runner()
    result = runner.compute_summary_metrics([])
    assert result["accuracy"] == 0.0


def test_compute_summary_metrics_basic():
    runner = _make_runner()
    results = [
        ItemResult(0, "p", "r", "A", 1.0, 100, 10, 10, 0.0, {"category": "math"}),
        ItemResult(1, "p", "r", "B", 0.0, 100, 10, 10, 0.0, {"category": "math"}),
        ItemResult(2, "p", "r", "C", 1.0, 100, 10, 10, 0.0, {"category": "science"}),
    ]
    summary = runner.compute_summary_metrics(results)
    assert summary["accuracy"] == pytest.approx(2/3, abs=0.001)
    assert summary["num_correct"] == 2
    assert summary["num_total"] == 3
    assert "math" in summary["by_category"]
    assert "science" in summary["by_category"]


def test_compute_summary_metrics_all_correct():
    runner = _make_runner()
    results = [
        ItemResult(i, "p", "r", "A", 1.0, 100, 10, 10, 0.0, {"category": "x"})
        for i in range(5)
    ]
    summary = runner.compute_summary_metrics(results)
    assert summary["accuracy"] == 1.0
    assert summary["accuracy_%"] == 100.0


def test_compute_summary_metrics_unknown_category():
    runner = _make_runner()
    results = [
        ItemResult(0, "p", "r", "A", 1.0, 100, 10, 10, 0.0, {}),
    ]
    summary = runner.compute_summary_metrics(results)
    assert "unknown" in summary["by_category"]


@pytest.mark.asyncio
async def test_build_prompt_no_fewshot():
    runner = _make_runner()
    item = {"question": "Capital of France?", "choices": ["Berlin", "London", "Paris", "Rome"], "answer": "C"}
    prompt = await runner.build_prompt(item, [])
    assert "Capital of France?" in prompt
    assert "(A)" in prompt


@pytest.mark.asyncio
async def test_build_prompt_with_fewshot():
    runner = _make_runner()
    few_shot = [
        {"question": "2+2?", "choices": ["1", "2", "3", "4"], "answer": "D"},
    ]
    item = {"question": "Capital?", "choices": ["A", "B", "C", "D"], "answer": "C"}
    prompt = await runner.build_prompt(item, few_shot)
    assert "2+2?" in prompt
    assert "Answer: D" in prompt
    assert "Capital?" in prompt
