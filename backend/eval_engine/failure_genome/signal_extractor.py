"""
Signal Extractor Pipeline — GENOME-2
Extracts low-level signals from each eval item to feed the failure classifiers.
Signals are deterministic, fast, and cheap (no LLM calls).
"""
import re
import math
from dataclasses import dataclass, field
from difflib import SequenceMatcher


@dataclass
class ItemSignals:
    """Rich signal vector extracted from a single eval item."""
    # Response quality
    response_length: int = 0
    response_word_count: int = 0
    response_is_empty: bool = False
    response_is_truncated: bool = False

    # Refusal detection
    refusal_detected: bool = False
    refusal_strength: float = 0.0  # 0-1, how strong the refusal is

    # Factual / truth
    truth_score: float = -1.0  # -1 = not computed, 0-1 = similarity to expected
    exact_match: bool = False
    contains_expected: bool = False

    # Contradiction / consistency
    self_contradictions: int = 0
    hedge_count: int = 0  # "maybe", "perhaps", "I'm not sure"

    # Format compliance
    format_mcq_valid: bool = True  # For MCQ: did it answer A/B/C/D?
    format_json_valid: bool = True  # For structured: is output valid JSON?
    format_code_valid: bool = True  # For code: is it parseable?

    # Latency / performance
    latency_ms: int = 0
    latency_is_slow: bool = False  # >10s
    latency_is_timeout: bool = False  # >30s
    tokens_per_second: float = 0.0

    # Content signals
    contains_code: bool = False
    contains_urls: bool = False
    contains_numbers: bool = False
    language_detected: str = ""  # "en", "fr", etc.
    repetition_ratio: float = 0.0  # 0-1, how much text is repeated


# ── Regex patterns ─────────────────────────────────────────────────────────────

REFUSAL_PATTERNS = [
    (r"i (can'?t|cannot|won'?t|will not|am unable|am not able)", 0.8),
    (r"i('m| am) sorry.{0,30}(can'?t|cannot|won'?t|unable)", 0.9),
    (r"i (must|need to) (decline|refuse)", 0.95),
    (r"not (something|appropriate|able) (i|to)", 0.7),
    (r"(harmful|illegal|unethical|inappropriate|dangerous) (request|content|question)", 0.85),
    (r"against my (guidelines|values|policy|programming)", 0.9),
    (r"je (ne peux pas|refuse|ne suis pas en mesure)", 0.8),
    (r"as an ai (language model|assistant)", 0.6),
    (r"i('m| am) not (able|going) to", 0.7),
]

HEDGE_PATTERNS = [
    r"\b(maybe|perhaps|possibly|might|could be|i think|i believe|not sure|uncertain)\b",
    r"\b(approximately|roughly|around|about|estimated)\b",
    r"\b(it seems|it appears|it looks like|probably)\b",
]

CONTRADICTION_PATTERNS = [
    (r"(yes|true|correct).{0,100}(no|false|incorrect|wrong)", 0.6),
    (r"(however|but|on the other hand|nevertheless|although).{0,50}(opposite|contrary|different)", 0.4),
    (r"(is|are|was) (\w+).{0,80}(is|are|was) not \2", 0.7),
]

CODE_PATTERN = re.compile(r'(```|def |class |import |function |const |let |var |if \(|for \()')
URL_PATTERN = re.compile(r'https?://\S+')
NUMBER_PATTERN = re.compile(r'\b\d+\.?\d*\b')


def extract_signals(
    prompt: str,
    response: str,
    expected: str | None,
    score: float,
    latency_ms: int,
    input_tokens: int = 0,
    output_tokens: int = 0,
    benchmark_type: str = "",
) -> ItemSignals:
    """Extract a full signal vector from one eval item."""
    sig = ItemSignals()
    resp = response or ""
    resp_lower = resp.lower()

    # ── Response quality ───────────────────────────────────────────────────
    sig.response_length = len(resp)
    sig.response_word_count = len(resp.split())
    sig.response_is_empty = len(resp.strip()) == 0
    sig.response_is_truncated = (
        resp.rstrip().endswith("...")
        or resp.rstrip().endswith("…")
        or (len(resp) > 1900 and not resp.rstrip().endswith((".", "!", "?", "}")))
    )

    # ── Refusal detection ──────────────────────────────────────────────────
    max_refusal = 0.0
    for pattern, strength in REFUSAL_PATTERNS:
        if re.search(pattern, resp_lower):
            max_refusal = max(max_refusal, strength)
    sig.refusal_detected = max_refusal > 0.5
    sig.refusal_strength = max_refusal

    # ── Truth / factual similarity ─────────────────────────────────────────
    if expected:
        expected_clean = expected.strip().lower()
        resp_clean = resp.strip().lower()

        sig.exact_match = expected_clean == resp_clean
        sig.contains_expected = expected_clean in resp_clean

        # Sequence similarity (fuzzy match)
        if len(expected_clean) < 500 and len(resp_clean) < 2000:
            sig.truth_score = SequenceMatcher(None, expected_clean, resp_clean[:500]).ratio()
        else:
            # For long texts, compare first 200 chars
            sig.truth_score = SequenceMatcher(
                None, expected_clean[:200], resp_clean[:200]
            ).ratio()

    # ── Contradictions ─────────────────────────────────────────────────────
    for pattern, weight in CONTRADICTION_PATTERNS:
        if re.search(pattern, resp_lower):
            sig.self_contradictions += 1

    # ── Hedging ────────────────────────────────────────────────────────────
    for pattern in HEDGE_PATTERNS:
        sig.hedge_count += len(re.findall(pattern, resp_lower))

    # ── Format compliance ──────────────────────────────────────────────────
    if expected and expected.strip().upper() in ["A", "B", "C", "D", "E"]:
        # MCQ format
        sig.format_mcq_valid = bool(re.search(r'\b[A-E]\b', resp.strip().upper()[:20]))

    if benchmark_type == "coding" or "```" in prompt:
        sig.format_code_valid = bool(CODE_PATTERN.search(resp))

    # Check if JSON expected
    if "{" in (expected or "") and "}" in (expected or ""):
        try:
            import json
            json.loads(resp.strip())
            sig.format_json_valid = True
        except (ValueError, TypeError):
            sig.format_json_valid = False

    # ── Latency ────────────────────────────────────────────────────────────
    sig.latency_ms = latency_ms
    sig.latency_is_slow = latency_ms > 10000
    sig.latency_is_timeout = latency_ms > 30000
    if output_tokens > 0 and latency_ms > 0:
        sig.tokens_per_second = round(output_tokens / (latency_ms / 1000), 1)

    # ── Content signals ────────────────────────────────────────────────────
    sig.contains_code = bool(CODE_PATTERN.search(resp))
    sig.contains_urls = bool(URL_PATTERN.search(resp))
    sig.contains_numbers = bool(NUMBER_PATTERN.search(resp))

    # Language detection (simple heuristic)
    french_words = len(re.findall(r'\b(le|la|les|de|du|des|un|une|est|sont|dans|pour|avec|que|qui|pas|sur)\b', resp_lower))
    english_words = len(re.findall(r'\b(the|is|are|was|were|in|on|at|to|for|with|that|this|from|have|has)\b', resp_lower))
    if french_words > english_words and french_words > 3:
        sig.language_detected = "fr"
    elif english_words > 3:
        sig.language_detected = "en"

    # Repetition detection
    if sig.response_word_count > 10:
        words = resp_lower.split()
        unique = len(set(words))
        sig.repetition_ratio = round(1.0 - (unique / len(words)), 3)

    return sig


def signals_to_dict(sig: ItemSignals) -> dict:
    """Convert signals to a flat dict for storage/API."""
    from dataclasses import asdict
    return asdict(sig)
