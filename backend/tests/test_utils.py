import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.utils import clamp_unit_interval, safe_extract_text, safe_json_load


def test_clamp_unit_interval_handles_bounds_and_invalid_values():
    assert clamp_unit_interval(-1) == 0.0
    assert clamp_unit_interval(2) == 1.0
    assert clamp_unit_interval("0.75") == 0.75
    assert clamp_unit_interval("not-a-number") == 0.0
    assert clamp_unit_interval(None) == 0.0


def test_safe_json_load_returns_parsed_value_or_fallback():
    assert safe_json_load('{"a": 1}') == {"a": 1}
    assert safe_json_load("", {"fallback": True}) == {"fallback": True}
    assert safe_json_load("not-json", {"fallback": True}) == {"fallback": True}
    assert safe_json_load(None) == {}


def test_safe_json_load_preserves_already_parsed_collections():
    raw_dict = {"k": "v"}
    raw_list = [1, 2, 3]
    assert safe_json_load(raw_dict) is raw_dict
    assert safe_json_load(raw_list) is raw_list


def test_safe_extract_text_handles_missing_content():
    assert safe_extract_text(None) == ""

    class _Message:
        content = []

    assert safe_extract_text(_Message()) == ""


def test_safe_extract_text_extracts_and_strips_first_block_text():
    class _Block:
        text = "  hello world  "

    class _Message:
        content = [_Block()]

    assert safe_extract_text(_Message()) == "hello world"
