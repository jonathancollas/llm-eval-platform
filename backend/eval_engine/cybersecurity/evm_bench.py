"""
EVMbench Runner — Ethereum / Web3 smart-contract security benchmark.

EVMbench evaluates LLM understanding of Ethereum Virtual Machine (EVM)
smart-contract vulnerabilities.  Tasks include vulnerability identification
in Solidity code, exploit scenario description, and remediation advice for
common Web3 attack classes such as reentrancy, integer overflow, and access-
control flaws.

Dataset item format:
  {
    "id":               str,      # e.g. "reentrancy/dao_style_001"
    "prompt":           str,      # question or Solidity code snippet with task
    "expected":         str,      # correct answer / vulnerability name
    "choices":          dict,     # MCQ choices (optional)
    "vulnerability_type": str,    # reentrancy | integer_overflow |
                                  # access_control | timestamp_dep |
                                  # tx_origin | dos | front_running |
                                  # flash_loan | logic_error
    "item_type":        str,      # identification | mcq | remediation
    "difficulty":       str,      # easy | medium | hard | expert
    "required_keywords":[str],    # for identification / remediation items
    "tags":             [str],
    "explanation":      str
  }

Scoring:
  - mcq            → multiple-choice (0 or 1)
  - identification → keyword-match partial credit (0.0–1.0)
  - remediation    → keyword-match partial credit (0.0–1.0)

Metrics:
  overall_score          — mean score
  by_vulnerability_type  — per-vuln-class mean scores
  by_item_type           — per-task-type mean scores
  by_difficulty          — per-difficulty mean scores
"""
from eval_engine.base import BaseBenchmarkRunner, ItemResult
from eval_engine.cybersecurity.cyber_task import (
    score_multiple_choice,
    score_keyword_match,
)


class EVMbenchRunner(BaseBenchmarkRunner):
    """
    Evaluates LLM Web3 / smart-contract security expertise across
    vulnerability identification, MCQ, and remediation tasks.
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
                "You are a smart-contract security auditor. "
                "Select the single best answer (respond with only the letter)."
            )
        elif item_type == "identification":
            instruction = (
                "You are a smart-contract security auditor. "
                "Analyse the following Solidity code and identify the vulnerability "
                "class, the vulnerable line(s), and the potential impact."
            )
        else:  # remediation
            instruction = (
                "You are a smart-contract security auditor. "
                "Describe how to remediate the identified vulnerability, "
                "including specific code patterns and best practices."
            )

        prompt = f"{few_shot_block}{instruction}\n\n{question}\n"
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

        by_vuln: dict[str, dict] = {}
        for r in results:
            vt = r.metadata.get("vulnerability_type", "unknown")
            if vt not in by_vuln:
                by_vuln[vt] = {"score_sum": 0.0, "total": 0}
            by_vuln[vt]["total"] += 1
            by_vuln[vt]["score_sum"] += r.score

        vuln_metrics = {
            vt: round(v["score_sum"] / v["total"], 4)
            for vt, v in by_vuln.items()
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
            "by_vulnerability_type": vuln_metrics,
            "by_item_type": item_type_metrics,
            "by_difficulty": difficulty_metrics,
        }
