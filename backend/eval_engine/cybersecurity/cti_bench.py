"""
CTIBench Runner — Cyber Threat Intelligence knowledge benchmark.

CTIBench assesses LLM capabilities across five cyber-threat-intelligence
tasks: MCQ (CTI-MCQ), analyst-style free-text (CTI-Analyst), MITRE ATT&CK
mapping (CTI-Mitre), root-cause mapping (CTI-RCM), and vulnerability
severity prediction (CTI-VSP).

References:
  Alam et al., "CTIBench: A Benchmark for Evaluating LLMs in Cyber Threat
  Intelligence", 2024.
  https://arxiv.org/abs/2406.07599

Dataset item format:
  {
    "id":               str,      # e.g. "mcq/apt_groups_001"
    "prompt":           str,      # question / scenario text
    "expected":         str,      # correct answer (letter or short text)
    "choices":          dict,     # for MCQ task_types — {"A": ..., "B": ...}
    "task_type":        str,      # cti_mcq | cti_analyst | cti_mitre |
                                  # cti_rcm | cti_vsp
    "category":         str,      # apt | malware | vulnerability | ioc |
                                  # mitre_attack | cve
    "difficulty":       str,      # easy | medium | hard | expert
    "required_keywords":[str],    # for analyst / MITRE tasks
    "tags":             [str],
    "explanation":      str
  }

Scoring:
  - cti_mcq, cti_vsp           → multiple-choice scoring        (0 or 1)
  - cti_analyst, cti_mitre,
    cti_rcm                    → keyword-match partial credit    (0.0–1.0)

Metrics:
  accuracy          — overall mean score
  by_task_type      — per-task-type accuracy
  by_category       — per-domain accuracy
  by_difficulty     — per-difficulty accuracy
"""
from eval_engine.base import BaseBenchmarkRunner, ItemResult
from eval_engine.cybersecurity.cyber_task import (
    score_multiple_choice,
    score_keyword_match,
)

_MCQ_TASK_TYPES = {"cti_mcq", "cti_vsp"}


class CTIBenchRunner(BaseBenchmarkRunner):
    """
    Evaluates LLM cyber-threat-intelligence capabilities across five
    CTIBench task types.
    """

    async def build_prompt(self, item: dict, few_shot_examples: list[dict]) -> str:
        question = item.get("prompt") or item.get("question") or str(item)
        task_type = item.get("task_type", "cti_mcq")
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

        task_instructions = {
            "cti_mcq": (
                "You are a cyber-threat-intelligence analyst. "
                "Select the single best answer (respond with only the letter)."
            ),
            "cti_analyst": (
                "You are a senior CTI analyst. "
                "Provide a concise professional analysis identifying threat actors, "
                "TTPs, and relevant IOCs."
            ),
            "cti_mitre": (
                "You are a MITRE ATT&CK expert. "
                "Map the described behaviour to the correct ATT&CK technique(s) "
                "and provide their IDs and names."
            ),
            "cti_rcm": (
                "You are a vulnerability analyst. "
                "Identify the root cause and affected component for the described issue."
            ),
            "cti_vsp": (
                "You are a CVSS scoring expert. "
                "Predict the CVSS severity (Critical/High/Medium/Low) and respond "
                "with only the severity label."
            ),
        }.get(task_type, "Answer the following cyber-threat-intelligence question.")

        prompt = f"{few_shot_block}{task_instructions}\n\nQuestion: {question}\n"
        if choices_text:
            prompt += f"\n{choices_text}\n"
        prompt += "\nAnswer:"
        return prompt

    def score_item(self, response: str, item: dict) -> float:
        task_type = item.get("task_type", "cti_mcq")
        if task_type in _MCQ_TASK_TYPES:
            return score_multiple_choice(response, item)
        return score_keyword_match(response, item)

    def compute_summary_metrics(self, results: list[ItemResult]) -> dict:
        if not results:
            return {"accuracy": 0.0}

        total = len(results)
        mean_score = round(sum(r.score for r in results) / total, 4)

        # Per-task-type breakdown
        by_task_type: dict[str, dict] = {}
        for r in results:
            tt = r.metadata.get("task_type", "unknown")
            if tt not in by_task_type:
                by_task_type[tt] = {"score_sum": 0.0, "total": 0}
            by_task_type[tt]["total"] += 1
            by_task_type[tt]["score_sum"] += r.score

        task_type_metrics = {
            tt: round(v["score_sum"] / v["total"], 4)
            for tt, v in by_task_type.items()
        }

        # Per-category breakdown
        by_category: dict[str, dict] = {}
        for r in results:
            cat = r.metadata.get("category", "unknown")
            if cat not in by_category:
                by_category[cat] = {"score_sum": 0.0, "total": 0}
            by_category[cat]["total"] += 1
            by_category[cat]["score_sum"] += r.score

        category_metrics = {
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

        difficulty_metrics = {
            diff: round(v["score_sum"] / v["total"], 4)
            for diff, v in by_difficulty.items()
        }

        return {
            "accuracy": mean_score,
            "accuracy_%": round(mean_score * 100, 2),
            "num_total": total,
            "by_task_type": task_type_metrics,
            "by_category": category_metrics,
            "by_difficulty": difficulty_metrics,
        }
