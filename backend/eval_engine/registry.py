"""
Runner registry — routes a Benchmark to the correct runner.
Priority: lm-eval harness (by task name) → named override → type fallback → custom.
"""
import logging
from core.models import Benchmark, BenchmarkType
from eval_engine.base import BaseBenchmarkRunner

logger = logging.getLogger(__name__)
_initialized = False
_NAME_REGISTRY: dict = {}
_TYPE_REGISTRY: dict = {}


def _lazy_register():
    global _initialized, _NAME_REGISTRY, _TYPE_REGISTRY
    if _initialized:
        return
    from eval_engine.academic.mmlu import MMLURunner
    from eval_engine.safety.refusals import SafetyRefusalsRunner
    from eval_engine.custom.runner import CustomRunner

    _NAME_REGISTRY = {
        "MMLU (subset)":                      MMLURunner,
        "HumanEval (mini)":                   MMLURunner,
        "Safety Refusals":                    SafetyRefusalsRunner,
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

    from eval_engine.harness_runner import HARNESS_CATALOG, get_available_harness_tasks

    # 1. Check if this benchmark's name matches an lm-eval task
    task_name = _find_harness_task(benchmark.name)
    if task_name:
        available = get_available_harness_tasks()
        if task_name in available:
            try:
                from eval_engine.harness_runner import HarnessRunner
                logger.info(f"Routing '{benchmark.name}' → HarnessRunner (task={task_name})")
                return HarnessRunner(benchmark=benchmark, bench_library_path=bench_library_path, task_name=task_name)
            except ImportError:
                logger.warning("lm-eval not available, falling back to local runner")

    # 2. Named override (INESIA frontier, built-in local)
    runner_cls = _NAME_REGISTRY.get(benchmark.name)
    if runner_cls:
        return runner_cls(benchmark=benchmark, bench_library_path=bench_library_path)

    # 3. Type fallback
    runner_cls = _TYPE_REGISTRY.get(benchmark.type)
    if runner_cls:
        return runner_cls(benchmark=benchmark, bench_library_path=bench_library_path)

    # 4. Generic fallback
    from eval_engine.custom.runner import CustomRunner
    logger.warning(f"No runner for '{benchmark.name}', using CustomRunner")
    return CustomRunner(benchmark=benchmark, bench_library_path=bench_library_path)


def _find_harness_task(benchmark_name: str) -> str | None:
    """
    Try to match a benchmark name to an lm-eval task.
    Checks: exact match on name, then fuzzy match on HARNESS_CATALOG keys.
    """
    from eval_engine.harness_runner import HARNESS_CATALOG, _task_display_name

    name_lower = benchmark_name.lower().strip()

    # Direct match on task ID
    if name_lower in HARNESS_CATALOG:
        return name_lower

    # Match on display name
    for task_id, meta in HARNESS_CATALOG.items():
        display = _task_display_name(task_id).lower()
        if name_lower == display or name_lower == task_id.replace("_", " "):
            return task_id

    # Partial match — task ID as prefix of benchmark name
    for task_id in HARNESS_CATALOG:
        if name_lower.startswith(task_id.replace("_", " ")) or task_id in name_lower.replace(" ", "_"):
            return task_id

    return None
