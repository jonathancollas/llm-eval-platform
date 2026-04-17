"""
DefenseBench Runner — Blue Team / SOC defensive operations benchmark.

DefenseBench evaluates LLM capability on defensive cybersecurity tasks
including log analysis, incident triage, malware identification, rule
writing, threat hunting, and remediation planning.

References:
  DefenseBench (SOC task suite)

Dataset item format:
  {
    "id":                str,         # unique task identifier
    "prompt":            str,         # scenario description and task
    "expected":          str,         # expected answer or label
    "category":          str,         # log_analysis | triage | malware | rule_writing |
                                      # threat_hunting | remediation | threat_intel
    "difficulty":        str,         # easy | medium | hard | expert
    "environment":       str,         # soc | sandbox | qa
    "required_keywords": [str],       # keywords that must appear in a correct response
    "subtasks":          [str],       # optional ordered subtask descriptions
    "tags":              [str],       # skill tags
    "explanation":       str          # rationale / reference answer
  }

Scoring:
  - Keyword-based partial credit if ``required_keywords`` is present   → 0.0–1.0
  - Subtask completion if ``subtasks`` is present                      → 0.0–1.0
  - Falls back to exact / embedded match against ``expected``          → 0.0 or 1.0

Metrics:
  defense_score     — overall mean score
  by_category       — per-SOC-task-type mean scores
  by_difficulty     — per-difficulty mean scores
  alerts            — actionable warnings on capability gaps
"""
from eval_engine.base import BaseBenchmarkRunner, ItemResult
from eval_engine.cybersecurity.cyber_task import (
    score_keyword_match,
    score_subtask_completion,
    score_multiple_choice,
)


_SOC_CATEGORIES = {
    "log_analysis",
    "triage",
    "malware",
    "rule_writing",
    "threat_hunting",
    "remediation",
    "threat_intel",
}


class DefenseBenchRunner(BaseBenchmarkRunner):
    """
    Evaluates LLM defensive cybersecurity capability on SOC-style tasks
    modelled on the DefenseBench benchmark suite.
    """

    async def build_prompt(self, item: dict, few_shot_examples: list[dict]) -> str:
        scenario = item.get("prompt") or item.get("question") or str(item)

        few_shot_block = ""
        if few_shot_examples:
            parts = []
            for ex in few_shot_examples:
                ex_q = ex.get("prompt", ex.get("question", ""))
                ex_ans = ex.get("expected", ex.get("answer", ""))
                parts.append(f"Scenario: {ex_q}\nResponse: {ex_ans}")
            few_shot_block = "\n\n".join(parts) + "\n\n"

        return (
            f"{few_shot_block}"
            f"You are an expert SOC analyst. Analyse the following scenario and provide a "
            f"detailed defensive response.\n\n"
            f"{scenario}"
        )

    def score_item(self, response: str, item: dict) -> float:
        # Priority: subtasks > keywords > multiple-choice / exact match
        if item.get("subtasks"):
            return score_subtask_completion(response, item)
        if item.get("required_keywords"):
            return score_keyword_match(response, item)
        # For triage / classification tasks presented as MCQ
        if item.get("choices"):
            return score_multiple_choice(response, item)
        return score_keyword_match(response, item)

    def compute_summary_metrics(self, results: list[ItemResult]) -> dict:
        if not results:
            return {"defense_score": 0.0}

        total = len(results)
        mean_score = round(sum(r.score for r in results) / total, 4)

        # Per-category breakdown
        by_category: dict[str, dict] = {}
        for r in results:
            cat = r.metadata.get("category", "unknown")
            if cat not in by_category:
                by_category[cat] = {"score_sum": 0.0, "total": 0}
            by_category[cat]["total"] += 1
            by_category[cat]["score_sum"] += r.score

        category_scores = {
            cat: round(v["score_sum"] / v["total"], 4)
            for cat, v in by_category.items()
        }

        # Per-difficulty breakdown
        by_difficulty: dict[str, dict] = {}
        for r in results:
            diff = r.metadata.get("difficulty", "unknown")
            if diff not in by_difficulty:
                by_difficulty[diff] = {"score_sum": 0.0, "total": 0}
            by_difficulty[diff]["total"] += 1
            by_difficulty[diff]["score_sum"] += r.score

        difficulty_scores = {
            diff: round(v["score_sum"] / v["total"], 4)
            for diff, v in by_difficulty.items()
        }

        # Identify weak categories (below 40%)
        alerts = []
        weak = [cat for cat, sc in category_scores.items() if sc < 0.4]
        if weak:
            alerts.append(
                f"LOW defensive capability in: {', '.join(sorted(weak))}. "
                "Model struggles with these SOC task types."
            )
        if mean_score < 0.3:
            alerts.append(
                f"VERY LOW overall defense score ({mean_score:.0%}): "
                "model is not suitable for SOC-assistance applications."
            )

        return {
            "defense_score": mean_score,
            "defense_score_%": round(mean_score * 100, 2),
            "num_total": total,
            "by_category": category_scores,
            "by_difficulty": difficulty_scores,
            "alerts": alerts,
        }
