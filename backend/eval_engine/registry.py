"""
Central registry that maps a Benchmark record to the correct runner class.
Add new runners here to make them available to the pipeline.
"""
import logging
from core.models import Benchmark, BenchmarkType
from eval_engine.base import BaseBenchmarkRunner

logger = logging.getLogger(__name__)

# Name-based overrides (for built-in benchmarks with specific runners)
_NAME_REGISTRY: dict[str, type[BaseBenchmarkRunner]] = {}

# Type-based fallbacks
_TYPE_REGISTRY: dict[BenchmarkType, type[BaseBenchmarkRunner]] = {}


def _lazy_register() -> None:
    """Import runners lazily to avoid circular imports."""
    global _NAME_REGISTRY, _TYPE_REGISTRY
    if _NAME_REGISTRY:
        return

    from eval_engine.academic.mmlu import MMLURunner
    from eval_engine.safety.refusals import SafetyRefusalsRunner
    from eval_engine.custom.runner import CustomRunner

    _NAME_REGISTRY = {
        "MMLU (subset)": MMLURunner,
        "Safety Refusals": SafetyRefusalsRunner,
        "Frontier: Autonomy (Probe)": SafetyRefusalsRunner,  # reuse scoring logic
    }

    _TYPE_REGISTRY = {
        BenchmarkType.ACADEMIC: MMLURunner,
        BenchmarkType.CODING: CustomRunner,
        BenchmarkType.SAFETY: SafetyRefusalsRunner,
        BenchmarkType.CUSTOM: CustomRunner,
    }


def get_runner(benchmark: Benchmark, bench_library_path: str) -> BaseBenchmarkRunner:
    """Return the appropriate runner instance for a benchmark."""
    _lazy_register()

    runner_cls = _NAME_REGISTRY.get(benchmark.name) or _TYPE_REGISTRY.get(benchmark.type)

    if runner_cls is None:
        from eval_engine.custom.runner import CustomRunner
        logger.warning(f"No specific runner for '{benchmark.name}', using CustomRunner.")
        runner_cls = CustomRunner

    return runner_cls(benchmark=benchmark, bench_library_path=bench_library_path)
