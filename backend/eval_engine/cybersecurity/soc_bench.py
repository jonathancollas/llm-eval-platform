"""
SOC Bench Runner — Security Operations Centre automated response benchmark.

SOC Bench (inspired by Simbian's SOC Bench) evaluates how well an LLM can
assist tier-1/2 SOC analysts with alert triage, threat detection queries,
incident investigation, and automated response playbook generation.

References:
  Simbian SOC Bench (2024): https://simbian.ai/soc-bench

Dataset item format:
  {
    "id":                str,      # e.g. "triage/ransomware_alert_001"
    "prompt":            str,      # alert / scenario description
    "expected":          str,      # expected classification or action label
    "category":          str,      # alert_triage | threat_detection |
                                   # investigation | response | siem_query |
                                   # playbook
    "difficulty":        str,      # easy | medium | hard | expert
    "environment":       str,      # soc | sandbox
    "required_keywords": [str],    # key concepts that must appear
    "subtasks":          [str],    # optional ordered analysis steps
    "choices":           dict,     # optional MCQ choices (triage tasks)
    "severity":          str,      # low | medium | high | critical
    "tags":              [str],
    "explanation":       str
  }

Scoring:
  - subtasks present     → subtask-completion partial credit (0.0–1.0)
  - required_keywords    → keyword-match partial credit      (0.0–1.0)
  - choices present      → multiple-choice                   (0 or 1)
  - fallback             → keyword-match on expected

Metrics:
  soc_score       — overall mean score
  by_category     — per-SOC-task-type mean scores
  by_severity     — mean score broken down by alert severity
  by_difficulty   — per-difficulty mean scores
  alerts          — warnings on weak SOC capability areas
"""
from eval_engine.base import BaseBenchmarkRunner, ItemResult
from eval_engine.cybersecurity.cyber_task import (
    score_keyword_match,
    score_subtask_completion,
    score_multiple_choice,
)


class SOCBenchRunner(BaseBenchmarkRunner):
    """
    Evaluates LLM SOC-analyst capability on alert triage, threat detection,
    investigation, and incident-response playbook tasks.
    """

    async def build_prompt(self, item: dict, few_shot_examples: list[dict]) -> str:
        scenario = item.get("prompt") or item.get("question") or str(item)
        category = item.get("category", "alert_triage")
        severity = item.get("severity", "")

        few_shot_block = ""
        if few_shot_examples:
            parts = []
            for ex in few_shot_examples:
                ex_q = ex.get("prompt", ex.get("question", ""))
                ex_ans = ex.get("expected", ex.get("answer", ""))
                parts.append(f"Scenario: {ex_q}\nResponse: {ex_ans}")
            few_shot_block = "\n\n".join(parts) + "\n\n"

        role_context = {
            "alert_triage": (
                "You are a tier-1 SOC analyst. Classify the alert severity "
                "and determine whether it requires escalation."
            ),
            "threat_detection": (
                "You are a threat-detection engineer. "
                "Write a detection query or rule to catch the described behaviour."
            ),
            "investigation": (
                "You are a tier-2 SOC investigator. "
                "Analyse the provided evidence and identify the root cause, "
                "affected systems, and attacker TTPs."
            ),
            "response": (
                "You are an incident responder. "
                "Outline the containment, eradication, and recovery steps."
            ),
            "siem_query": (
                "You are a SIEM engineer. "
                "Write a query (e.g. Splunk SPL or Sigma rule) to detect "
                "the described malicious activity."
            ),
            "playbook": (
                "You are a SOC automation engineer. "
                "Generate a structured incident-response playbook for the given scenario."
            ),
        }.get(category, "You are an expert SOC analyst.")

        severity_line = f"\nAlert severity: {severity.upper()}" if severity else ""

        return (
            f"{few_shot_block}"
            f"{role_context}{severity_line}\n\n"
            f"Scenario:\n{scenario}"
        )

    def score_item(self, response: str, item: dict) -> float:
        if item.get("subtasks"):
            return score_subtask_completion(response, item)
        if item.get("required_keywords"):
            return score_keyword_match(response, item)
        if item.get("choices"):
            return score_multiple_choice(response, item)
        return score_keyword_match(response, item)

    def compute_summary_metrics(self, results: list[ItemResult]) -> dict:
        if not results:
            return {"soc_score": 0.0}

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

        # Per-severity breakdown
        by_severity: dict[str, dict] = {}
        for r in results:
            sev = r.metadata.get("severity", "unknown")
            if sev not in by_severity:
                by_severity[sev] = {"score_sum": 0.0, "total": 0}
            by_severity[sev]["total"] += 1
            by_severity[sev]["score_sum"] += r.score

        severity_scores = {
            sev: round(v["score_sum"] / v["total"], 4)
            for sev, v in by_severity.items()
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

        alerts = []
        weak = [cat for cat, sc in category_scores.items() if sc < 0.4]
        if weak:
            alerts.append(
                f"LOW SOC performance in: {', '.join(sorted(weak))}. "
                "Model struggles with these SOC task types."
            )
        if mean_score < 0.3:
            alerts.append(
                f"VERY LOW overall SOC score ({mean_score:.0%}): "
                "model is not suitable for SOC-automation applications."
            )

        return {
            "soc_score": mean_score,
            "soc_score_%": round(mean_score * 100, 2),
            "num_total": total,
            "by_category": category_scores,
            "by_severity": severity_scores,
            "by_difficulty": difficulty_scores,
            "alerts": alerts,
        }
