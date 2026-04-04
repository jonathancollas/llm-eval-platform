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

# Fallback starter pack if OpenRouter unreachable
STARTER_MODELS = [
    {"name": "Llama 3.3 70B (free)",   "model_id": "meta-llama/llama-3.3-70b-instruct:free", "ctx": 65536,  "in": 0.0,    "out": 0.0},
    {"name": "Llama 3.2 3B (free)",    "model_id": "meta-llama/llama-3.2-3b-instruct:free",  "ctx": 131072, "in": 0.0,    "out": 0.0},
    {"name": "Gemma 3 27B (free)",     "model_id": "google/gemma-3-27b-it:free",              "ctx": 131072, "in": 0.0,    "out": 0.0},
    {"name": "Gemma 3 12B (free)",     "model_id": "google/gemma-3-12b-it:free",              "ctx": 32768,  "in": 0.0,    "out": 0.0},
    {"name": "Mistral 7B Instruct",    "model_id": "mistralai/mistral-7b-instruct-v0.1",      "ctx": 2824,   "in": 0.0001, "out": 0.0002},
    {"name": "Qwen3 8B",               "model_id": "qwen/qwen3-8b",                           "ctx": 40960,  "in": 0.0,    "out": 0.0004},
    {"name": "Hermes 3 405B (free)",   "model_id": "nousresearch/hermes-3-llama-3.1-405b:free","ctx": 131072, "in": 0.0,    "out": 0.0},
    {"name": "DeepSeek V3",            "model_id": "deepseek/deepseek-chat",                  "ctx": 163840, "in": 0.0003, "out": 0.0009},
]


class SyncResult(BaseModel):
    benchmarks_added: int
    models_added: int
    total_benchmarks: int
    total_models: int
    openrouter_synced: bool


def _build_model(m: dict) -> LLMModel | None:
    """Convert an OpenRouter API model dict to an LLMModel."""
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
    )


@router.post("/startup", response_model=SyncResult)
async def startup_sync(session: Session = Depends(get_session)):
    """
    Auto-import at startup:
    - All missing benchmarks from catalog
    - All OpenRouter models (if API key configured), else starter pack
    """

    # ── Benchmarks ────────────────────────────────────────────────────────────
    local_bench_names = {b.name for b in session.exec(select(Benchmark)).all()}
    benches_added = 0
    for item in BENCHMARK_CATALOG:
        if item["name"] not in local_bench_names:
            b = Benchmark(
                name=item["name"],
                type=BenchmarkType(item["type"]),
                description=item.get("description", ""),
                tags=json.dumps(item.get("tags", [])),
                dataset_path=item.get("dataset_path", ""),
                metric=item.get("metric", "accuracy"),
                num_samples=item.get("num_samples"),
                config_json=json.dumps(item.get("config", {})),
                risk_threshold=item.get("risk_threshold"),
                is_builtin=True,
            )
            session.add(b)
            benches_added += 1

    # ── Models ────────────────────────────────────────────────────────────────
    local_model_ids = {m.model_id for m in session.exec(select(LLMModel)).all()}
    models_added = 0
    openrouter_synced = False

    api_key = getattr(settings, "openrouter_api_key", "")

    if api_key:
        # Fetch full OpenRouter catalog
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(OPENROUTER_MODELS_URL, headers=headers)
                resp.raise_for_status()
                raw_models = resp.json().get("data", [])

            for raw in raw_models:
                model = _build_model(raw)
                if model and model.model_id not in local_model_ids:
                    session.add(model)
                    local_model_ids.add(model.model_id)
                    models_added += 1

            openrouter_synced = True
            logger.info(f"OpenRouter sync: +{models_added} models imported")

        except Exception as e:
            logger.warning(f"OpenRouter sync failed, falling back to starter pack: {e}")
            # Fall through to starter pack below

    if not openrouter_synced:
        # Fallback: import starter pack
        for m in STARTER_MODELS:
            if m["model_id"] not in local_model_ids:
                model = LLMModel(
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
                )
                session.add(model)
                models_added += 1

    session.commit()

    total_benches = len(session.exec(select(Benchmark)).all())
    total_models  = len(session.exec(select(LLMModel)).all())

    return SyncResult(
        benchmarks_added=benches_added,
        models_added=models_added,
        total_benchmarks=total_benches,
        total_models=total_models,
        openrouter_synced=openrouter_synced,
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
    local_names = {b.name for b in session.exec(select(Benchmark)).all()}
    added = 0
    for item in BENCHMARK_CATALOG:
        if item["name"] not in local_names:
            b = Benchmark(
                name=item["name"],
                type=BenchmarkType(item["type"]),
                description=item.get("description", ""),
                tags=json.dumps(item.get("tags", [])),
                dataset_path=item.get("dataset_path", ""),
                metric=item.get("metric", "accuracy"),
                num_samples=item.get("num_samples"),
                config_json=json.dumps(item.get("config", {})),
                risk_threshold=item.get("risk_threshold"),
                is_builtin=True,
            )
            session.add(b)
            added += 1
    session.commit()
    return {"added": added}
