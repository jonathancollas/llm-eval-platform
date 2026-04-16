"""
Cybersecurity benchmark runners — Phase 1 MVP integration.

Exposes three Phase-1 benchmark runners:
  - CybenchRunner       (offensive CTF tasks)
  - CyberSecBenchRunner (knowledge & reasoning MCQ)
  - DefenseBenchRunner  (SOC / blue-team tasks)

And the shared CyberTask abstraction with scoring utilities.
"""
from eval_engine.cybersecurity.cybench import CybenchRunner
from eval_engine.cybersecurity.cybersec_bench import CyberSecBenchRunner
from eval_engine.cybersecurity.defense_bench import DefenseBenchRunner
from eval_engine.cybersecurity.cyber_task import (
    CyberTask,
    score_flag,
    score_multiple_choice,
    score_keyword_match,
    score_subtask_completion,
    CATEGORY_OFFENSE,
    CATEGORY_DEFENSE,
    CATEGORY_REASONING,
    CATEGORY_LONG_HORIZON,
)

__all__ = [
    "CybenchRunner",
    "CyberSecBenchRunner",
    "DefenseBenchRunner",
    "CyberTask",
    "score_flag",
    "score_multiple_choice",
    "score_keyword_match",
    "score_subtask_completion",
    "CATEGORY_OFFENSE",
    "CATEGORY_DEFENSE",
    "CATEGORY_REASONING",
    "CATEGORY_LONG_HORIZON",
]
