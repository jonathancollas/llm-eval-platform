"""
Normalize imported / uploaded eval items so runners can score them.

HuggingFace MC rows (cais/mmlu, ARC, …) store the gold label as an integer
index. Local runners expect a letter. Open-ended HF rows use question+answer
while CustomRunner looks for prompt+expected. `0` must not be treated as missing.
"""
from __future__ import annotations

import json
from typing import Any, Optional

_MC_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_Q_FIELDS = ("question", "input", "prompt", "text", "query", "instruction")
_A_FIELDS = ("answer", "output", "target", "expected", "response", "label")


def stringify_gold(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _as_choice_index(raw: Any) -> Optional[int]:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


def _index_to_letter(index: int, n_choices: int) -> Optional[str]:
    if n_choices <= 0:
        return None
    if 0 <= index < n_choices and index < len(_MC_LETTERS):
        return _MC_LETTERS[index]
    return None


def canonical_mc_answer(item: dict) -> str:
    """Return the gold MC letter, mapping integer indices when choices exist."""
    raw = item.get("answer", "")
    choices = item.get("choices")
    n_choices = len(choices) if isinstance(choices, list) else 0
    index = _as_choice_index(raw)
    if index is not None:
        letter = _index_to_letter(index, n_choices)
        if letter:
            return letter
    if raw is None:
        return ""
    return stringify_gold(raw).strip().upper()


def item_expected(item: dict) -> Optional[str]:
    """Gold label for persistence. Treats answer=0 as present, not missing."""
    if "answer" in item and item["answer"] is not None:
        raw = item["answer"]
    elif "expected" in item and item["expected"] is not None:
        raw = item["expected"]
    else:
        return None
    text = stringify_gold(raw)
    return text if text else None


def normalize_imported_item(item: dict) -> dict:
    """Rewrite a HuggingFace (or similar) row into the local runner schema."""
    normalized = dict(item)

    if "question" not in normalized:
        for field in _Q_FIELDS:
            if field in normalized:
                normalized["question"] = normalized[field]
                break
    if "prompt" not in normalized and "question" in normalized:
        normalized["prompt"] = normalized["question"]

    raw_answer = None
    if "answer" in normalized and normalized["answer"] is not None:
        raw_answer = normalized["answer"]
    else:
        for field in _A_FIELDS:
            if field in normalized and normalized[field] is not None:
                raw_answer = normalized[field]
                break

    if raw_answer is not None:
        gold = canonical_mc_answer({**normalized, "answer": raw_answer})
        if not gold:
            gold = stringify_gold(raw_answer)
        normalized["answer"] = gold
        if item.get("expected") is None:
            normalized["expected"] = gold
        else:
            normalized["expected"] = stringify_gold(item["expected"])

    return normalized
