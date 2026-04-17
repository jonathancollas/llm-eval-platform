"""Tests for eval_engine/custom/runner.py"""
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

import pytest
from eval_engine.custom.runner import CustomRunner


def _make_runner():
    b = MagicMock()
    b.name = "Custom Test"
    b.dataset_path = None
    b.has_dataset = False
    b.num_items = 10
    b.config = {}
    return CustomRunner(benchmark=b, bench_library_path="/tmp")


def test_detect_format_multiple_choice():
    runner = _make_runner()
    item = {"question": "Q?", "choices": ["A", "B"], "answer": "A"}
    assert runner._detect_format(item) == "multiple_choice"


def test_detect_format_keyword_match():
    runner = _make_runner()
    item = {"prompt": "Explain X", "expected_keywords": ["keyword1"]}
    assert runner._detect_format(item) == "keyword_match"


def test_detect_format_classification():
    runner = _make_runner()
    item = {"prompt": "Classify this", "expected": "POSITIVE"}
    assert runner._detect_format(item) == "classification"


def test_detect_format_unknown():
    runner = _make_runner()
    item = {"something": "else"}
    assert runner._detect_format(item) == "unknown"


def test_score_multiple_choice_correct():
    runner = _make_runner()
    item = {"choices": ["opt1", "opt2", "opt3", "opt4"], "answer": "B"}
    assert runner.score_item("B", item) == 1.0


def test_score_multiple_choice_wrong():
    runner = _make_runner()
    item = {"choices": ["opt1", "opt2", "opt3", "opt4"], "answer": "A"}
    assert runner.score_item("B", item) == 0.0


def test_score_multiple_choice_no_letter():
    runner = _make_runner()
    item = {"choices": ["opt1", "opt2"], "answer": "A"}
    assert runner.score_item("I dunno", item) == 0.0


def test_score_keyword_match_all_hit():
    runner = _make_runner()
    item = {"expected_keywords": ["foo", "bar"]}
    assert runner.score_item("foo and bar are here", item) == 1.0


def test_score_keyword_match_partial():
    runner = _make_runner()
    item = {"expected_keywords": ["foo", "bar", "baz"]}
    score = runner.score_item("foo is here", item)
    assert score == pytest.approx(1/3, abs=0.01)


def test_score_keyword_match_none():
    runner = _make_runner()
    item = {"expected_keywords": ["foo", "bar"]}
    assert runner.score_item("nothing relevant", item) == 0.0


def test_score_keyword_match_empty_keywords():
    runner = _make_runner()
    item = {"expected_keywords": []}
    assert runner.score_item("anything", item) == 0.0


def test_score_classification_correct():
    runner = _make_runner()
    item = {"prompt": "Classify", "expected": "POSITIVE"}
    assert runner.score_item("POSITIVE sentiment", item) == 1.0


def test_score_classification_wrong():
    runner = _make_runner()
    item = {"prompt": "Classify", "expected": "POSITIVE"}
    assert runner.score_item("NEGATIVE", item) == 0.0


def test_score_classification_case_insensitive():
    runner = _make_runner()
    item = {"prompt": "Classify", "expected": "positive"}
    assert runner.score_item("This is POSITIVE", item) == 1.0


def test_score_unknown_format():
    runner = _make_runner()
    item = {"something": "else"}
    assert runner.score_item("response", item) == 0.0


@pytest.mark.asyncio
async def test_build_prompt_multiple_choice():
    runner = _make_runner()
    item = {"question": "What is Python?", "choices": ["A language", "A snake", "A tool", "A film"], "answer": "A"}
    prompt = await runner.build_prompt(item, [])
    assert "What is Python?" in prompt
    assert "(A)" in prompt
    assert "Answer:" in prompt


@pytest.mark.asyncio
async def test_build_prompt_default():
    runner = _make_runner()
    item = {"prompt": "Describe the sky"}
    prompt = await runner.build_prompt(item, [])
    assert "Describe the sky" in prompt


@pytest.mark.asyncio
async def test_build_prompt_question_field():
    runner = _make_runner()
    item = {"question": "What is AI?"}
    prompt = await runner.build_prompt(item, [])
    assert "What is AI?" in prompt
