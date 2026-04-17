"""
CyberSec-Bench Runner — cybersecurity knowledge and reasoning benchmark.

CyberSec-Bench evaluates LLM knowledge across cybersecurity domains via
multiple-choice questions covering attack techniques, defensive concepts,
vulnerability classes, compliance, and threat intelligence.

Dataset item format:
  {
    "id":          str,          # unique question identifier
    "prompt":      str,          # question text
    "choices":     {             # answer options (dict or list)
                     "A": str,
                     "B": str,
                     "C": str,
                     "D": str
                   },
    "expected":    str,          # correct letter: "A" | "B" | "C" | "D"
    "answer":      str,          # alias for expected
    "category":    str,          # domain category
    "difficulty":  str,          # easy | medium | hard | expert
    "tags":        [str],        # skill tags
    "explanation": str           # correct-answer rationale
  }

Scoring:
  - Correct letter selected  → 1.0
  - Any other response       → 0.0

Metrics:
  accuracy          — overall fraction correct
  by_category       — per-domain accuracy
  by_difficulty     — per-difficulty accuracy
"""
from eval_engine.base import BaseBenchmarkRunner, ItemResult
from eval_engine.cybersecurity.cyber_task import score_multiple_choice


class CyberSecBenchRunner(BaseBenchmarkRunner):
    """
    Evaluates LLM cybersecurity knowledge via multiple-choice questions
    modelled on the CyberSec-Bench benchmark family.
    """

    async def build_prompt(self, item: dict, few_shot_examples: list[dict]) -> str:
        question = item.get("prompt") or item.get("question") or str(item)
        choices = item.get("choices", {})

        choices_text = ""
        if isinstance(choices, dict):
            choices_text = "\n".join(f"{k}. {v}" for k, v in choices.items())
        elif isinstance(choices, list):
            labels = "ABCDEFGHIJ"
            choices_text = "\n".join(
                f"{labels[i]}. {c}" for i, c in enumerate(choices)
            )

        few_shot_block = ""
        if few_shot_examples:
            parts = []
            for ex in few_shot_examples:
                ex_q = ex.get("prompt", ex.get("question", ""))
                ex_ans = ex.get("expected", ex.get("answer", ""))
                parts.append(f"Question: {ex_q}\nAnswer: {ex_ans}")
            few_shot_block = "\n\n".join(parts) + "\n\n"

        prompt = (
            f"{few_shot_block}"
            f"Answer the following cybersecurity question by selecting the single best option "
            f"(respond with only the letter).\n\n"
            f"Question: {question}\n"
        )
        if choices_text:
            prompt += f"\n{choices_text}\n"
        prompt += "\nAnswer:"
        return prompt

    def score_item(self, response: str, item: dict) -> float:
        return score_multiple_choice(response, item)

    def compute_summary_metrics(self, results: list[ItemResult]) -> dict:
        if not results:
            return {"accuracy": 0.0}

        total = len(results)
        correct = sum(r.score for r in results)
        accuracy = round(correct / total, 4)

        # Per-category breakdown
        by_category: dict[str, dict] = {}
        for r in results:
            cat = r.metadata.get("category", "unknown")
            if cat not in by_category:
                by_category[cat] = {"correct": 0, "total": 0}
            by_category[cat]["total"] += 1
            by_category[cat]["correct"] += int(r.score == 1.0)

        category_accuracy = {
            cat: round(v["correct"] / v["total"], 4)
            for cat, v in by_category.items()
        }

        # Per-difficulty breakdown
        by_difficulty: dict[str, dict] = {}
        for r in results:
            diff = r.metadata.get("difficulty", "unknown")
            if diff not in by_difficulty:
                by_difficulty[diff] = {"correct": 0, "total": 0}
            by_difficulty[diff]["total"] += 1
            by_difficulty[diff]["correct"] += int(r.score == 1.0)

        difficulty_accuracy = {
            diff: round(v["correct"] / v["total"], 4)
            for diff, v in by_difficulty.items()
        }

        return {
            "accuracy": accuracy,
            "accuracy_%": round(accuracy * 100, 2),
            "num_correct": int(correct),
            "num_total": total,
            "by_category": category_accuracy,
            "by_difficulty": difficulty_accuracy,
        }
