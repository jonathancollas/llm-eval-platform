"""
Sync — auto-imports benchmarks + all OpenRouter models at startup.
"""
import json
import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select
import httpx

from core.database import get_session
from core.config import get_settings
from core.models import Benchmark, BenchmarkType, LLMModel, ModelProvider
from api.routers.catalog import BENCHMARK_CATALOG

router = APIRouter(prefix="/sync", tags=["sync"])
logger = logging.getLogger(__name__)
settings = get_settings()

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

OPEN_SOURCE_PROVIDERS = {
    "meta-llama", "mistralai", "google", "microsoft", "qwen", "deepseek",
    "01-ai", "openchat", "teknium", "cognitivecomputations", "nousresearch",
    "phind", "wizardlm", "allenai", "tiiuae", "bigcode", "eleutherai",
    "huggingfaceh4", "stabilityai",
}

# Only models with :free suffix are truly free on OpenRouter (no credits needed)
STARTER_MODELS = [
    {"name": "Llama 3.3 70B (free)",   "model_id": "meta-llama/llama-3.3-70b-instruct:free", "ctx": 65536,  "in": 0.0, "out": 0.0},
    {"name": "Llama 3.2 3B (free)",    "model_id": "meta-llama/llama-3.2-3b-instruct:free",  "ctx": 131072, "in": 0.0, "out": 0.0},
    {"name": "Gemma 3 27B (free)",     "model_id": "google/gemma-3-27b-it:free",              "ctx": 131072, "in": 0.0, "out": 0.0},
    {"name": "Gemma 3 12B (free)",     "model_id": "google/gemma-3-12b-it:free",              "ctx": 32768,  "in": 0.0, "out": 0.0},
    {"name": "Gemma 2 9B (free)",      "model_id": "google/gemma-2-9b-it:free",               "ctx": 8192,   "in": 0.0, "out": 0.0},
    {"name": "Hermes 3 405B (free)",   "model_id": "nousresearch/hermes-3-llama-3.1-405b:free","ctx": 131072,"in": 0.0, "out": 0.0},
    {"name": "Mistral 7B (free)",      "model_id": "mistralai/mistral-7b-instruct:free",      "ctx": 32768,  "in": 0.0, "out": 0.0},
    {"name": "Qwen 2.5 7B (free)",     "model_id": "qwen/qwen-2.5-7b-instruct:free",          "ctx": 32768,  "in": 0.0, "out": 0.0},
]


class SyncResult(BaseModel):
    benchmarks_added: int
    models_added: int
    total_benchmarks: int
    total_models: int
    openrouter_synced: bool


# ── Reusable sync functions (called from lifespan AND from API routes) ─────────

def sync_benchmarks_from_catalog(session: Session) -> int:
    """
    Import all catalog benchmarks missing from DB.
    Synchronous — no network calls.
    Returns number of benchmarks added.
    """
    from pathlib import Path
    bench_path = Path(settings.bench_library_path)
    local_names = {b.name for b in session.exec(select(Benchmark)).all()}
    added = 0
    for item in BENCHMARK_CATALOG:
        if item["name"] not in local_names:
            dataset_path = item.get("dataset_path", "")
            has_dataset = bool(dataset_path and (bench_path / dataset_path).exists())
            b = Benchmark(
                name=item["name"],
                type=BenchmarkType(item["type"]),
                description=item.get("description", ""),
                tags=json.dumps(item.get("tags", [])),
                dataset_path=dataset_path,
                metric=item.get("metric", "accuracy"),
                num_samples=item.get("num_samples"),
                config_json=json.dumps(item.get("config", {})),
                risk_threshold=item.get("risk_threshold"),
                is_builtin=True,
                has_dataset=has_dataset,
            )
            session.add(b)
            added += 1
    if added:
        session.commit()
        logger.info(f"Synced {added} benchmarks from catalog.")
    return added


def sync_starter_models(session: Session) -> int:
    """Import the starter pack of free models. Synchronous — no network."""
    local_ids = {m.model_id for m in session.exec(select(LLMModel)).all()}
    added = 0
    for m in STARTER_MODELS:
        if m["model_id"] not in local_ids:
            session.add(LLMModel(
                name=m["name"],
                provider=ModelProvider.CUSTOM,
                model_id=m["model_id"],
                endpoint=OPENROUTER_ENDPOINT,
                context_length=m["ctx"],
                cost_input_per_1k=m["in"],
                cost_output_per_1k=m["out"],
                tags=json.dumps(["gratuit" if m["in"] == 0 else "open-source"]),
                notes="Via OpenRouter (starter pack)",
                is_active=True,
            ))
            added += 1
    if added:
        session.commit()
    return added


async def sync_openrouter_models(session: Session) -> tuple[int, bool]:
    """
    Fetch full OpenRouter catalog and import missing models.
    Async — makes HTTP call.
    Returns (models_added, openrouter_synced).
    """
    api_key = settings.openrouter_api_key
    if not api_key:
        logger.info("No OPENROUTER_API_KEY — importing starter pack only.")
        added = sync_starter_models(session)
        return added, False

    local_ids = {m.model_id for m in session.exec(select(LLMModel)).all()}
    added = 0
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(OPENROUTER_MODELS_URL, headers=headers)
            resp.raise_for_status()
            raw_models = resp.json().get("data", [])

        for raw in raw_models:
            model = _build_model(raw)
            if model and model.model_id not in local_ids:
                session.add(model)
                local_ids.add(model.model_id)
                added += 1

        session.commit()
        logger.info(f"OpenRouter sync: +{added} models imported.")
        return added, True

    except Exception as e:
        logger.warning(f"OpenRouter sync failed: {e} — importing starter pack.")
        added = sync_starter_models(session)
        return added, False


def _build_model(m: dict) -> LLMModel | None:
    model_id = m.get("id", "")
    name = m.get("name", model_id)
    if not model_id or not name:
        return None

    pricing = m.get("pricing", {})
    try:
        cost_in  = float(pricing.get("prompt", 0)) * 1000
        cost_out = float(pricing.get("completion", 0)) * 1000
    except (TypeError, ValueError):
        cost_in = cost_out = 0.0

    ctx = int(m.get("context_length", 4096) or 4096)
    is_oss = any(p in model_id.lower() for p in OPEN_SOURCE_PROVIDERS)

    tags = []
    if cost_in == 0 and cost_out == 0: tags.append("gratuit")
    if is_oss:                          tags.append("open-source")
    if ctx >= 100_000:                  tags.append("long-context")
    if "instruct" in model_id.lower(): tags.append("instruct")
    if "code" in model_id.lower() or "coder" in model_id.lower(): tags.append("code")
    if any(x in model_id.lower() for x in ["70b", "72b", "405b"]): tags.append("70B+")
    elif any(x in model_id.lower() for x in ["7b", "8b", "6b"]):   tags.append("7-8B")
    elif any(x in model_id.lower() for x in ["3b", "2b", "1b"]):   tags.append("≤3B")

    desc = (m.get("description", "") or "")[:200]
    modalities = m.get("architecture", {}).get("modality", "") or ""
    supported_params = m.get("supported_parameters") or []
    supports_vision = "image" in str(modalities).lower()
    supports_tools = any("tool" in str(p).lower() or "function" in str(p).lower()
                         for p in supported_params)
    supports_reasoning = any("reasoning" in str(p).lower()
                              or "think" in model_id.lower()
                              or "r1" in model_id.lower()
                              or "qwq" in model_id.lower()
                              for p in supported_params)

    return LLMModel(
        name=name,
        provider=ModelProvider.CUSTOM,
        model_id=model_id,
        endpoint=OPENROUTER_ENDPOINT,
        context_length=ctx,
        cost_input_per_1k=round(cost_in, 6),
        cost_output_per_1k=round(cost_out, 6),
        tags=json.dumps(tags),
        notes=f"Via OpenRouter. {desc}",
        is_active=True,
        supports_vision=supports_vision,
        supports_tools=supports_tools,
        supports_reasoning=supports_reasoning,
    )


# ── API routes ─────────────────────────────────────────────────────────────────

@router.post("/startup", response_model=SyncResult)
async def startup_sync(session: Session = Depends(get_session)):
    """Called by frontend once per session (cached 15min in localStorage)."""
    benches_added = sync_benchmarks_from_catalog(session)
    models_added, or_synced = await sync_openrouter_models(session)

    total_benches = len(session.exec(select(Benchmark)).all())
    total_models  = len(session.exec(select(LLMModel)).all())

    return SyncResult(
        benchmarks_added=benches_added,
        models_added=models_added,
        total_benchmarks=total_benches,
        total_models=total_models,
        openrouter_synced=or_synced,
    )


@router.get("/benchmarks")
def sync_benchmarks_check(session: Session = Depends(get_session)):
    local_names = {b.name for b in session.exec(select(Benchmark)).all()}
    new_items = [i for i in BENCHMARK_CATALOG if i["name"] not in local_names]
    return {
        "new_count": len(new_items),
        "new_benchmarks": new_items,
        "total_catalog": len(BENCHMARK_CATALOG),
        "total_local": len(local_names),
    }


@router.post("/benchmarks/import-all")
def import_all_benchmarks(session: Session = Depends(get_session)):
    added = sync_benchmarks_from_catalog(session)
    return {"added": added}
