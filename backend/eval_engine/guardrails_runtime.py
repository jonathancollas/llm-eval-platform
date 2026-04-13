"""
Runtime Guardrails integration for structured validation + safety constraints.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import create_model

# Guardrails AI emits OpenTelemetry traces by default; disable in sandbox/runtime.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")


@dataclass
class GuardrailsValidationResult:
    passed: bool
    schema_valid: bool
    safety_valid: bool
    violations: list[str] = field(default_factory=list)
    parsed_output: Optional[dict] = None
    validator: str = "builtin"


_JSON_TYPE_MAP: dict[str, type] = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def _build_model_from_schema(schema: dict) -> Optional[type]:
    if schema.get("type") != "object":
        return None
    properties = schema.get("properties") or {}
    if not isinstance(properties, dict) or not properties:
        return None

    required = set(schema.get("required") or [])
    fields: dict[str, tuple[type, Any]] = {}

    for field_name, field_schema in properties.items():
        if not isinstance(field_schema, dict):
            continue
        py_type = _JSON_TYPE_MAP.get(field_schema.get("type"), Any)
        if field_name in required:
            fields[field_name] = (py_type, ...)
        else:
            fields[field_name] = (Optional[py_type], None)

    if not fields:
        return None
    return create_model("GuardrailsStructuredOutput", **fields)


def _validate_with_guardrails_ai(text: str, schema: dict) -> tuple[bool, Optional[dict], list[str]]:
    try:
        from guardrails import Guard
    except Exception:
        return False, None, ["guardrails_ai_unavailable"]

    model = _build_model_from_schema(schema)
    if model is None:
        return False, None, ["unsupported_schema_for_guardrails_ai"]

    try:
        guard = Guard.for_pydantic(model)
        outcome = guard.parse(text)
    except Exception as e:
        return False, None, [f"guardrails_parse_error:{str(e)[:120]}"]

    if not getattr(outcome, "validation_passed", False):
        err = getattr(outcome, "error", None)
        return False, None, [f"guardrails_validation_failed:{str(err)[:120] if err else 'unknown'}"]

    validated = getattr(outcome, "validated_output", None)
    if not isinstance(validated, dict):
        return False, None, ["guardrails_validated_output_not_object"]
    return True, validated, []


def _validate_with_builtin(text: str, schema: dict) -> tuple[bool, Optional[dict], list[str]]:
    try:
        parsed = json.loads(text)
    except Exception as e:
        return False, None, [f"invalid_json:{str(e)[:120]}"]

    if not isinstance(parsed, dict):
        return False, None, ["json_output_not_object"]

    required = schema.get("required") or []
    missing = [k for k in required if k not in parsed]
    if missing:
        return False, parsed, [f"missing_required:{','.join(sorted(missing))}"]

    properties = schema.get("properties") or {}
    type_errors: list[str] = []
    for key, spec in properties.items():
        if key not in parsed or not isinstance(spec, dict):
            continue
        expected = spec.get("type")
        py_type = _JSON_TYPE_MAP.get(expected)
        if py_type and not isinstance(parsed[key], py_type):
            type_errors.append(f"type_mismatch:{key}:{expected}")

    if type_errors:
        return False, parsed, type_errors
    return True, parsed, []


def _check_safety_constraints(text: str, constraints: dict) -> list[str]:
    violations: list[str] = []

    max_length = constraints.get("max_length")
    if isinstance(max_length, int) and max_length >= 0 and len(text) > max_length:
        violations.append(f"max_length_exceeded:{len(text)}>{max_length}")

    forbidden_phrases = constraints.get("forbidden_phrases") or []
    if isinstance(forbidden_phrases, list):
        lowered = text.lower()
        for phrase in forbidden_phrases:
            if isinstance(phrase, str) and phrase and phrase.lower() in lowered:
                violations.append(f"forbidden_phrase:{phrase}")

    forbidden_patterns = constraints.get("forbidden_patterns") or []
    if isinstance(forbidden_patterns, list):
        for pattern in forbidden_patterns:
            if not isinstance(pattern, str) or not pattern:
                continue
            try:
                if re.search(pattern, text, flags=re.IGNORECASE):
                    violations.append(f"forbidden_pattern:{pattern}")
            except re.error:
                violations.append(f"invalid_pattern:{pattern}")

    return violations


def apply_guardrails(
    text: str,
    output_schema: Optional[dict] = None,
    safety_constraints: Optional[dict] = None,
) -> GuardrailsValidationResult:
    violations: list[str] = []
    parsed_output: Optional[dict] = None
    schema_valid = True
    validator = "builtin"

    if output_schema:
        ok, parsed, errs = _validate_with_guardrails_ai(text, output_schema)
        if not ok and errs and errs[0] in {"guardrails_ai_unavailable", "unsupported_schema_for_guardrails_ai"}:
            ok, parsed, errs = _validate_with_builtin(text, output_schema)
            validator = "builtin"
        else:
            validator = "guardrails_ai"

        schema_valid = ok
        parsed_output = parsed
        violations.extend(errs)

    safety_valid = True
    if safety_constraints:
        safety_violations = _check_safety_constraints(text, safety_constraints)
        if safety_violations:
            safety_valid = False
            violations.extend(safety_violations)

    return GuardrailsValidationResult(
        passed=schema_valid and safety_valid,
        schema_valid=schema_valid,
        safety_valid=safety_valid,
        violations=violations,
        parsed_output=parsed_output,
        validator=validator,
    )
