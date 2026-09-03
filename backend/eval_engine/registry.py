"""
Runner registry — routes a Benchmark to the correct runner.

Priority:
1. has_dataset=True AND dataset_path set → always use local runner (fast, no HuggingFace)
2. Named override (INESIA frontier benchmarks)
3. lm-eval harness (explicit config.lm_eval_task, then exact name match)
4. Type fallback
5. CustomRunner (default)
"""
import json
import logging
from core.models import Benchmark, BenchmarkType
from eval_engine.base import BaseBenchmarkRunner

logger = logging.getLogger(__name__)
_initialized = False
_NAME_REGISTRY: dict = {}
_TYPE_REGISTRY: dict = {}

# Benchmarks that ALWAYS use local runners regardless of name matching
LOCAL_ONLY_NAMES = {
    "MMLU (subset)", "HumanEval (mini)", "Safety Refusals",
    "Giskard LLM Scan",
    "Safety Refusals (INESIA)", "Frontier: Autonomy Probe",
    "Cyber Uplift (INESIA)", "CBRN-E Uplift Probe (INESIA)",
    "Loss of Control (INESIA)", "Evaluation Awareness (INESIA)",
    "Capability Overhang (INESIA)",
    "Mechanistic Interpretability Probe (INESIA)",
    "Deception Probe (INESIA)",
    "Manipulation Information d'Origine Étrangère (INESIA)",
    # Purple Llama benchmarks
    "CyberSecEval (Purple Llama)",
    "LlamaGuard Harm Classification (Purple Llama)",
    # Cybersecurity benchmarks (Phase 1)
    "Cybench",
    "CyberSec-Bench",
    "DefenseBench",
    # Cybersecurity benchmarks (Phase 2)
    "InterCode CTF",
    "CTIBench",
    "CyberBench",
    "SOC Bench",
    # Cybersecurity benchmarks (Phase 3)
    "PACEbench",
    "CAIBench",
    "CyScenarioBench",
    "CyberGym",
    "EVMbench",
    "SusVibes",
    # NRBC-E benchmarks (all 16)
    "SAFE-Bio (NRBC-E)",
    "BioBench (NRBC-E)",
    "ChemBench (NRBC-E)",
    "SafetyChem Evals (NRBC-E)",
    "Nuclear QA Bench (NRBC-E)",
    "RDD Scenario Eval (NRBC-E)",
    "Explosive Risk Bench (NRBC-E)",
    "Hazmat Classification (NRBC-E)",
    "NRBC-E QA Sets",
    "CTI-WMD Bench (NRBC-E)",
    "WMD Scenario Bench (NRBC-E)",
    "Frontier Safety Evals (NRBC-E)",
    "Pandemic Sim Bench (NRBC-E)",
    "Crisis Response Bench (NRBC-E)",
    "Policy Compliance Bench (NRBC-E)",
    "Refusal Eval Suites (NRBC-E)",
}


def _lazy_register():
    global _initialized, _NAME_REGISTRY, _TYPE_REGISTRY
    if _initialized:
        return

    from eval_engine.academic.mmlu import MMLURunner
    from eval_engine.safety.refusals import SafetyRefusalsRunner
    from eval_engine.safety.giskard import GiskardRunner
    from eval_engine.safety.purple_llama import PurpleLlamaRunner
    from eval_engine.custom.runner import CustomRunner
    from eval_engine.safety.sycophancy import SycophancyRunner
    from eval_engine.cybersecurity.cybench import CybenchRunner
    from eval_engine.cybersecurity.cybersec_bench import CyberSecBenchRunner
    from eval_engine.cybersecurity.defense_bench import DefenseBenchRunner
    # Phase 2
    from eval_engine.cybersecurity.intercode_ctf import InterCodeCTFRunner
    from eval_engine.cybersecurity.cti_bench import CTIBenchRunner
    from eval_engine.cybersecurity.cyberbench import CyberBenchRunner
    from eval_engine.cybersecurity.soc_bench import SOCBenchRunner
    # Phase 3
    from eval_engine.cybersecurity.pace_bench import PACEbenchRunner
    from eval_engine.cybersecurity.cai_bench import CAIBenchRunner
    from eval_engine.cybersecurity.cy_scenario_bench import CyScenarioBenchRunner
    from eval_engine.cybersecurity.cyber_gym import CyberGymRunner
    from eval_engine.cybersecurity.evm_bench import EVMbenchRunner
    from eval_engine.cybersecurity.sus_vibes import SusVibesRunner
    from eval_engine.nrbce.runner import NRBCERunner

    _NAME_REGISTRY = {
        "MMLU (subset)":                      MMLURunner,
        "HumanEval (mini)":                   MMLURunner,
        "Safety Refusals":                    SafetyRefusalsRunner,
        "Giskard LLM Scan":                   GiskardRunner,
        "Safety Refusals (INESIA)":           SafetyRefusalsRunner,
        "Frontier: Autonomy Probe":           SafetyRefusalsRunner,
        "Cyber Uplift (INESIA)":              SafetyRefusalsRunner,
        "CBRN-E Uplift Probe (INESIA)":       SafetyRefusalsRunner,
        "Loss of Control (INESIA)":           SafetyRefusalsRunner,
        "Evaluation Awareness (INESIA)":      SafetyRefusalsRunner,
        "Capability Overhang (INESIA)":       SafetyRefusalsRunner,
        "Mechanistic Interpretability Probe (INESIA)": SafetyRefusalsRunner,
        "Deception Probe (INESIA)":           SafetyRefusalsRunner,
        "Manipulation Information d'Origine Étrangère (INESIA)": SafetyRefusalsRunner,
        # Purple Llama
        "CyberSecEval (Purple Llama)":                 PurpleLlamaRunner,
        "LlamaGuard Harm Classification (Purple Llama)": PurpleLlamaRunner,
        "Sycophancy Evaluation (INESIA)":     SycophancyRunner,
        # Cybersecurity benchmarks (Phase 1)
        "Cybench":                            CybenchRunner,
        "CyberSec-Bench":                     CyberSecBenchRunner,
        "DefenseBench":                       DefenseBenchRunner,
        # Cybersecurity benchmarks (Phase 2)
        "InterCode CTF":                      InterCodeCTFRunner,
        "CTIBench":                           CTIBenchRunner,
        "CyberBench":                         CyberBenchRunner,
        "SOC Bench":                          SOCBenchRunner,
        # Cybersecurity benchmarks (Phase 3)
        "PACEbench":                          PACEbenchRunner,
        "CAIBench":                           CAIBenchRunner,
        "CyScenarioBench":                    CyScenarioBenchRunner,
        "CyberGym":                           CyberGymRunner,
        "EVMbench":                           EVMbenchRunner,
        "SusVibes":                           SusVibesRunner,
        # NRBC-E benchmarks (all 16)
        "SAFE-Bio (NRBC-E)":                  NRBCERunner,
        "BioBench (NRBC-E)":                  NRBCERunner,
        "ChemBench (NRBC-E)":                 NRBCERunner,
        "SafetyChem Evals (NRBC-E)":          NRBCERunner,
        "Nuclear QA Bench (NRBC-E)":          NRBCERunner,
        "RDD Scenario Eval (NRBC-E)":         NRBCERunner,
        "Explosive Risk Bench (NRBC-E)":      NRBCERunner,
        "Hazmat Classification (NRBC-E)":     NRBCERunner,
        "NRBC-E QA Sets":                     NRBCERunner,
        "CTI-WMD Bench (NRBC-E)":             NRBCERunner,
        "WMD Scenario Bench (NRBC-E)":        NRBCERunner,
        "Frontier Safety Evals (NRBC-E)":     NRBCERunner,
        "Pandemic Sim Bench (NRBC-E)":        NRBCERunner,
        "Crisis Response Bench (NRBC-E)":     NRBCERunner,
        "Policy Compliance Bench (NRBC-E)":   NRBCERunner,
        "Refusal Eval Suites (NRBC-E)":       NRBCERunner,
    }
    _TYPE_REGISTRY = {
        BenchmarkType.SAFETY:   SafetyRefusalsRunner,
        BenchmarkType.ACADEMIC: MMLURunner,
        BenchmarkType.CODING:   CustomRunner,
        BenchmarkType.CUSTOM:   CustomRunner,
    }
    _initialized = True


def get_runner(benchmark: Benchmark, bench_library_path: str) -> BaseBenchmarkRunner:
    _lazy_register()

    # 1. If benchmark has a local dataset file → always use local runner
    #    This prevents lm-eval HuggingFace downloads for built-in datasets
    if benchmark.has_dataset and benchmark.dataset_path:
        from pathlib import Path
        full_path = Path(bench_library_path) / benchmark.dataset_path
        if full_path.exists():
            runner_cls = _NAME_REGISTRY.get(benchmark.name) or _TYPE_REGISTRY.get(benchmark.type)
            if runner_cls:
                logger.info(f"Local dataset → using {runner_cls.__name__} for '{benchmark.name}'")
                return runner_cls(benchmark=benchmark, bench_library_path=bench_library_path)

    # 2. Named override (always takes priority for known INESIA benchmarks)
    if benchmark.name in _NAME_REGISTRY:
        runner_cls = _NAME_REGISTRY[benchmark.name]
        logger.info(f"Named override → {runner_cls.__name__} for '{benchmark.name}'")
        return runner_cls(benchmark=benchmark, bench_library_path=bench_library_path)

    # 3. lm-eval harness — only for benchmarks WITHOUT a local dataset
    #    (they explicitly need HuggingFace)
    config = _benchmark_config(benchmark)
    if benchmark.name not in LOCAL_ONLY_NAMES:
        task_name = _find_harness_task(benchmark.name, config)
        if task_name:
            try:
                from eval_engine.harness_runner import HarnessRunner, get_available_harness_tasks
                available = get_available_harness_tasks()
                explicit = bool(
                    config.get("lm_eval_task") or config.get("harness_task")
                )
                # Honor an explicit task id from harness-search "Add" even if
                # the installed index failed to enumerate the full 14k list.
                if explicit or task_name in available:
                    logger.info(f"lm-eval harness → task '{task_name}' for '{benchmark.name}'")
                    return HarnessRunner(
                        benchmark=benchmark,
                        bench_library_path=bench_library_path,
                        task_name=task_name,
                    )
            except ImportError:
                logger.warning("lm-eval not available, falling back to local runner")

    # 4. Type fallback
    runner_cls = _TYPE_REGISTRY.get(benchmark.type)
    if runner_cls:
        logger.info(f"Type fallback → {runner_cls.__name__} for '{benchmark.name}' (type={benchmark.type})")
        return runner_cls(benchmark=benchmark, bench_library_path=bench_library_path)

    # 5. Generic fallback
    from eval_engine.custom.runner import CustomRunner
    logger.warning(f"No specific runner for '{benchmark.name}', using CustomRunner")
    return CustomRunner(benchmark=benchmark, bench_library_path=bench_library_path)


def _benchmark_config(benchmark: Benchmark) -> dict:
    raw = getattr(benchmark, "config_json", None) or ""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _find_harness_task(benchmark_name: str, config: dict | None = None) -> str | None:
    """Match a benchmark to a lm-eval task ID.

    Prefer an explicit ``lm_eval_task`` stored when the bench was added from
    harness search. Otherwise require an *exact* task-id, slug, or display-name
    match against the installed lm-eval index.

    Do not prefix-match curated catalog keys: that routed
    ``mmlu_abstract_algebra`` (display "Mmlu Abstract Algebra") to ``mmlu``.
    """
    if config:
        explicit = config.get("lm_eval_task") or config.get("harness_task")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()

    try:
        from eval_engine.harness_runner import _task_display_name, get_available_harness_tasks
    except ImportError:
        return None

    available = get_available_harness_tasks()
    name_lower = (benchmark_name or "").lower().strip()
    if not name_lower:
        return None

    if name_lower in available:
        return name_lower

    name_slug = name_lower.replace(" ", "_").replace("-", "_")
    if name_slug in available:
        return name_slug

    for task_id in available:
        if name_lower == _task_display_name(task_id).lower():
            return task_id

    return None
