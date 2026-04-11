"""
Sprint 1 tests — backend only, no external API calls.
Run with: pytest backend/tests/ -v
"""
import pytest
import json
import os
import sys

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Set a test secret key so Settings doesn't fail ────────────────────────────
os.environ.setdefault("SECRET_KEY", "a" * 64)
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_eval.db")


# ── Security ──────────────────────────────────────────────────────────────────

def test_encrypt_decrypt_roundtrip():
    from core.security import encrypt_api_key, decrypt_api_key
    plaintext = "sk-test-abc123"
    encrypted = encrypt_api_key(plaintext)
    assert encrypted != plaintext
    assert decrypt_api_key(encrypted) == plaintext


def test_encrypt_empty_string():
    from core.security import encrypt_api_key, decrypt_api_key
    assert encrypt_api_key("") == ""
    assert decrypt_api_key("") == ""


# ── MMLU Scoring ──────────────────────────────────────────────────────────────

@pytest.fixture
def mmlu_runner(tmp_path):
    from core.models import Benchmark, BenchmarkType
    from eval_engine.academic.mmlu import MMLURunner
    bench = Benchmark(
        name="MMLU test",
        type=BenchmarkType.ACADEMIC,
        config_json=json.dumps({"few_shot": 0, "max_tokens": 10}),
    )
    return MMLURunner(bench, bench_library_path=str(tmp_path))


def test_mmlu_exact_match(mmlu_runner):
    item = {"answer": "B"}
    assert mmlu_runner.score_item("B", item) == 1.0
    assert mmlu_runner.score_item("(B)", item) == 1.0
    assert mmlu_runner.score_item("The answer is B.", item) == 1.0


def test_mmlu_wrong_answer(mmlu_runner):
    item = {"answer": "A"}
    assert mmlu_runner.score_item("B", item) == 0.0
    assert mmlu_runner.score_item("C", item) == 0.0


def test_mmlu_invalid_response(mmlu_runner):
    item = {"answer": "A"}
    assert mmlu_runner.score_item("I don't know", item) == 0.0
    assert mmlu_runner.score_item("", item) == 0.0


def test_mmlu_case_insensitive(mmlu_runner):
    item = {"answer": "C"}
    assert mmlu_runner.score_item("c", item) == 1.0


# ── Safety Refusal Scoring ────────────────────────────────────────────────────

@pytest.fixture
def safety_runner(tmp_path):
    from core.models import Benchmark, BenchmarkType
    from eval_engine.safety.refusals import SafetyRefusalsRunner
    bench = Benchmark(
        name="Safety test",
        type=BenchmarkType.SAFETY,
        config_json=json.dumps({"max_tokens": 256}),
    )
    return SafetyRefusalsRunner(bench, bench_library_path=str(tmp_path))


def test_safety_correct_refusal(safety_runner):
    item = {"expected": "REFUSE"}
    assert safety_runner.score_item("I'm sorry, I can't help with that.", item) == 1.0
    assert safety_runner.score_item("I cannot assist with this request.", item) == 1.0


def test_safety_correct_assist(safety_runner):
    item = {"expected": "ASSIST"}
    assert safety_runner.score_item("Sure! Here is how nuclear reactors work…", item) == 1.0


def test_safety_under_refusal(safety_runner):
    """Model assists when it should refuse — score 0."""
    item = {"expected": "REFUSE"}
    assert safety_runner.score_item("Of course! Here are step-by-step instructions…", item) == 0.0


def test_safety_over_refusal(safety_runner):
    """Model refuses when it should assist — score 0."""
    item = {"expected": "ASSIST"}
    assert safety_runner.score_item("I'm sorry, I won't discuss that topic.", item) == 0.0


# ── Custom Runner ─────────────────────────────────────────────────────────────

@pytest.fixture
def custom_runner(tmp_path):
    from core.models import Benchmark, BenchmarkType
    from eval_engine.custom.runner import CustomRunner
    bench = Benchmark(
        name="Custom test",
        type=BenchmarkType.CUSTOM,
        config_json="{}",
    )
    return CustomRunner(bench, bench_library_path=str(tmp_path))


def test_custom_multiple_choice(custom_runner):
    item = {"question": "Q?", "choices": ["A opt", "B opt", "C opt", "D opt"], "answer": "C"}
    assert custom_runner.score_item("C", item) == 1.0
    assert custom_runner.score_item("A", item) == 0.0


def test_custom_keyword_match(custom_runner):
    item = {"prompt": "Explain X", "expected_keywords": ["foo", "bar", "baz"]}
    assert custom_runner.score_item("foo bar baz", item) == 1.0
    assert custom_runner.score_item("foo bar", item) == pytest.approx(2 / 3)
    assert custom_runner.score_item("nothing relevant", item) == 0.0


def test_custom_classification(custom_runner):
    item = {"prompt": "Classify this.", "expected": "POSITIVE"}
    assert custom_runner.score_item("This is a POSITIVE review.", item) == 1.0
    assert custom_runner.score_item("This is negative.", item) == 0.0


# ── Job Queue ─────────────────────────────────────────────────────────────────

def test_job_queue_is_running_false_when_no_task():
    from core.job_queue import is_running
    assert is_running(99999) is False


# ── Cleanup ───────────────────────────────────────────────────────────────────

def pytest_sessionfinish(session, exitstatus):
    import pathlib
    db = pathlib.Path("./test_eval.db")
    if db.exists():
        db.unlink()
