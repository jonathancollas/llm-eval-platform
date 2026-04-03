"""
MMLU (Massive Multitask Language Understanding) runner.
5-shot multiple choice, accuracy metric.
Standard format used by lm-evaluation-harness.
"""
import re
from eval_engine.base import BaseBenchmarkRunner, ItemResult


SYSTEM_PROMPT = (
    "You are a knowledgeable assistant answering multiple-choice questions. "
    "Always respond with just the letter of the correct answer: A, B, C, or D."
)

CHOICES = ["A", "B", "C", "D"]


def _format_question(item: dict, include_answer: bool = False) -> str:
    lines = [f"Question: {item['question']}"]
    for letter, choice in zip(CHOICES, item.get("choices", [])):
        lines.append(f"({letter}) {choice}")
    if include_answer:
        lines.append(f"Answer: {item['answer']}")
    else:
        lines.append("Answer:")
    return "\n".join(lines)


class MMLURunner(BaseBenchmarkRunner):

    async def build_prompt(self, item: dict, few_shot_examples: list[dict]) -> str:
        parts = ["The following are multiple choice questions. Answer with the letter only.\n"]
        for ex in few_shot_examples:
            parts.append(_format_question(ex, include_answer=True))
            parts.append("")
        parts.append(_format_question(item, include_answer=False))
        return "\n".join(parts)

    def score_item(self, response: str, item: dict) -> float:
        """Extract first capital letter A-D from response and compare to answer."""
        response = response.strip().upper()
        # Extract first letter A-D
        match = re.search(r"\b([A-D])\b", response)
        if match:
            predicted = match.group(1)
        elif response and response[0] in CHOICES:
            predicted = response[0]
        else:
            return 0.0
        return 1.0 if predicted == item.get("answer", "").upper() else 0.0

    def compute_summary_metrics(self, results: list[ItemResult]) -> dict:
        if not results:
            return {"accuracy": 0.0}

        accuracy = sum(r.score for r in results) / len(results)

        # Per-category accuracy
        by_category: dict[str, list[float]] = {}
        for r in results:
            cat = r.metadata.get("category", "unknown")
            by_category.setdefault(cat, []).append(r.score)

        category_scores = {
            cat: sum(scores) / len(scores)
            for cat, scores in by_category.items()
        }

        return {
            "accuracy": round(accuracy, 4),
            "accuracy_%": round(accuracy * 100, 2),
            "by_category": category_scores,
            "num_correct": int(sum(r.score for r in results)),
            "num_total": len(results),
        }
