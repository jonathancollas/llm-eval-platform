"""
Abstract base for all benchmark runners.
Every benchmark is a plugin that implements this interface.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
import json
import random
from pathlib import Path

from core.models import LLMModel, Benchmark, EvalRun


@dataclass
class ItemResult:
    """Result for a single benchmark item."""
    item_index: int
    prompt: str
    response: str
    expected: Optional[str]
    score: float  # 0.0 – 1.0
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    metadata: dict = field(default_factory=dict)


@dataclass
class RunSummary:
    """Aggregated results for one model × one benchmark run."""
    score: float          # primary metric (accuracy, pass@1, safety_score…)
    metrics: dict         # full metrics dict
    total_cost_usd: float
    total_latency_ms: int
    num_items: int
    item_results: list[ItemResult]


class BaseBenchmarkRunner(ABC):
    """
    Plugin interface for benchmark runners.
    Subclasses must implement `load_items` and `score_item`.
    """

    def __init__(self, benchmark: Benchmark, bench_library_path: str):
        self.benchmark = benchmark
        self.bench_library_path = Path(bench_library_path)
        self.config: dict = json.loads(benchmark.config_json or "{}")

    def load_dataset(self) -> list[dict]:
        """Load raw items from the benchmark's dataset_path JSON file."""
        if not self.benchmark.dataset_path:
            return []
        full_path = self.bench_library_path / self.benchmark.dataset_path
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("items", [])

    def sample_items(self, items: list[dict], max_samples: int, seed: int) -> list[dict]:
        """Reproducibly sample items."""
        if max_samples and len(items) > max_samples:
            rng = random.Random(seed)
            items = rng.sample(items, max_samples)
        return items

    @abstractmethod
    async def build_prompt(self, item: dict, few_shot_examples: list[dict]) -> str:
        """Build the prompt string to send to the model."""
        ...

    @abstractmethod
    def score_item(self, response: str, item: dict) -> float:
        """Score the model's response for this item. Returns 0.0 – 1.0."""
        ...

    def compute_summary_metrics(self, results: list[ItemResult]) -> dict:
        """Override to add benchmark-specific aggregate metrics."""
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
        """
        Full benchmark run for one model.
        progress_callback(done, total) is called after each item.
        """
        from eval_engine.litellm_client import complete

        raw_items = self.load_dataset()
        items = self.sample_items(raw_items, max_samples, seed)

        # Few-shot pool: items not in our test set (seeded)
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
                progress_callback(idx + 1, len(items))

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
