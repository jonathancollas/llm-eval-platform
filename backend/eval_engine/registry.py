"""
Runner registry — routes a Benchmark to the correct runner.

Priority:
1. has_dataset=True AND dataset_path set → always use local runner (fast, no HuggingFace)
2. Named override (INESIA frontier benchmarks)
3. lm-eval harness (by task name match) — only if no local dataset
4. Type fallback
5. CustomRunner (default)
"""
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
    if benchmark.name not in LOCAL_ONLY_NAMES:
        task_name = _find_harness_task(benchmark.name)
        if task_name:
            try:
                from eval_engine.harness_runner import HarnessRunner, get_available_harness_tasks
                if task_name in get_available_harness_tasks():
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


def _find_harness_task(benchmark_name: str) -> str | None:
    """Match a benchmark name to a lm-eval task ID."""
    try:
        from eval_engine.harness_runner import HARNESS_CATALOG, _task_display_name
    except ImportError:
        return None

    name_lower = benchmark_name.lower().strip()

    # Direct task ID match
    if name_lower in HARNESS_CATALOG:
        return name_lower

    # Display name match
    for task_id in HARNESS_CATALOG:
        display = _task_display_name(task_id).lower()
        if name_lower == display:
            return task_id

    # Fuzzy: task ID embedded in benchmark name (e.g. "GSM8K (CoT)" → "gsm8k_cot")
    name_slug = name_lower.replace(" ", "_").replace("-", "_")
    for task_id in HARNESS_CATALOG:
        if task_id in name_slug or name_slug.startswith(task_id):
            return task_id

    return None
