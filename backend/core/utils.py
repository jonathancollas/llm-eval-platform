"""Shared utility functions."""
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def safe_json_load(value: Any, fallback: Any = None) -> Any:
    """Parse JSON safely — returns fallback on None, empty string, or malformed JSON."""
    if not value:
        return fallback if fallback is not None else {}
    if isinstance(value, (list, dict)):
        return value  # already parsed
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning(f"Failed to parse JSON: {repr(value)[:100]}")
        return fallback if fallback is not None else {}


def safe_extract_text(message) -> str:
    """Safely extract text from an Anthropic API message response.
    Handles None message, empty content, or missing text attribute.
    """
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if not content or not isinstance(content, list) or len(content) == 0:
        return ""
    block = content[0]
    text = getattr(block, "text", None)
    return text.strip() if text else ""
