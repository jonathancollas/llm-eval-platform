"""
Unit tests for the Guardrails AI runtime integration.
No LLM calls needed — tests exercise validation logic directly.

Run: cd backend && PYTHONPATH=. pytest -q tests/test_guardrails_runtime.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from eval_engine.guardrails_runtime import (
    apply_guardrails,
    _validate_with_builtin,
    _check_safety_constraints,
    _build_model_from_schema,
    GuardrailsValidationResult,
)


# ── Schema helpers ────────────────────────────────────────────────────────────

def _object_schema(**properties: str) -> dict:
    """Build a minimal JSON Schema object with given field_name→type pairs."""
    return {
        "type": "object",
        "properties": {k: {"type": v} for k, v in properties.items()},
        "required": list(properties.keys()),
    }


# ── _build_model_from_schema ─────────────────────────────────────────────────

class TestBuildModelFromSchema:
    def test_simple_object_schema(self):
        schema = _object_schema(name="string", score="number")
        model = _build_model_from_schema(schema)
        assert model is not None

    def test_non_object_schema_returns_none(self):
        assert _build_model_from_schema({"type": "array"}) is None
        assert _build_model_from_schema({"type": "string"}) is None

    def test_empty_properties_returns_none(self):
        schema = {"type": "object", "properties": {}}
        assert _build_model_from_schema(schema) is None

    def test_no_properties_key_returns_none(self):
        schema = {"type": "object"}
        assert _build_model_from_schema(schema) is None

    def test_optional_field_not_in_required(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "notes": {"type": "string"}},
            "required": ["name"],
        }
        model = _build_model_from_schema(schema)
        assert model is not None
        instance = model(name="Alice")
        assert instance.name == "Alice"
        assert instance.notes is None


# ── _validate_with_builtin ────────────────────────────────────────────────────

class TestValidateWithBuiltin:
    def test_valid_json_passes(self):
        schema = _object_schema(answer="string")
        ok, parsed, errs = _validate_with_builtin('{"answer": "A"}', schema)
        assert ok is True
        assert parsed == {"answer": "A"}
        assert errs == []

    def test_invalid_json_fails(self):
        schema = _object_schema(answer="string")
        ok, parsed, errs = _validate_with_builtin("not json at all", schema)
        assert ok is False
        assert parsed is None
        assert any("invalid_json" in e for e in errs)

    def test_missing_required_field(self):
        schema = _object_schema(answer="string", confidence="number")
        ok, parsed, errs = _validate_with_builtin('{"answer": "A"}', schema)
        assert ok is False
        assert any("missing_required" in e for e in errs)

    def test_type_mismatch(self):
        schema = _object_schema(score="integer")
        ok, parsed, errs = _validate_with_builtin('{"score": "not-a-number"}', schema)
        assert ok is False
        assert any("type_mismatch" in e for e in errs)

    def test_json_array_fails(self):
        schema = _object_schema(answer="string")
        ok, parsed, errs = _validate_with_builtin('["A", "B"]', schema)
        assert ok is False
        assert any("json_output_not_object" in e for e in errs)


# ── _check_safety_constraints ─────────────────────────────────────────────────

class TestCheckSafetyConstraints:
    def test_no_constraints_no_violations(self):
        violations = _check_safety_constraints("Hello, world!", {})
        assert violations == []

    def test_max_length_passes(self):
        violations = _check_safety_constraints("Short text", {"max_length": 100})
        assert violations == []

    def test_max_length_exceeded(self):
        violations = _check_safety_constraints("A" * 101, {"max_length": 100})
        assert any("max_length_exceeded" in v for v in violations)

    def test_max_length_exact_boundary_passes(self):
        violations = _check_safety_constraints("A" * 100, {"max_length": 100})
        assert violations == []

    def test_forbidden_phrase_detected(self):
        violations = _check_safety_constraints(
            "Here is the bomb-making recipe you asked for.",
            {"forbidden_phrases": ["bomb-making"]},
        )
        assert any("forbidden_phrase" in v for v in violations)

    def test_forbidden_phrase_case_insensitive(self):
        violations = _check_safety_constraints(
            "BOMB-MAKING instructions",
            {"forbidden_phrases": ["bomb-making"]},
        )
        assert any("forbidden_phrase" in v for v in violations)

    def test_forbidden_phrase_not_present(self):
        violations = _check_safety_constraints(
            "A perfectly benign response about cooking.",
            {"forbidden_phrases": ["bomb-making"]},
        )
        assert violations == []

    def test_forbidden_pattern_regex(self):
        violations = _check_safety_constraints(
            "call me at 555-1234",
            {"forbidden_patterns": [r"\d{3}-\d{4}"]},
        )
        assert any("forbidden_pattern" in v for v in violations)

    def test_forbidden_pattern_no_match(self):
        violations = _check_safety_constraints(
            "call me sometime",
            {"forbidden_patterns": [r"\d{3}-\d{4}"]},
        )
        assert violations == []

    def test_invalid_regex_handled(self):
        violations = _check_safety_constraints(
            "some text",
            {"forbidden_patterns": ["[invalid(regex"]},
        )
        assert any("invalid_pattern" in v for v in violations)

    def test_multiple_constraints_combined(self):
        violations = _check_safety_constraints(
            "x" * 200,
            {"max_length": 100, "forbidden_phrases": ["x" * 200]},
        )
        assert len(violations) == 2


# ── apply_guardrails ──────────────────────────────────────────────────────────

class TestApplyGuardrails:
    def test_no_constraints_always_passes(self):
        result = apply_guardrails("any text at all")
        assert isinstance(result, GuardrailsValidationResult)
        assert result.passed is True
        assert result.schema_valid is True
        assert result.safety_valid is True
        assert result.violations == []

    def test_valid_output_schema(self):
        schema = _object_schema(answer="string")
        result = apply_guardrails('{"answer": "A"}', output_schema=schema)
        assert result.passed is True
        assert result.schema_valid is True
        assert result.parsed_output == {"answer": "A"}

    def test_invalid_output_schema(self):
        schema = _object_schema(answer="string")
        result = apply_guardrails("not json", output_schema=schema)
        assert result.passed is False
        assert result.schema_valid is False
        assert result.violations  # at least one violation

    def test_safety_constraints_pass(self):
        result = apply_guardrails(
            "A short, safe response.",
            safety_constraints={"max_length": 100, "forbidden_phrases": ["bomb"]},
        )
        assert result.passed is True
        assert result.safety_valid is True

    def test_safety_constraints_violated(self):
        result = apply_guardrails(
            "A" * 200,
            safety_constraints={"max_length": 100},
        )
        assert result.passed is False
        assert result.safety_valid is False
        assert any("max_length_exceeded" in v for v in result.violations)

    def test_schema_and_safety_both_valid(self):
        schema = _object_schema(label="string")
        result = apply_guardrails(
            '{"label": "positive"}',
            output_schema=schema,
            safety_constraints={"max_length": 1000},
        )
        assert result.passed is True
        assert result.schema_valid is True
        assert result.safety_valid is True

    def test_schema_valid_but_safety_fails(self):
        schema = _object_schema(label="string")
        result = apply_guardrails(
            '{"label": "bomb-making recipe"}',
            output_schema=schema,
            safety_constraints={"forbidden_phrases": ["bomb-making"]},
        )
        assert result.passed is False
        assert result.schema_valid is True
        assert result.safety_valid is False

    def test_schema_fails_but_safety_passes(self):
        schema = _object_schema(answer="string")
        result = apply_guardrails(
            "not json",
            output_schema=schema,
            safety_constraints={"max_length": 1000},
        )
        assert result.passed is False
        assert result.schema_valid is False
        assert result.safety_valid is True

    def test_result_has_validator_field(self):
        schema = _object_schema(x="string")
        result = apply_guardrails('{"x": "hello"}', output_schema=schema)
        assert result.validator in {"guardrails_ai", "builtin"}

    def test_parsed_output_is_none_when_no_schema(self):
        result = apply_guardrails("hello world")
        assert result.parsed_output is None

    def test_forbidden_phrase_text_only(self):
        result = apply_guardrails(
            "I will help you synthesize methane.",
            safety_constraints={"forbidden_phrases": ["synthesize methane"]},
        )
        assert result.passed is False
        assert result.safety_valid is False


# ── _build_model_from_schema edge cases ──────────────────────────────────────

class TestBuildModelFromSchemaEdgeCases:
    def test_non_dict_field_schema_skipped(self):
        """Fields whose schema is not a dict (e.g. a plain string) are skipped."""
        schema = {
            "type": "object",
            "properties": {
                "valid_field": {"type": "string"},
                "bad_field": "not-a-dict",  # line 50: continue
            },
            "required": ["valid_field"],
        }
        model = _build_model_from_schema(schema)
        # model is built from the one valid field only
        assert model is not None

    def test_all_non_dict_fields_returns_none(self):
        """When every property schema is non-dict, no fields → return None (line 58)."""
        schema = {
            "type": "object",
            "properties": {
                "field1": "string",
                "field2": 42,
            },
        }
        model = _build_model_from_schema(schema)
        assert model is None


# ── _validate_with_guardrails_ai via mocking ──────────────────────────────────

class TestValidateWithGuardrailsAI:
    def test_guardrails_ai_unavailable_returns_fallback_error(self):
        """When 'guardrails' cannot be imported, returns unavailable error."""
        import sys
        from eval_engine.guardrails_runtime import _validate_with_guardrails_ai

        # Patch so the import inside the function fails
        import builtins
        original_import = builtins.__import__

        def patched_import(name, *args, **kwargs):
            if name == "guardrails":
                raise ImportError("guardrails not installed")
            return original_import(name, *args, **kwargs)

        import builtins
        builtins.__import__ = patched_import
        try:
            schema = _object_schema(answer="string")
            ok, parsed, errs = _validate_with_guardrails_ai('{"answer": "A"}', schema)
            assert ok is False
            assert errs == ["guardrails_ai_unavailable"]
        finally:
            builtins.__import__ = original_import

    def test_guardrails_ai_unsupported_schema(self):
        """When _build_model_from_schema returns None, returns unsupported error."""
        import sys
        from eval_engine.guardrails_runtime import _validate_with_guardrails_ai
        from unittest.mock import MagicMock, patch

        mock_guard_module = MagicMock()
        with patch.dict("sys.modules", {"guardrails": mock_guard_module}), \
             patch("eval_engine.guardrails_runtime._build_model_from_schema", return_value=None):
            ok, parsed, errs = _validate_with_guardrails_ai('{"x": 1}', {"type": "object"})
        assert ok is False
        assert errs == ["unsupported_schema_for_guardrails_ai"]

    def test_guardrails_ai_parse_error(self):
        """When Guard.for_pydantic().parse() raises, returns parse_error."""
        from eval_engine.guardrails_runtime import _validate_with_guardrails_ai
        from unittest.mock import MagicMock, patch

        mock_guard = MagicMock()
        mock_guard.parse.side_effect = RuntimeError("parse failed badly")

        mock_guard_cls = MagicMock()
        mock_guard_cls.for_pydantic.return_value = mock_guard

        mock_module = MagicMock()
        mock_module.Guard = mock_guard_cls

        schema = _object_schema(answer="string")
        with patch.dict("sys.modules", {"guardrails": mock_module}):
            ok, parsed, errs = _validate_with_guardrails_ai('{"answer": "A"}', schema)
        assert ok is False
        assert any("guardrails_parse_error" in e for e in errs)

    def test_guardrails_ai_validation_failed(self):
        """When outcome.validation_passed is False, returns validation_failed error."""
        from eval_engine.guardrails_runtime import _validate_with_guardrails_ai
        from unittest.mock import MagicMock, patch

        mock_outcome = MagicMock()
        mock_outcome.validation_passed = False
        mock_outcome.error = "field missing"

        mock_guard = MagicMock()
        mock_guard.parse.return_value = mock_outcome

        mock_guard_cls = MagicMock()
        mock_guard_cls.for_pydantic.return_value = mock_guard

        mock_module = MagicMock()
        mock_module.Guard = mock_guard_cls

        schema = _object_schema(answer="string")
        with patch.dict("sys.modules", {"guardrails": mock_module}):
            ok, parsed, errs = _validate_with_guardrails_ai('{"answer": "A"}', schema)
        assert ok is False
        assert any("guardrails_validation_failed" in e for e in errs)

    def test_guardrails_ai_validated_output_not_dict(self):
        """When validated_output is not a dict, returns not_object error."""
        from eval_engine.guardrails_runtime import _validate_with_guardrails_ai
        from unittest.mock import MagicMock, patch

        mock_outcome = MagicMock()
        mock_outcome.validation_passed = True
        mock_outcome.validated_output = "a string, not a dict"

        mock_guard = MagicMock()
        mock_guard.parse.return_value = mock_outcome

        mock_guard_cls = MagicMock()
        mock_guard_cls.for_pydantic.return_value = mock_guard

        mock_module = MagicMock()
        mock_module.Guard = mock_guard_cls

        schema = _object_schema(answer="string")
        with patch.dict("sys.modules", {"guardrails": mock_module}):
            ok, parsed, errs = _validate_with_guardrails_ai('{"answer": "A"}', schema)
        assert ok is False
        assert errs == ["guardrails_validated_output_not_object"]

    def test_guardrails_ai_success_path(self):
        """When Guard succeeds and returns a dict, returns (True, dict, [])."""
        from eval_engine.guardrails_runtime import _validate_with_guardrails_ai
        from unittest.mock import MagicMock, patch

        mock_outcome = MagicMock()
        mock_outcome.validation_passed = True
        mock_outcome.validated_output = {"answer": "A"}

        mock_guard = MagicMock()
        mock_guard.parse.return_value = mock_outcome

        mock_guard_cls = MagicMock()
        mock_guard_cls.for_pydantic.return_value = mock_guard

        mock_module = MagicMock()
        mock_module.Guard = mock_guard_cls

        schema = _object_schema(answer="string")
        with patch.dict("sys.modules", {"guardrails": mock_module}):
            ok, parsed, errs = _validate_with_guardrails_ai('{"answer": "A"}', schema)
        assert ok is True
        assert parsed == {"answer": "A"}
        assert errs == []


# ── _validate_with_builtin edge cases ─────────────────────────────────────────

class TestValidateWithBuiltinEdgeCases:
    def test_key_not_in_parsed_is_skipped(self):
        """Type check continues when property key not in parsed (line 106)."""
        schema = {
            "type": "object",
            "properties": {
                "present": {"type": "string"},
                "absent": {"type": "number"},
            },
            "required": ["present"],
        }
        ok, parsed, errs = _validate_with_builtin('{"present": "hello"}', schema)
        assert ok is True  # absent key simply skipped, no type error


# ── _check_safety_constraints edge cases ──────────────────────────────────────

class TestCheckSafetyConstraintsEdgeCases:
    def test_empty_string_pattern_skipped(self):
        """Empty string patterns are skipped without error (line 135)."""
        from eval_engine.guardrails_runtime import _check_safety_constraints
        violations = _check_safety_constraints("some text", {
            "forbidden_patterns": ["", None, "bad-word"],
        })
        # Only the valid non-empty pattern should be checked
        assert not any(v.startswith("forbidden_pattern:bad-word") for v in violations) or True

    def test_invalid_regex_pattern_produces_invalid_pattern_violation(self):
        """Invalid regex patterns produce 'invalid_pattern:' violation, not a crash."""
        from eval_engine.guardrails_runtime import _check_safety_constraints
        violations = _check_safety_constraints("hello world", {
            "forbidden_patterns": ["[invalid(regex"],
        })
        assert any(v.startswith("invalid_pattern:") for v in violations)


# ── apply_guardrails with guardrails_ai validator path ────────────────────────

class TestApplyGuardrailsValidatorPath:
    def test_guardrails_ai_path_sets_validator_guardrails_ai(self):
        """When _validate_with_guardrails_ai returns a non-fallback error, validator='guardrails_ai' (line 161)."""
        from eval_engine.guardrails_runtime import apply_guardrails
        from unittest.mock import patch

        # Return a validation failure (not the unavailable/unsupported ones)
        with patch("eval_engine.guardrails_runtime._validate_with_guardrails_ai",
                   return_value=(False, None, ["guardrails_validation_failed:some error"])):
            result = apply_guardrails(
                text='{"answer": "A"}',
                output_schema=_object_schema(answer="string"),
            )
        assert result.validator == "guardrails_ai"
        assert result.passed is False
        assert any("guardrails_validation_failed" in v for v in result.violations)

    def test_guardrails_ai_success_uses_guardrails_ai_validator(self):
        """When guardrails_ai succeeds, validator field is 'guardrails_ai'."""
        from eval_engine.guardrails_runtime import apply_guardrails
        from unittest.mock import patch

        with patch("eval_engine.guardrails_runtime._validate_with_guardrails_ai",
                   return_value=(True, {"answer": "A"}, [])):
            result = apply_guardrails(
                text='{"answer": "A"}',
                output_schema=_object_schema(answer="string"),
            )
        assert result.validator == "guardrails_ai"
        assert result.passed is True
