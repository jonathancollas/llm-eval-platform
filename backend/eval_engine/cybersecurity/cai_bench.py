"""
CAIBench Runner — Comprehensive AI Security benchmark.

CAIBench (Comprehensive AI security benchmarK) evaluates LLM competency on
adversarial-machine-learning and AI-system security topics including model
inversion, membership inference, data poisoning, model theft, differential
privacy, and prompt injection.

References:
  CAIBench — Comprehensive AI security benchmarK (2024).

Dataset item format:
  {
    "id":               str,      # e.g. "adversarial_ml/fgsm_001"
    "prompt":           str,      # question or scenario
    "expected":         str,      # correct answer (letter or keyword)
    "choices":          dict,     # MCQ choices (optional)
    "domain":           str,      # adversarial_ml | data_poisoning |
                                  # model_theft | privacy |
                                  # prompt_injection | ai_governance
    "item_type":        str,      # mcq | scenario
    "difficulty":       str,      # easy | medium | hard | expert
    "required_keywords":[str],    # for scenario items
    "tags":             [str],
    "explanation":      str
  }

Scoring:
  - mcq      → multiple-choice (0 or 1)
  - scenario  → keyword-match partial credit (0.0–1.0)

Metrics:
  overall_score  — mean score
  by_domain      — per-domain mean scores
  by_item_type   — breakdown by task type
  by_difficulty  — per-difficulty mean scores
"""
from eval_engine.base import BaseBenchmarkRunner, ItemResult
from eval_engine.cybersecurity.cyber_task import (
    score_multiple_choice,
    score_keyword_match,
)


class CAIBenchRunner(BaseBenchmarkRunner):
    """
    Evaluates LLM AI-security knowledge across adversarial ML, privacy,
    and AI-governance topics.
    """

    async def build_prompt(self, item: dict, few_shot_examples: list[dict]) -> str:
        question = item.get("prompt") or item.get("question") or str(item)
        item_type = item.get("item_type", "mcq")
        choices = item.get("choices", {})

        choices_text = ""
        if isinstance(choices, dict) and choices:
            choices_text = "\n".join(f"{k}. {v}" for k, v in choices.items())
        elif isinstance(choices, list) and choices:
            labels = "ABCDEFGHIJ"
            choices_text = "\n".join(f"{labels[i]}. {c}" for i, c in enumerate(choices))

        few_shot_block = ""
        if few_shot_examples:
            parts = []
            for ex in few_shot_examples:
                ex_q = ex.get("prompt", ex.get("question", ""))
                ex_ans = ex.get("expected", ex.get("answer", ""))
                parts.append(f"Question: {ex_q}\nAnswer: {ex_ans}")
            few_shot_block = "\n\n".join(parts) + "\n\n"

        if item_type == "mcq":
            instruction = (
                "You are an AI security expert. "
                "Select the single best answer (respond with only the letter)."
            )
        else:
            instruction = (
                "You are an AI security expert. "
                "Analyse the following scenario and provide a precise response "
                "covering the threat, impact, and mitigations."
            )

        prompt = f"{few_shot_block}{instruction}\n\nQuestion: {question}\n"
        if choices_text:
            prompt += f"\n{choices_text}\n"
        prompt += "\nAnswer:"
        return prompt

    def score_item(self, response: str, item: dict) -> float:
        if item.get("item_type", "mcq") == "mcq":
            return score_multiple_choice(response, item)
        return score_keyword_match(response, item)

    def compute_summary_metrics(self, results: list[ItemResult]) -> dict:
        if not results:
            return {"overall_score": 0.0}

        total = len(results)
        mean_score = round(sum(r.score for r in results) / total, 4)

        by_domain: dict[str, dict] = {}
        for r in results:
            dom = r.metadata.get("domain", "unknown")
            if dom not in by_domain:
                by_domain[dom] = {"score_sum": 0.0, "total": 0}
            by_domain[dom]["total"] += 1
            by_domain[dom]["score_sum"] += r.score

        domain_metrics = {
            dom: round(v["score_sum"] / v["total"], 4)
            for dom, v in by_domain.items()
        }

        by_item_type: dict[str, dict] = {}
        for r in results:
            it = r.metadata.get("item_type", "unknown")
            if it not in by_item_type:
                by_item_type[it] = {"score_sum": 0.0, "total": 0}
            by_item_type[it]["total"] += 1
            by_item_type[it]["score_sum"] += r.score

        item_type_metrics = {
            it: round(v["score_sum"] / v["total"], 4)
            for it, v in by_item_type.items()
        }

        by_difficulty: dict[str, dict] = {}
        for r in results:
            diff = r.metadata.get("difficulty", "unknown")
            if diff not in by_difficulty:
                by_difficulty[diff] = {"score_sum": 0.0, "total": 0}
            by_difficulty[diff]["total"] += 1
            by_difficulty[diff]["score_sum"] += r.score

        difficulty_metrics = {
            diff: round(v["score_sum"] / v["total"], 4)
            for diff, v in by_difficulty.items()
        }

        return {
            "overall_score": mean_score,
            "overall_score_%": round(mean_score * 100, 2),
            "num_total": total,
            "by_domain": domain_metrics,
            "by_item_type": item_type_metrics,
            "by_difficulty": difficulty_metrics,
        }
