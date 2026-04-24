"""
Campaign builder — turns extracted NL slots into a CampaignCreate preview.

The builder is intentionally conservative:
  * It NEVER POSTs to /campaigns itself. It only produces a preview dict
    shaped exactly like CampaignCreate. The user confirms and the frontend
    submits to the canonical endpoint.
  * It asks for disambiguation (via LaunchPayload.clarification) whenever
    a slot is ambiguous — multiple model matches with close scores, no
    benchmark match at all, etc.
  * Cost and time estimates are best-effort. The platform is honest: the
    UI labels these as estimates, not guarantees.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlmodel import Session

from core.models import LLMModel, Benchmark
from eval_engine.search.resolvers import resolve_model, resolve_benchmark
from eval_engine.search.schema import LaunchPayload, LaunchPreview, LaunchSlots


DEFAULT_AVERAGE_INPUT_TOKENS = 800
DEFAULT_AVERAGE_OUTPUT_TOKENS = 300
# Conservative default when we cannot estimate cost at all (free / Ollama).
MINIMUM_DISPLAY_COST_USD = 0.0


def build_launch_preview(
    session: Session,
    slots: dict,
) -> LaunchPayload:
    """
    Build a CampaignCreate preview from classifier slots.

    Input slots (coming from either deterministic or LLM classifier):
        model_names: list[str]       (optional)
        model_name:  str             (optional, single)
        benchmark_names: list[str]   (optional)
        max_samples: int             (optional)
        autonomy_level: "L1".."L5"   (optional)
        temperature: float           (optional)
    """
    clarifications: list[str] = []

    # ── Resolve model ────────────────────────────────────────────────
    model_query_list: list[str] = []
    if "model_names" in slots and isinstance(slots["model_names"], list):
        model_query_list = [str(m) for m in slots["model_names"] if m]
    elif "model_name" in slots and slots["model_name"]:
        model_query_list = [str(slots["model_name"])]

    resolved_models: list[LLMModel] = []
    for q in model_query_list:
        matches = resolve_model(session, q, limit=3)
        if not matches:
            clarifications.append(
                f"No model matched '{q}'. Pick from /models."
            )
            continue
        top = matches[0]
        # If top score is < 0.75 or a runner-up is within 0.05, ask user to pick.
        if top.score < 0.75 or (
            len(matches) > 1 and matches[1].score >= top.score - 0.05
        ):
            options = ", ".join(m.name for m in matches[:3])
            clarifications.append(
                f"Ambiguous model '{q}'. Candidates: {options}."
            )
            continue
        full = session.get(LLMModel, top.id)
        if full:
            resolved_models.append(full)

    # ── Resolve benchmarks ───────────────────────────────────────────
    bench_query_list: list[str] = []
    if "benchmark_names" in slots and isinstance(slots["benchmark_names"], list):
        bench_query_list = [str(b) for b in slots["benchmark_names"] if b]
    elif "benchmark_name" in slots and slots["benchmark_name"]:
        bench_query_list = [str(slots["benchmark_name"])]

    resolved_benchmarks: list[Benchmark] = []
    for q in bench_query_list:
        matches = resolve_benchmark(session, q, limit=3)
        if not matches:
            clarifications.append(
                f"No benchmark matched '{q}'. Browse /benchmarks."
            )
            continue
        top = matches[0]
        if top.score < 0.65:
            options = ", ".join(m.name for m in matches[:3])
            clarifications.append(
                f"Uncertain benchmark '{q}'. Closest: {options}."
            )
            continue
        full = session.get(Benchmark, top.id)
        if full:
            resolved_benchmarks.append(full)

    # ── Other slots ──────────────────────────────────────────────────
    max_samples = int(slots.get("max_samples") or 50)
    max_samples = max(1, min(10000, max_samples))

    autonomy_level_raw = str(slots.get("autonomy_level") or "L2").upper()
    if autonomy_level_raw not in {"L1", "L2", "L3", "L4", "L5"}:
        autonomy_level_raw = "L2"
    autonomy_level = autonomy_level_raw

    try:
        temperature = float(slots.get("temperature", 0.0))
    except (TypeError, ValueError):
        temperature = 0.0
    temperature = max(0.0, min(2.0, temperature))

    launch_slots = LaunchSlots(
        model_id=resolved_models[0].id if resolved_models else None,
        model_name=resolved_models[0].name if resolved_models else None,
        benchmark_ids=[b.id for b in resolved_benchmarks],
        benchmark_names=[b.name for b in resolved_benchmarks],
        max_samples=max_samples,
        autonomy_level=autonomy_level,
        temperature=temperature,
    )

    # If required slots are missing we cannot build a preview — let the UI
    # ask the user to complete.
    if not resolved_models or not resolved_benchmarks:
        if not resolved_models:
            clarifications.append("Select at least one model.")
        if not resolved_benchmarks:
            clarifications.append("Select at least one benchmark.")
        return LaunchPayload(
            slots=launch_slots,
            preview=None,
            clarification="; ".join(clarifications) or None,
        )

    # ── Cost estimate ────────────────────────────────────────────────
    # Sum across models × benchmarks × max_samples, using published per-1k rates.
    total_cost = 0.0
    for model in resolved_models:
        in_cost = (model.cost_input_per_1k or 0.0) * (DEFAULT_AVERAGE_INPUT_TOKENS / 1000.0)
        out_cost = (model.cost_output_per_1k or 0.0) * (DEFAULT_AVERAGE_OUTPUT_TOKENS / 1000.0)
        per_sample = in_cost + out_cost
        total_cost += per_sample * max_samples * len(resolved_benchmarks)
    total_cost = max(MINIMUM_DISPLAY_COST_USD, total_cost)

    # ── Time estimate ────────────────────────────────────────────────
    # Empirical conservative estimate: 2s per sample for small models,
    # 6s for big. We lack a reliable signal — use a flat 4s/sample across
    # models until we log real throughput.
    estimated_time_min = (4.0 * max_samples * len(resolved_benchmarks) * len(resolved_models)) / 60.0

    name = (
        f"{resolved_models[0].name} × {resolved_benchmarks[0].name}"
        f"{'+' + str(len(resolved_benchmarks) - 1) if len(resolved_benchmarks) > 1 else ''}"
        f" · search"
    )

    run_context = {
        "autonomy_level": autonomy_level,
        "source": "search_nl",
    }

    preview = LaunchPreview(
        name=name[:200],
        description="Built from natural-language query via the search bar.",
        model_ids=[m.id for m in resolved_models],
        benchmark_ids=[b.id for b in resolved_benchmarks],
        max_samples=max_samples,
        temperature=temperature,
        run_context_json=json.dumps(run_context),
        estimated_cost_usd=round(total_cost, 4),
        estimated_time_minutes=round(estimated_time_min, 2),
        needs_confirmation=clarifications,
    )

    return LaunchPayload(
        slots=launch_slots,
        preview=preview,
        clarification="; ".join(clarifications) or None,
    )
