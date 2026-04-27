"""
Generic runner for custom benchmarks imported as JSON.

Supported item formats:
  1. Multiple choice:  { question, choices[A-D], answer, category? }
  2. Open-ended:       { prompt, expected_keywords: [], category? }
  3. Classification:   { prompt, expected: "LABEL", category? }
"""
import re
from eval_engine.base import BaseBenchmarkRunner


class CustomRunner(BaseBenchmarkRunner):

    def _detect_format(self, item: dict) -> str:
        if "choices" in item and "answer" in item:
            return "multiple_choice"
        if "expected_keywords" in item:
            return "keyword_match"
        if "expected" in item and "prompt" in item:
            return "classification"
        return "unknown"

    async def build_prompt(self, item: dict, few_shot_examples: list[dict]) -> str:
        fmt = self._detect_format(item)
        if fmt == "multiple_choice":
            lines = [f"Question: {item.get('question', item.get('prompt', ''))}"]
            for letter, choice in zip(["A", "B", "C", "D"], item.get("choices", [])):
                lines.append(f"({letter}) {choice}")
            lines.append("Answer:")
            return "\n".join(lines)
        # Default: use prompt/question as-is
        return item.get("prompt", item.get("question", ""))

    def score_item(self, response: str, item: dict) -> float:
        fmt = self._detect_format(item)
        response = response.strip()

        if fmt == "multiple_choice":
            match = re.search(r"\b([A-D])\b", response.upper())
            if match:
                return 1.0 if match.group(1) == item.get("answer", "").upper() else 0.0
            return 0.0

        if fmt == "keyword_match":
            keywords = item.get("expected_keywords", [])
            if not keywords:
                return 0.0
            hits = sum(1 for kw in keywords if kw.lower() in response.lower())
            return hits / len(keywords)

        if fmt == "classification":
            expected = str(item.get("expected", "")).strip().upper()
            return 1.0 if expected in response.upper() else 0.0

        return 0.0  # unknown format
