"""
Cybersecurity benchmark runners — Phase 1–3 integration.

Phase 1 (MVP):
  - CybenchRunner       (offensive CTF tasks)
  - CyberSecBenchRunner (knowledge & reasoning MCQ)
  - DefenseBenchRunner  (SOC / blue-team tasks)

Phase 2:
  - InterCodeCTFRunner  (interactive bash/SQL/web CTF tasks)
  - CTIBenchRunner      (cyber threat intelligence MCQ + analysis)
  - CyberBenchRunner    (multi-domain coverage)
  - SOCBenchRunner      (SOC alert triage & response)

Phase 3:
  - PACEbenchRunner     (agent-focused offensive CTF)
  - CAIBenchRunner      (AI-specific security)
  - CyScenarioBenchRunner (long-horizon attack/defense planning)
  - CyberGymRunner      (long-horizon pentesting exercises)
  - EVMbenchRunner      (Ethereum/Web3 smart contract security)
  - SusVibesRunner      (secure coding vulnerability detection)

And the shared CyberTask abstraction with scoring utilities.
"""
from eval_engine.cybersecurity.cybench import CybenchRunner
from eval_engine.cybersecurity.cybersec_bench import CyberSecBenchRunner
from eval_engine.cybersecurity.defense_bench import DefenseBenchRunner
from eval_engine.cybersecurity.intercode_ctf import InterCodeCTFRunner
from eval_engine.cybersecurity.cti_bench import CTIBenchRunner
from eval_engine.cybersecurity.cyberbench import CyberBenchRunner
from eval_engine.cybersecurity.soc_bench import SOCBenchRunner
from eval_engine.cybersecurity.pace_bench import PACEbenchRunner
from eval_engine.cybersecurity.cai_bench import CAIBenchRunner
from eval_engine.cybersecurity.cy_scenario_bench import CyScenarioBenchRunner
from eval_engine.cybersecurity.cyber_gym import CyberGymRunner
from eval_engine.cybersecurity.evm_bench import EVMbenchRunner
from eval_engine.cybersecurity.sus_vibes import SusVibesRunner
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
    # Phase 1
    "CybenchRunner",
    "CyberSecBenchRunner",
    "DefenseBenchRunner",
    # Phase 2
    "InterCodeCTFRunner",
    "CTIBenchRunner",
    "CyberBenchRunner",
    "SOCBenchRunner",
    # Phase 3
    "PACEbenchRunner",
    "CAIBenchRunner",
    "CyScenarioBenchRunner",
    "CyberGymRunner",
    "EVMbenchRunner",
    "SusVibesRunner",
    # Shared utilities
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
