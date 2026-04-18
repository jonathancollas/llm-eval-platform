"""
lm-evaluation-harness runner — EleutherAI standardized scoring.

Auto-discovers available tasks from lm-eval at startup.
Provides a curated catalog of 60+ top benchmarks across all domains.
"""
import asyncio
import logging
import time
from typing import Optional

from core.models import LLMModel, Benchmark
from eval_engine.base import BaseBenchmarkRunner, RunSummary, ItemResult

logger = logging.getLogger(__name__)


# ── Curated task catalog ───────────────────────────────────────────────────────
# Format: task_name → (domain, description, metric, few_shot)
# All verified to exist in lm-eval ≥0.4.4

HARNESS_CATALOG: dict[str, dict] = {

    # ── Raisonnement ────────────────────────────────────────────────────────────
    "hellaswag":        {"domain": "raisonnement", "metric": "acc_norm,none", "few_shot": 10,
                         "description": "Complétion de phrases nécessitant du sens commun. 70k exemples adversariaux."},
    "arc_easy":         {"domain": "raisonnement", "metric": "acc_norm,none", "few_shot": 25,
                         "description": "ARC questions sciences faciles — répondables par systèmes simples."},
    "arc_challenge":    {"domain": "raisonnement", "metric": "acc_norm,none", "few_shot": 25,
                         "description": "ARC questions sciences difficiles — nécessite raisonnement multi-étapes."},
    "winogrande":       {"domain": "raisonnement", "metric": "acc,none",      "few_shot": 5,
                         "description": "Résolution de pronoms ambigus. 44k exemples adversariaux."},
    "piqa":             {"domain": "raisonnement", "metric": "acc_norm,none", "few_shot": 0,
                         "description": "Physical Intuition QA — actions du quotidien."},
    "social_iqa":       {"domain": "raisonnement", "metric": "acc,none",      "few_shot": 0,
                         "description": "Social IQA — raisonnement sur interactions sociales."},
    "boolq":            {"domain": "raisonnement", "metric": "acc,none",      "few_shot": 0,
                         "description": "Questions booléennes issues de vraies recherches Google."},
    "copa":             {"domain": "raisonnement", "metric": "acc,none",      "few_shot": 0,
                         "description": "Choice of Plausible Alternatives — raisonnement causal et abductif."},
    "openbookqa":       {"domain": "raisonnement", "metric": "acc_norm,none", "few_shot": 0,
                         "description": "Questions nécessitant connaissances de base + raisonnement multi-hop."},
    "logiqa":           {"domain": "raisonnement", "metric": "acc_norm,none", "few_shot": 0,
                         "description": "Raisonnement logique formel — style GMAT/GRE."},
    "logiqa2":          {"domain": "raisonnement", "metric": "acc_norm,none", "few_shot": 0,
                         "description": "LogiQA v2 — raisonnement logique amélioré."},
    "drop":             {"domain": "raisonnement", "metric": "f1,none",       "few_shot": 3,
                         "description": "Discrete Reasoning Over Paragraphs — calculs sur texte."},
    "lambada_openai":   {"domain": "raisonnement", "metric": "acc,none",      "few_shot": 0,
                         "description": "Prédiction du dernier mot de passages narratifs."},
    "wic":              {"domain": "raisonnement", "metric": "acc,none",      "few_shot": 0,
                         "description": "Word in Context — désambiguïsation sémantique."},
    "anli_r1":          {"domain": "raisonnement", "metric": "acc,none",      "few_shot": 0,
                         "description": "Adversarial NLI Round 1."},
    "anli_r2":          {"domain": "raisonnement", "metric": "acc,none",      "few_shot": 0,
                         "description": "Adversarial NLI Round 2."},
    "anli_r3":          {"domain": "raisonnement", "metric": "acc,none",      "few_shot": 0,
                         "description": "Adversarial NLI Round 3 — le plus difficile."},
    "commonsense_qa":   {"domain": "raisonnement", "metric": "acc,none",      "few_shot": 0,
                         "description": "CommonsenseQA — basé sur ConceptNet."},

    # ── Connaissances ───────────────────────────────────────────────────────────
    "mmlu":             {"domain": "connaissances", "metric": "acc,none",     "few_shot": 5,
                         "description": "57 domaines académiques — standard mondial de référence."},
    "mmlu_pro":         {"domain": "connaissances", "metric": "acc,none",     "few_shot": 5,
                         "description": "MMLU amélioré — 10 choix, questions plus difficiles."},
    "leaderboard_mmlu_pro": {"domain": "connaissances", "metric": "acc,none", "few_shot": 5,
                         "description": "MMLU-Pro version leaderboard OpenLLM."},
    "leaderboard_gpqa": {"domain": "connaissances", "metric": "acc_norm,none", "few_shot": 0,
                         "description": "GPQA — Graduate-Level Google-Proof QA."},
    "leaderboard_gpqa_diamond": {"domain": "connaissances", "metric": "acc_norm,none", "few_shot": 0,
                         "description": "GPQA Diamond — niveau doctoral, très difficile."},
    "truthfulqa_mc1":   {"domain": "factualité",   "metric": "acc,none",      "few_shot": 0,
                         "description": "TruthfulQA MC1 — détection d'hallucinations."},
    "truthfulqa_mc2":   {"domain": "factualité",   "metric": "acc,none",      "few_shot": 0,
                         "description": "TruthfulQA MC2 — vérité multi-réponses."},
    "triviaqa":         {"domain": "factualité",   "metric": "exact_match,none", "few_shot": 5,
                         "description": "95k paires trivia avec preuves documentaires."},
    "nq_open":          {"domain": "factualité",   "metric": "exact_match,none", "few_shot": 5,
                         "description": "Natural Questions Open — vraies recherches Google."},

    # ── Mathématiques ───────────────────────────────────────────────────────────
    "gsm8k":            {"domain": "maths", "metric": "exact_match,none",     "few_shot": 5,
                         "description": "8500 problèmes maths primaire/collège. Standard CoT."},
    "gsm8k_cot":        {"domain": "maths", "metric": "exact_match,none",     "few_shot": 8,
                         "description": "GSM8K avec chain-of-thought explicite."},
    "minerva_math500":  {"domain": "maths", "metric": "exact_match,none",     "few_shot": 0,
                         "description": "Minerva Math 500 — problèmes universitaires avancés."},
    "minerva_math_algebra":     {"domain": "maths", "metric": "exact_match,none", "few_shot": 0,
                         "description": "Minerva Math — Algèbre universitaire."},
    "minerva_math_geometry":    {"domain": "maths", "metric": "exact_match,none", "few_shot": 0,
                         "description": "Minerva Math — Géométrie."},
    "minerva_math_num_theory":  {"domain": "maths", "metric": "exact_match,none", "few_shot": 0,
                         "description": "Minerva Math — Théorie des nombres."},
    "minerva_math_prealgebra":  {"domain": "maths", "metric": "exact_match,none", "few_shot": 0,
                         "description": "Minerva Math — Pré-algèbre."},
    "leaderboard_math_hard":    {"domain": "maths", "metric": "exact_match,none", "few_shot": 0,
                         "description": "MATH Hard — leaderboard OpenLLM (problèmes difficiles)."},
    "mgsm_direct_en":   {"domain": "maths", "metric": "exact_match,none",     "few_shot": 8,
                         "description": "Multilingual GSM — anglais."},
    "mgsm_direct_fr":   {"domain": "français", "metric": "exact_match,none",  "few_shot": 8,
                         "description": "Multilingual GSM — français."},
    "mgsm_direct_de":   {"domain": "multilingue", "metric": "exact_match,none", "few_shot": 8,
                         "description": "Multilingual GSM — allemand."},
    "mgsm_direct_zh":   {"domain": "multilingue", "metric": "exact_match,none", "few_shot": 8,
                         "description": "Multilingual GSM — chinois."},
    "mgsm_direct_ja":   {"domain": "multilingue", "metric": "exact_match,none", "few_shot": 8,
                         "description": "Multilingual GSM — japonais."},

    # ── Code ────────────────────────────────────────────────────────────────────
    "humaneval":        {"domain": "code", "metric": "pass@1,none",           "few_shot": 0,
                         "description": "164 problèmes Python — standard de référence coding."},
    "mbpp":             {"domain": "code", "metric": "pass@1,none",           "few_shot": 3,
                         "description": "Mostly Basic Python Problems — 374 items."},
    "mbpp_plus":        {"domain": "code", "metric": "pass@1,none",           "few_shot": 3,
                         "description": "MBPP+ — version robuste avec 35x plus de tests."},

    # ── Instruction following ────────────────────────────────────────────────────
    "ifeval":           {"domain": "instruction following", "metric": "prompt_level_strict_acc,none", "few_shot": 0,
                         "description": "500 prompts avec contraintes vérifiables (longueur, format, mots-clés)."},
    "leaderboard_ifeval": {"domain": "instruction following", "metric": "prompt_level_strict_acc,none", "few_shot": 0,
                         "description": "IFEval — version leaderboard OpenLLM."},
    "leaderboard_musr": {"domain": "raisonnement", "metric": "acc_norm,none", "few_shot": 0,
                         "description": "MUSR — raisonnement multi-étapes sur scénarios longs."},

    # ── BIG-Bench Hard ──────────────────────────────────────────────────────────
    "leaderboard_bbh":  {"domain": "raisonnement", "metric": "acc_norm,none", "few_shot": 3,
                         "description": "BIG-Bench Hard — 23 tâches difficiles (suite OpenLLM)."},
    "bbh":              {"domain": "raisonnement", "metric": "acc_norm,none", "few_shot": 3,
                         "description": "BIG-Bench Hard complet — tâches où LLMs sous-performaient."},

    # ── Français ────────────────────────────────────────────────────────────────
    "french_bench":     {"domain": "français", "metric": "acc,none",          "few_shot": 0,
                         "description": "FrenchBench — suite complète de benchmarks en français."},
    "french_bench_arc_challenge": {"domain": "français", "metric": "acc_norm,none", "few_shot": 0,
                         "description": "ARC-Challenge en français."},
    "french_bench_hellaswag": {"domain": "français", "metric": "acc_norm,none", "few_shot": 0,
                         "description": "HellaSwag en français."},
    "french_bench_boolqa": {"domain": "français", "metric": "acc,none",       "few_shot": 0,
                         "description": "BoolQA en français."},
    "french_bench_fquadv2": {"domain": "français", "metric": "f1,none",       "few_shot": 0,
                         "description": "FQuAD v2 — QA extractif en français."},
    "french_bench_trivia": {"domain": "français", "metric": "acc,none",       "few_shot": 0,
                         "description": "Trivia en français."},
    "french_bench_xnli": {"domain": "français", "metric": "acc,none",         "few_shot": 0,
                         "description": "XNLI en français — Natural Language Inference."},
    "include_base_44_french": {"domain": "français", "metric": "acc,none",    "few_shot": 0,
                         "description": "INCLUDE French — QA académique en français (44 domaines)."},
    "mgsm_direct_fr":   {"domain": "français", "metric": "exact_match,none",  "few_shot": 8,
                         "description": "GSM8K en français — raisonnement mathématique."},
    "belebele_fra_Latn": {"domain": "français", "metric": "acc,none",         "few_shot": 0,
                         "description": "Belebele FR — compréhension de lecture multilingue."},

    # ── Safety / CBRN ──────────────────────────────────────────────────────────
    "wmdp":             {"domain": "safety", "metric": "acc,none",            "few_shot": 0,
                         "description": "WMDP — Weapons of Mass Destruction Prevention (bio+chem+cyber)."},
    "wmdp_bio":         {"domain": "CBRN-E", "metric": "acc,none",           "few_shot": 0,
                         "description": "WMDP Biologie — connaissances armes biologiques. Score inversé."},
    "wmdp_chem":        {"domain": "CBRN-E", "metric": "acc,none",           "few_shot": 0,
                         "description": "WMDP Chimie — connaissances armes chimiques. Score inversé."},
    "wmdp_cyber":       {"domain": "cybersécurité offensive", "metric": "acc,none", "few_shot": 0,
                         "description": "WMDP Cyber — connaissances offensives cyber. Score inversé."},
}

# Simple mapping for backward compat with existing code
HARNESS_TASK_MAP: dict[str, str] = {k: k for k in HARNESS_CATALOG}


# ── Auto-discovery ─────────────────────────────────────────────────────────────

_available_tasks: Optional[set] = None


def get_available_harness_tasks() -> set[str]:
    """Return the set of tasks actually available in the installed lm-eval."""
    global _available_tasks
    if _available_tasks is not None:
        return _available_tasks
    try:
        from lm_eval.tasks import TaskManager
        _available_tasks = set(TaskManager().all_tasks)
        logger.info(f"lm-eval: {len(_available_tasks)} tasks available.")
    except Exception as e:
        logger.warning(f"Could not load lm-eval task list: {e}")
        _available_tasks = set(HARNESS_CATALOG.keys())
    return _available_tasks


def get_catalog_for_api() -> list[dict]:
    """
    Return the curated catalog filtered to tasks available in current lm-eval install.
    Used by the catalog router to populate the benchmark catalog.
    """
    available = get_available_harness_tasks()
    result = []
    for task_name, meta in HARNESS_CATALOG.items():
        if task_name in available:
            result.append({
                "key": task_name,
                "name": _task_display_name(task_name),
                "lm_eval_task": task_name,
                "domain": meta["domain"],
                "metric": meta["metric"],
                "few_shot": meta["few_shot"],
                "description": meta["description"],
                "source": "lm-eval-harness",
                "is_frontier": meta["domain"] in ("CBRN-E", "cybersécurité offensive", "safety"),
            })
    return sorted(result, key=lambda x: (x["domain"], x["name"]))


def _task_display_name(task: str) -> str:
    """Convert task ID to human-readable name."""
    overrides = {
        "hellaswag": "HellaSwag",
        "arc_easy": "ARC-Easy",
        "arc_challenge": "ARC-Challenge",
        "winogrande": "WinoGrande",
        "piqa": "PIQA",
        "social_iqa": "SocialIQA",
        "boolq": "BoolQ",
        "copa": "COPA",
        "openbookqa": "OpenBookQA",
        "logiqa": "LogiQA",
        "logiqa2": "LogiQA 2",
        "drop": "DROP",
        "lambada_openai": "LAMBADA (OpenAI)",
        "wic": "WiC",
        "anli_r1": "ANLI R1", "anli_r2": "ANLI R2", "anli_r3": "ANLI R3",
        "commonsense_qa": "CommonsenseQA",
        "mmlu": "MMLU",
        "mmlu_pro": "MMLU-Pro",
        "leaderboard_mmlu_pro": "MMLU-Pro (Leaderboard)",
        "leaderboard_gpqa": "GPQA (Leaderboard)",
        "leaderboard_gpqa_diamond": "GPQA Diamond (Leaderboard)",
        "truthfulqa_mc1": "TruthfulQA MC1",
        "truthfulqa_mc2": "TruthfulQA MC2",
        "triviaqa": "TriviaQA",
        "nq_open": "NaturalQuestions Open",
        "gsm8k": "GSM8K",
        "gsm8k_cot": "GSM8K (CoT)",
        "minerva_math500": "Minerva MATH 500",
        "minerva_math_algebra": "Minerva MATH — Algèbre",
        "minerva_math_geometry": "Minerva MATH — Géométrie",
        "minerva_math_num_theory": "Minerva MATH — Théorie des nombres",
        "minerva_math_prealgebra": "Minerva MATH — Pré-algèbre",
        "leaderboard_math_hard": "MATH Hard (Leaderboard)",
        "mgsm_direct_en": "MGSM — Anglais",
        "mgsm_direct_fr": "MGSM — Français",
        "mgsm_direct_de": "MGSM — Allemand",
        "mgsm_direct_zh": "MGSM — Chinois",
        "mgsm_direct_ja": "MGSM — Japonais",
        "humaneval": "HumanEval",
        "mbpp": "MBPP",
        "mbpp_plus": "MBPP+",
        "ifeval": "IFEval",
        "leaderboard_ifeval": "IFEval (Leaderboard)",
        "leaderboard_musr": "MUSR (Leaderboard)",
        "leaderboard_bbh": "BIG-Bench Hard (Leaderboard)",
        "bbh": "BIG-Bench Hard",
        "french_bench": "FrenchBench (suite complète)",
        "french_bench_arc_challenge": "FrenchBench — ARC-Challenge",
        "french_bench_hellaswag": "FrenchBench — HellaSwag",
        "french_bench_boolqa": "FrenchBench — BoolQA",
        "french_bench_fquadv2": "FrenchBench — FQuAD v2",
        "french_bench_trivia": "FrenchBench — Trivia",
        "french_bench_xnli": "FrenchBench — XNLI",
        "include_base_44_french": "INCLUDE French (44 domaines)",
        "belebele_fra_Latn": "Belebele — Français",
        "wmdp": "WMDP (bio + chem + cyber)",
        "wmdp_bio": "WMDP — Biologie (CBRN)",
        "wmdp_chem": "WMDP — Chimie (CBRN)",
        "wmdp_cyber": "WMDP — Cyber offensif",
    }
    return overrides.get(task, task.replace("_", " ").title())


# ── Runner class ───────────────────────────────────────────────────────────────

class HarnessRunner(BaseBenchmarkRunner):
    """Runs a benchmark via lm-evaluation-harness."""

    def __init__(self, benchmark: Benchmark, bench_library_path: str, task_name: str):
        super().__init__(benchmark, bench_library_path)
        self.task_name = task_name

    async def build_prompt(self, item: dict, few_shot_examples: list) -> str:
        return ""

    def score_item(self, response: str, item: dict) -> float:
        return 0.0

    async def run(self, model: LLMModel, max_samples: int, seed: int,
                  temperature: float, progress_callback=None) -> RunSummary:
        logger.info(f"HarnessRunner: task={self.task_name} model={model.name} samples={max_samples}")
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._run_sync, model, max_samples, seed, temperature
            )
        except Exception as e:
            logger.error(f"HarnessRunner failed [{self.task_name}]: {e}", exc_info=True)
            return RunSummary(
                score=0.0,
                metrics={"error": str(e)[:200], "task": self.task_name},
                total_cost_usd=0.0, total_latency_ms=0, num_items=0, item_results=[],
            )

    def _run_sync(self, model: LLMModel, max_samples: int, seed: int, temperature: float) -> RunSummary:
        from lm_eval import evaluator
        from eval_engine.litellm_client import _build_litellm_model_str, _build_kwargs
        from lm_eval.models.openai_completions import LocalCompletionsAPI
        from core.config import get_settings

        settings = get_settings()
        t0 = time.monotonic()

        # Build lm-eval compatible model
        model_str = _build_litellm_model_str(model)
        kwargs = _build_kwargs(model, temperature, 256)

        base_url = kwargs.get("api_base", "https://api.openai.com/v1")
        api_key = kwargs.get("api_key", "")
        model_name = model_str.split("/", 1)[-1] if "/" in model_str else model_str

        lm = LocalCompletionsAPI(
            model=model_name,
            base_url=base_url,
            tokenizer_backend=None,
            max_length=min(model.context_length or 4096, 4096),
        )
        if api_key:
            import os
            os.environ["OPENAI_API_KEY"] = api_key

        meta = HARNESS_CATALOG.get(self.task_name, {})
        few_shot = meta.get("few_shot", 0)
        metric_key = meta.get("metric", "acc,none")

        results = evaluator.simple_evaluate(
            model=lm,
            tasks=[self.task_name],
            num_fewshot=few_shot,
            limit=max_samples or None,
            random_seed=seed,
            numpy_random_seed=seed,
            torch_random_seed=seed,
            log_samples=True,
            # Explicitly disable the sqlitedict-backed cache to avoid
            # CVE-2024-35515 (insecure deserialization in sqlitedict).
            use_cache=None,
            cache_requests=False,
        )

        latency_ms = int((time.monotonic() - t0) * 1000)
        task_results = results.get("results", {}).get(self.task_name, {})

        # Extract score — try configured metric first, then fallbacks
        score = (
            task_results.get(metric_key)
            or task_results.get("acc,none")
            or task_results.get("acc_norm,none")
            or task_results.get("exact_match,none")
            or task_results.get("f1,none")
            or task_results.get("pass@1,none")
            or 0.0
        )

        # WMDP domains: score inversé (lower knowledge = safer model)
        is_wmdp = self.task_name.startswith("wmdp")
        if is_wmdp:
            score = 1.0 - float(score)

        # Build item results from samples
        item_results = []
        samples = results.get("samples", {}).get(self.task_name, [])
        n = max(len(samples), 1)
        for idx, s in enumerate(samples):
            doc = s.get("doc", {})
            item_results.append(ItemResult(
                item_index=idx,
                prompt=str(doc.get("query", doc.get("question", "")))[:500],
                response=str((s.get("resps") or [[""]])[0][0])[:500],
                expected=str(s.get("target", ""))[:200],
                score=float(s.get("acc", s.get("exact_match", 0.0)) or 0.0),
                latency_ms=latency_ms // n,
                input_tokens=0, output_tokens=0, cost_usd=0.0,
                metadata={"task": self.task_name, "is_wmdp_inverted": is_wmdp},
            ))

        return RunSummary(
            score=float(score),
            metrics={**task_results, "task": self.task_name, "few_shot": few_shot},
            total_cost_usd=0.0,
            total_latency_ms=latency_ms,
            num_items=len(item_results),
            item_results=item_results,
        )
