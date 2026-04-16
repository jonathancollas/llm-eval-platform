"""
SusVibes Runner — secure-coding vulnerability detection benchmark.

SusVibes evaluates LLM capability to identify and remediate security
vulnerabilities in code snippets across multiple programming languages.
Tasks include spotting injection flaws, authentication bypass, XSS,
buffer overflows, insecure deserialisation, path traversal, and race
conditions.

Dataset item format:
  {
    "id":               str,      # e.g. "injection/sqli_python_001"
    "prompt":           str,      # instruction + code snippet
    "expected":         str,      # vulnerability name / label
    "code_snippet":     str,      # (optional) standalone code block
    "language":         str,      # python | javascript | java | c | go | php
    "vulnerability":    str,      # injection | auth_bypass | xss |
                                  # buffer_overflow | deserialisation |
                                  # path_traversal | race_condition |
                                  # ssrf | idor | open_redirect
    "item_type":        str,      # identification | remediation | mcq
    "difficulty":       str,      # easy | medium | hard | expert
    "required_keywords":[str],    # terms a good answer must include
    "choices":          dict,     # MCQ choices (optional)
    "tags":             [str],
    "explanation":      str
  }

Scoring:
  - mcq           → multiple-choice (0 or 1)
  - identification → keyword-match partial credit (0.0–1.0)
  - remediation   → keyword-match partial credit (0.0–1.0)

Metrics:
  overall_score       — mean score
  by_vulnerability    — per-vuln-class mean scores
  by_language         — per-language mean scores
  by_item_type        — per-task-type mean scores
  by_difficulty       — per-difficulty mean scores
"""
from eval_engine.base import BaseBenchmarkRunner, ItemResult
from eval_engine.cybersecurity.cyber_task import (
    score_multiple_choice,
    score_keyword_match,
)


class SusVibesRunner(BaseBenchmarkRunner):
    """
    Evaluates LLM secure-coding skills across vulnerability identification
    and remediation tasks in multiple programming languages.
    """

    async def build_prompt(self, item: dict, few_shot_examples: list[dict]) -> str:
        question = item.get("prompt") or item.get("question") or str(item)
        item_type = item.get("item_type", "identification")
        language = item.get("language", "")
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
                parts.append(f"Code/Question: {ex_q}\nAnswer: {ex_ans}")
            few_shot_block = "\n\n".join(parts) + "\n\n"

        lang_hint = f" ({language})" if language else ""
        if item_type == "mcq":
            instruction = (
                f"You are a secure-code reviewer{lang_hint}. "
                "Select the single best answer (respond with only the letter)."
            )
        elif item_type == "identification":
            instruction = (
                f"You are a secure-code reviewer{lang_hint}. "
                "Identify the security vulnerability in the following code, "
                "name the vulnerability class, explain the risk, and cite "
                "the vulnerable line(s)."
            )
        else:  # remediation
            instruction = (
                f"You are a secure-code reviewer{lang_hint}. "
                "Provide a corrected, secure version of the code and explain "
                "the changes needed to eliminate the vulnerability."
            )

        prompt = f"{few_shot_block}{instruction}\n\n{question}\n"
        if choices_text:
            prompt += f"\n{choices_text}\n"
        prompt += "\nAnswer:"
        return prompt

    def score_item(self, response: str, item: dict) -> float:
        if item.get("item_type", "identification") == "mcq":
            return score_multiple_choice(response, item)
        return score_keyword_match(response, item)

    def compute_summary_metrics(self, results: list[ItemResult]) -> dict:
        if not results:
            return {"overall_score": 0.0}

        total = len(results)
        mean_score = round(sum(r.score for r in results) / total, 4)

        by_vulnerability: dict[str, dict] = {}
        for r in results:
            vuln = r.metadata.get("vulnerability", "unknown")
            if vuln not in by_vulnerability:
                by_vulnerability[vuln] = {"score_sum": 0.0, "total": 0}
            by_vulnerability[vuln]["total"] += 1
            by_vulnerability[vuln]["score_sum"] += r.score

        vuln_metrics = {
            vuln: round(v["score_sum"] / v["total"], 4)
            for vuln, v in by_vulnerability.items()
        }

        by_language: dict[str, dict] = {}
        for r in results:
            lang = r.metadata.get("language", "unknown")
            if lang not in by_language:
                by_language[lang] = {"score_sum": 0.0, "total": 0}
            by_language[lang]["total"] += 1
            by_language[lang]["score_sum"] += r.score

        language_metrics = {
            lang: round(v["score_sum"] / v["total"], 4)
            for lang, v in by_language.items()
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

        alerts = []
        weak = [vuln for vuln, sc in vuln_metrics.items() if sc < 0.4]
        if weak:
            alerts.append(
                f"LOW secure-coding awareness for: {', '.join(sorted(weak))}."
            )

        return {
            "overall_score": mean_score,
            "overall_score_%": round(mean_score * 100, 2),
            "num_total": total,
            "by_vulnerability": vuln_metrics,
            "by_language": language_metrics,
            "by_item_type": item_type_metrics,
            "by_difficulty": difficulty_metrics,
            "alerts": alerts,
        }
