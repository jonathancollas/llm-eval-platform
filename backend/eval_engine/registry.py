"""
Central registry — maps a Benchmark to the correct runner.
Priority: name match → harness → type fallback → custom.
"""
import logging
from core.models import Benchmark, BenchmarkType
from eval_engine.base import BaseBenchmarkRunner
from eval_engine.harness_runner import HARNESS_TASK_MAP
from core.models import ModelProvider

logger = logging.getLogger(__name__)

_NAME_REGISTRY: dict[str, type] = {}
_TYPE_REGISTRY: dict[BenchmarkType, type] = {}
_initialized = False


def _lazy_register() -> None:
    global _NAME_REGISTRY, _TYPE_REGISTRY, _initialized
    if _initialized:
        return

    from eval_engine.academic.mmlu import MMLURunner
    from eval_engine.safety.refusals import SafetyRefusalsRunner
    from eval_engine.custom.runner import CustomRunner

    # Specific name overrides (built-in datasets that exist locally)
    _NAME_REGISTRY = {
        "MMLU (subset)":              MMLURunner,
        "Safety Refusals (INESIA)":   SafetyRefusalsRunner,
        "Frontier: Autonomy Probe":   SafetyRefusalsRunner,
        "Autonomy Probe":             SafetyRefusalsRunner,
        # INESIA frontier — use safety runner (refusal detection)
        "Cyber Uplift (INESIA)":              SafetyRefusalsRunner,
        "CBRN-E Uplift Probe (INESIA)":       SafetyRefusalsRunner,
        "Loss of Control (INESIA)":           SafetyRefusalsRunner,
        "Evaluation Awareness (INESIA)":      SafetyRefusalsRunner,
        "Capability Overhang (INESIA)":       SafetyRefusalsRunner,
        "Mechanistic Interpretability Probe (INESIA)": SafetyRefusalsRunner,
        "Deception Probe (INESIA)":           SafetyRefusalsRunner,
        "Manipulation Information d'Origine Étrangère (INESIA)": SafetyRefusalsRunner,
    }

    # Type fallbacks
    _TYPE_REGISTRY = {
        BenchmarkType.ACADEMIC: MMLURunner,
        BenchmarkType.CODING:   CustomRunner,
        BenchmarkType.SAFETY:   SafetyRefusalsRunner,
        BenchmarkType.CUSTOM:   CustomRunner,
    }

    _initialized = True


def get_runner(benchmark: Benchmark, bench_library_path: str) -> BaseBenchmarkRunner:
    """Return the best runner for this benchmark."""
    _lazy_register()

    # 1. Check if lm-eval harness supports this benchmark (by key match on name)
    bench_key = _infer_key(benchmark.name)
    if bench_key and bench_key in HARNESS_TASK_MAP:
        try:
            from eval_engine.harness_runner import HarnessRunner
            task_name = HARNESS_TASK_MAP[bench_key]
            logger.info(f"Using HarnessRunner for '{benchmark.name}' → task '{task_name}'")
            return HarnessRunner(
                benchmark=benchmark,
                bench_library_path=bench_library_path,
                task_name=task_name,
            )
        except ImportError:
            logger.warning("lm-eval not installed, falling back to local runner")

    # 2. Name-specific override
    runner_cls = _NAME_REGISTRY.get(benchmark.name)
    if runner_cls:
        return runner_cls(benchmark=benchmark, bench_library_path=bench_library_path)

    # 3. Type fallback
    runner_cls = _TYPE_REGISTRY.get(benchmark.type)
    if runner_cls:
        logger.info(f"Using type fallback runner for '{benchmark.name}' (type={benchmark.type})")
        return runner_cls(benchmark=benchmark, bench_library_path=bench_library_path)

    # 4. Generic custom runner
    from eval_engine.custom.runner import CustomRunner
    logger.warning(f"No runner found for '{benchmark.name}', using CustomRunner")
    return CustomRunner(benchmark=benchmark, bench_library_path=bench_library_path)


def _infer_key(name: str) -> str | None:
    """Try to match a benchmark name to a HARNESS_TASK_MAP key."""
    name_lower = name.lower()
    # Direct key match
    for key in HARNESS_TASK_MAP:
        if key.lower() in name_lower or name_lower.startswith(key.lower()):
            return key
    # Fuzzy: first word match
    first_word = name_lower.split()[0] if name_lower else ""
    for key in HARNESS_TASK_MAP:
        if key.startswith(first_word) or first_word in key:
            return key
    return None
