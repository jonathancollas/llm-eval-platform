"""
Abstract base for all benchmark runners.
Every benchmark is a plugin that implements this interface.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional
import json
import logging
import random
from pathlib import Path

from core.models import LLMModel, Benchmark
from core.utils import resolve_safe_path

logger = logging.getLogger(__name__)


@dataclass
class ItemResult:
    item_index: int
    prompt: str
    response: str
    expected: Optional[str]
    score: float
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    metadata: dict = field(default_factory=dict)


@dataclass
class RunSummary:
    score: float
    metrics: dict
    total_cost_usd: float
    total_latency_ms: int
    num_items: int
    item_results: list[ItemResult]


@lru_cache(maxsize=64)
def _load_dataset_cached(full_path: str) -> list[dict]:
    """Load and cache a dataset JSON file.  Cached by absolute path string.

    The cache is process-level and lives for the lifetime of the worker.
    It is invalidated automatically when the process restarts (e.g. after a
    dataset upload followed by a gunicorn worker restart or Docker redeploy).
    """
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("items", [])
    except Exception as e:
        logger.error(f"Failed to load dataset {full_path}: {e}")
        return []


class BaseBenchmarkRunner(ABC):

    def __init__(self, benchmark: Benchmark, bench_library_path: str):
        self.benchmark = benchmark
        self.bench_library_path = Path(bench_library_path)
        self.config: dict = json.loads(benchmark.config_json or "{}")

    def load_dataset(self) -> list[dict]:
        """Load items from dataset_path JSON. Cached per file path."""
        if not self.benchmark.dataset_path:
            return []
        try:
            full_path = resolve_safe_path(self.bench_library_path, self.benchmark.dataset_path)
        except ValueError:
            logger.warning(
                f"Dataset path '{self.benchmark.dataset_path}' resolves outside the allowed directory "
                f"(benchmark: {self.benchmark.name}). Skipping dataset load."
            )
            return []
        if not full_path.exists():
            logger.warning(
                f"Dataset file not found: {full_path} "
                f"(benchmark: {self.benchmark.name}). "
                f"Upload a dataset via the Benchmarks page."
            )
            return []
        return list(_load_dataset_cached(str(full_path)))

    def sample_items(self, items: list[dict], max_samples: int, seed: int) -> list[dict]:
        if max_samples and len(items) > max_samples:
            rng = random.Random(seed)
            items = rng.sample(items, max_samples)
        return items

    @staticmethod
    def invalidate_dataset_cache(full_path: str) -> None:
        """Invalidate the LRU cache after uploading a new dataset file.

        NOTE: `functools.lru_cache` does not support per-key invalidation, so
        this clears the entire dataset cache (all benchmark files).  In practice
        this is acceptable because uploads are rare, the cache is warm again after
        the first benchmark run per file, and the cache is bounded to 64 entries.

        Call this immediately after writing a new dataset to disk.
        """
        _load_dataset_cached.cache_clear()

    @abstractmethod
    async def build_prompt(self, item: dict, few_shot_examples: list[dict]) -> str: ...

    @abstractmethod
    def score_item(self, response: str, item: dict) -> float: ...

    def compute_summary_metrics(self, results: list[ItemResult]) -> dict:
        if not results:
            return {}
        return {"accuracy": sum(r.score for r in results) / len(results)}

    async def run(
        self,
        model: LLMModel,
        max_samples: int,
        seed: int,
        temperature: float,
        progress_callback=None,
    ) -> RunSummary:
        from eval_engine.litellm_client import complete

        raw_items = self.load_dataset()

        # ── No dataset: return a clear no-op result instead of crashing ──────
        if not raw_items:
            logger.warning(
                f"No items loaded for benchmark '{self.benchmark.name}'. "
                f"Returning empty run — upload a dataset to get real results."
            )
            return RunSummary(
                score=0.0,
                metrics={"error": "no_dataset", "message": "Dataset file not found. Upload a JSON dataset via the Benchmarks page."},
                total_cost_usd=0.0,
                total_latency_ms=0,
                num_items=0,
                item_results=[],
            )

        items = self.sample_items(raw_items, max_samples, seed)

        few_shot_count = self.config.get("few_shot", 0)
        few_shot_pool = [i for i in raw_items if i not in items]
        rng = random.Random(seed + 1)
        few_shot_examples = rng.sample(few_shot_pool, min(few_shot_count, len(few_shot_pool)))

        max_tokens = self.config.get("max_tokens", 256)
        item_results: list[ItemResult] = []

        for idx, item in enumerate(items):
            prompt = await self.build_prompt(item, few_shot_examples)
            try:
                result = await complete(
                    model=model,
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                score = self.score_item(result.text, item)
                item_results.append(ItemResult(
                    item_index=idx,
                    prompt=prompt,
                    response=result.text,
                    expected=item.get("answer") or item.get("expected"),
                    score=score,
                    latency_ms=result.latency_ms,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cost_usd=result.cost_usd,
                    metadata={k: v for k, v in item.items() if k not in ("question", "prompt")},
                ))
            except Exception as e:
                item_results.append(ItemResult(
                    item_index=idx,
                    prompt=prompt,
                    response=f"ERROR: {e}",
                    expected=item.get("answer") or item.get("expected"),
                    score=0.0,
                    latency_ms=0,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    metadata={"error": str(e)},
                ))

            if progress_callback:
                progress_callback(idx + 1, len(items), item_results[-1])

        metrics = self.compute_summary_metrics(item_results)
        primary_score = metrics.get(
            self.benchmark.metric,
            metrics.get("accuracy", 0.0)
        )

        return RunSummary(
            score=primary_score,
            metrics=metrics,
            total_cost_usd=sum(r.cost_usd for r in item_results),
            total_latency_ms=sum(r.latency_ms for r in item_results),
            num_items=len(item_results),
            item_results=item_results,
        )
