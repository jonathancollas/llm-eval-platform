"""
lm-evaluation-harness runner — wraps EleutherAI's lm-eval for standardized scoring.

Each HarnessRunner instance handles one benchmark task.
We use lm-eval's task system to download + evaluate datasets automatically.
Our pipeline gets back a standard RunSummary.
"""
import asyncio
import json
import logging
import time
from typing import Optional

from core.models import LLMModel, Benchmark
from eval_engine.base import BaseBenchmarkRunner, RunSummary, ItemResult
from core.security import decrypt_api_key

logger = logging.getLogger(__name__)

# Map our benchmark keys → lm-eval task names
HARNESS_TASK_MAP = {
    # Academic / reasoning
    "hellaswag":             "hellaswag",
    "arc_challenge":         "arc_challenge",
    "arc_easy":              "arc_easy",
    "winogrande":            "winogrande",
    "piqa":                  "piqa",
    "siqa":                  "social_iqa",
    "boolq":                 "boolq",
    "openbookqa":            "openbookqa",
    "commonsenseqa":         "commonsenseqa",
    "logiqa":                "logiqa",

    # Knowledge
    "mmlu":                  "mmlu",
    "mmlu_pro":              "mmlu_pro",
    "truthfulqa":            "truthfulqa_mc1",
    "triviaqa":              "triviaqa",

    # Math
    "gsm8k":                 "gsm8k",
    "math_subset":           "math_word_problems",
    "mgsm":                  "mgsm_direct_en",

    # Code
    "humaneval_full":        "humaneval",
    "mbpp":                  "mbpp",

    # NLI
    "anli":                  "anli_r3",
    "wic":                   "wic",
    "drop":                  "drop",
    "lambada":               "lambada_openai",

    # Instruction following
    "ifeval":                "ifeval",

    # French
    "mmlu_fr":               "mmlu_fr",

    # Multilingual
    "mmmlu":                 "mmmlu",
}


def _make_lm_eval_model(model: LLMModel) -> "lm_eval.api.model.LM":
    """Create an lm-eval compatible model wrapper for our LiteLLM-backed models."""
    from lm_eval.models.openai_completions import LocalCompletionsAPI

    api_key = ""
    if model.api_key_encrypted:
        api_key = decrypt_api_key(model.api_key_encrypted)

    # Build model string for LiteLLM
    from eval_engine.litellm_client import _build_litellm_model_str, _is_openrouter
    model_str = _build_litellm_model_str(model)

    base_url = model.endpoint or "https://api.openai.com/v1"
    if _is_openrouter(model):
        base_url = "https://openrouter.ai/api/v1"
        from core.config import get_settings
        settings = get_settings()
        api_key = api_key or settings.openrouter_api_key or ""

    # Extract just the model name after provider prefix
    model_name = model_str.split("/", 1)[-1] if "/" in model_str else model_str

    return LocalCompletionsAPI(
        model=model_name,
        base_url=base_url,
        tokenizer_backend=None,
        max_length=model.context_length or 4096,
    )


class HarnessRunner(BaseBenchmarkRunner):
    """
    Uses lm-evaluation-harness to evaluate a benchmark.
    Downloads datasets automatically from HuggingFace.
    """

    def __init__(self, benchmark: Benchmark, bench_library_path: str, task_name: str):
        super().__init__(benchmark, bench_library_path)
        self.task_name = task_name

    # These are required by BaseBenchmarkRunner but not used in HarnessRunner
    async def build_prompt(self, item: dict, few_shot_examples: list[dict]) -> str:
        return ""

    def score_item(self, response: str, item: dict) -> float:
        return 0.0

    async def run(
        self,
        model: LLMModel,
        max_samples: int,
        seed: int,
        temperature: float,
        progress_callback=None,
    ) -> RunSummary:
        """Run evaluation via lm-eval harness in a thread pool."""
        logger.info(f"HarnessRunner: task={self.task_name}, model={model.name}, samples={max_samples}")

        try:
            summary = await asyncio.get_event_loop().run_in_executor(
                None,
                self._run_sync,
                model, max_samples, seed, temperature, progress_callback,
            )
            return summary
        except Exception as e:
            logger.error(f"HarnessRunner failed for {self.task_name}: {e}", exc_info=True)
            # Return a graceful failure rather than crashing the whole campaign
            return RunSummary(
                score=0.0,
                metrics={"error": str(e), "task": self.task_name},
                total_cost_usd=0.0,
                total_latency_ms=0,
                num_items=0,
                item_results=[],
            )

    def _run_sync(
        self,
        model: LLMModel,
        max_samples: int,
        seed: int,
        temperature: float,
        progress_callback,
    ) -> RunSummary:
        """Synchronous lm-eval execution (runs in thread pool)."""
        import lm_eval
        from lm_eval import evaluator

        t0 = time.monotonic()

        lm = _make_lm_eval_model(model)

        results = evaluator.simple_evaluate(
            model=lm,
            tasks=[self.task_name],
            num_fewshot=self.config.get("few_shot", 0),
            limit=max_samples if max_samples else None,
            random_seed=seed,
            numpy_random_seed=seed,
            torch_random_seed=seed,
            log_samples=True,
        )

        latency_ms = int((time.monotonic() - t0) * 1000)

        # Extract primary score
        task_results = results.get("results", {}).get(self.task_name, {})
        primary_metric = self.benchmark.metric or "acc,none"

        # lm-eval returns metrics like "acc,none", "acc_norm,none"
        score = (
            task_results.get(primary_metric)
            or task_results.get("acc,none")
            or task_results.get("acc_norm,none")
            or task_results.get("exact_match,none")
            or task_results.get("pass@1,none")
            or 0.0
        )

        # Build item results from logged samples
        item_results = []
        samples = results.get("samples", {}).get(self.task_name, [])
        for idx, sample in enumerate(samples):
            item_results.append(ItemResult(
                item_index=idx,
                prompt=str(sample.get("doc", {}).get("query", sample.get("doc", ""))),
                response=str(sample.get("resps", [[""]]) [0][0] if sample.get("resps") else ""),
                expected=str(sample.get("target", "")),
                score=float(sample.get("acc", 0.0) or sample.get("exact_match", 0.0) or 0.0),
                latency_ms=latency_ms // max(len(samples), 1),
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                metadata={"task": self.task_name},
            ))

        if progress_callback:
            progress_callback(len(item_results), len(item_results))

        return RunSummary(
            score=float(score),
            metrics={**task_results, "task": self.task_name},
            total_cost_usd=0.0,
            total_latency_ms=latency_ms,
            num_items=len(item_results),
            item_results=item_results,
        )
