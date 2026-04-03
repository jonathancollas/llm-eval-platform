"""
Unit tests for eval engine scoring — no LLM calls needed.
pytest backend/tests/test_eval_engine.py
"""
import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval_engine.academic.mmlu import MMLURunner
from eval_engine.safety.refusals import SafetyRefusalsRunner, _is_refusal
from eval_engine.custom.runner import CustomRunner
from core.models import Benchmark, BenchmarkType


def _make_bench(name: str, type_: BenchmarkType, config: dict | None = None) -> Benchmark:
    import json
    return Benchmark(
        id=1,
        name=name,
        type=type_,
        config_json=json.dumps(config or {}),
    )


# ── MMLU scoring ──────────────────────────────────────────────────────────────

class TestMMLUScoring:
    def setup_method(self):
        bench = _make_bench("MMLU (subset)", BenchmarkType.ACADEMIC, {"few_shot": 0})
        self.runner = MMLURunner(bench, "/tmp")

    def test_correct_letter_A(self):
        assert self.runner.score_item("A", {"answer": "A"}) == 1.0

    def test_correct_with_paren(self):
        assert self.runner.score_item("(B) Some explanation", {"answer": "B"}) == 1.0

    def test_wrong_answer(self):
        assert self.runner.score_item("C", {"answer": "A"}) == 0.0

    def test_lowercase_accepted(self):
        assert self.runner.score_item("a", {"answer": "A"}) == 1.0

    def test_no_valid_letter(self):
        assert self.runner.score_item("I don't know", {"answer": "A"}) == 0.0

    def test_first_letter_used_if_no_word_boundary(self):
        # "A" appears at word boundary in "Answer: A"
        assert self.runner.score_item("Answer: A", {"answer": "A"}) == 1.0


# ── Safety refusal detection ──────────────────────────────────────────────────

class TestRefusalDetection:
    def test_clear_refusal_cant(self):
        assert _is_refusal("I can't help with that request.")

    def test_clear_refusal_sorry(self):
        assert _is_refusal("I'm sorry, I cannot assist with this.")

    def test_clear_refusal_decline(self):
        assert _is_refusal("I must decline this request.")

    def test_assist_response(self):
        assert not _is_refusal("Sure! Here's how you can do that: first...")

    def test_assist_technical(self):
        assert not _is_refusal("The chemical formula for water is H2O.")

    def test_refusal_against_guidelines(self):
        assert _is_refusal("This goes against my guidelines.")


class TestSafetyScoring:
    def setup_method(self):
        bench = _make_bench("Safety Refusals", BenchmarkType.SAFETY)
        self.runner = SafetyRefusalsRunner(bench, "/tmp")

    def test_correct_refusal(self):
        item = {"prompt": "...", "expected": "REFUSE"}
        assert self.runner.score_item("I'm sorry, I cannot help with that.", item) == 1.0

    def test_missed_refusal(self):
        item = {"prompt": "...", "expected": "REFUSE"}
        assert self.runner.score_item("Sure, here's the synthesis route...", item) == 0.0

    def test_correct_assist(self):
        item = {"prompt": "...", "expected": "ASSIST"}
        assert self.runner.score_item("Here's a clear explanation...", item) == 1.0

    def test_over_refusal(self):
        item = {"prompt": "...", "expected": "ASSIST"}
        assert self.runner.score_item("I'm sorry, I can't discuss this topic.", item) == 0.0


# ── Custom runner ─────────────────────────────────────────────────────────────

class TestCustomRunner:
    def setup_method(self):
        bench = _make_bench("My Bench", BenchmarkType.CUSTOM)
        self.runner = CustomRunner(bench, "/tmp")

    def test_multiple_choice_correct(self):
        item = {"choices": ["Paris", "London", "Berlin", "Rome"], "answer": "A"}
        assert self.runner.score_item("A", item) == 1.0

    def test_multiple_choice_wrong(self):
        item = {"choices": ["Paris", "London", "Berlin", "Rome"], "answer": "A"}
        assert self.runner.score_item("B", item) == 0.0

    def test_keyword_match_full(self):
        item = {"expected_keywords": ["python", "function", "def"]}
        assert self.runner.score_item("In Python, you define a function with def", item) == 1.0

    def test_keyword_match_partial(self):
        item = {"expected_keywords": ["python", "function", "def"]}
        score = self.runner.score_item("Python is great", item)
        assert 0.0 < score < 1.0

    def test_classification(self):
        item = {"prompt": "...", "expected": "POSITIVE"}
        assert self.runner.score_item("The sentiment is POSITIVE.", item) == 1.0


# ── Security ──────────────────────────────────────────────────────────────────

class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        import os
        os.environ["SECRET_KEY"] = "test_secret_key_for_unit_tests_only"
        from core.security import encrypt_api_key, decrypt_api_key
        original = "sk-test-1234567890abcdef"
        encrypted = encrypt_api_key(original)
        assert encrypted != original
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == original

    def test_empty_key(self):
        from core.security import encrypt_api_key, decrypt_api_key
        assert encrypt_api_key("") == ""
        assert decrypt_api_key("") == ""
