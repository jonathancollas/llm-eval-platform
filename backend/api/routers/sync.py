"""
Sync — auto-imports benchmarks + all OpenRouter models at startup.

Startup sync runs as a background task so it never blocks the API.
Frontend polls GET /sync/startup/status to know when it's done.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlmodel import Session, select
import httpx

from core.database import get_session, engine
from core.config import get_settings
from core.models import Benchmark, BenchmarkType, LLMModel, ModelProvider
from api.routers.catalog import BENCHMARK_CATALOG

router = APIRouter(prefix="/sync", tags=["sync"])
logger = logging.getLogger(__name__)
settings = get_settings()

# ── Startup sync state (in-process, survives across requests) ─────────────────
_sync_state: dict = {
    "status": "idle",          # idle | running | done | error
    "started_at": None,
    "finished_at": None,
    "benchmarks_added": 0,
    "models_added": 0,
    "total_benchmarks": 0,
    "total_models": 0,
    "openrouter_synced": False,
    "error": None,
}
_sync_lock = asyncio.Lock()

# ── Ollama circuit breaker — avoids 5s wait on every request ─────────────────
_ollama_available: Optional[bool] = None
_ollama_last_check: Optional[datetime] = None
OLLAMA_TIMEOUT = 2.0        # seconds — was 5.0, now aggressive
OLLAMA_CACHE_TTL = 30.0     # seconds between re-checks

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_TIMEOUT = 8.0    # seconds — was 20.0, background task so can be lower

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


class StartupStatus(BaseModel):
    status: str            # idle | running | done | error
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    benchmarks_added: int = 0
    models_added: int = 0
    total_benchmarks: int = 0
    total_models: int = 0
    openrouter_synced: bool = False
    error: Optional[str] = None


# ── Reusable sync functions (called from lifespan AND from API routes) ─────────

def sync_benchmarks_from_catalog(session: Session) -> int:
    """
    Import all catalog benchmarks missing from DB.
    Safe against duplicate inserts at startup.
    """
    from pathlib import Path
    from sqlalchemy.exc import IntegrityError

    bench_path = Path(settings.bench_library_path)
    added = 0

    for item in BENCHMARK_CATALOG:
        existing = session.exec(
            select(Benchmark).where(Benchmark.name == item["name"])
        ).first()

        if existing:
            continue

        dataset_path = item.get("dataset_path", "")
        has_dataset = bool(
            dataset_path and (bench_path / dataset_path).exists()
        )

        benchmark = Benchmark(
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
            source=item.get("source", "public"),
        )

        session.add(benchmark)

        try:
            session.commit()
            added += 1
        except IntegrityError:
            session.rollback()
            logger.info(f"Benchmark already exists: {item['name']}")

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
    Async — makes HTTP call. Called from background task, never from a route handler.
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
        async with httpx.AsyncClient(timeout=OPENROUTER_TIMEOUT) as client:
            resp = await client.get(OPENROUTER_MODELS_URL, headers=headers)
            resp.raise_for_status()
            raw_models = resp.json().get("data", [])

        for raw in raw_models:
            model = _build_model(raw)
            if model and model.model_id not in local_ids:
                session.add(model)
                local_ids.add(model.model_id)
                added += 1

        try:
            session.commit()
        except Exception as commit_err:
            # Race condition: another sync ran concurrently — rollback and re-check
            session.rollback()
            logger.warning(f"OpenRouter bulk insert conflict (concurrent sync?): {commit_err}")
            # Re-insert one by one, skipping existing
            already = {m.model_id for m in session.exec(select(LLMModel)).all()}
            added = 0
            for raw in raw_models:
                model = _build_model(raw)
                if model and model.model_id not in already:
                    try:
                        session.add(model)
                        session.commit()
                        already.add(model.model_id)
                        added += 1
                    except Exception:
                        session.rollback()

        logger.info(f"OpenRouter sync: +{added} models imported.")
        return added, True

    except Exception as e:
        logger.warning(f"OpenRouter sync failed: {e} — importing starter pack.")
        added = sync_starter_models(session)
        return added, False


async def _run_startup_sync_task() -> None:
    """
    Background task: runs benchmarks + OpenRouter sync without blocking any request.
    Uses its own DB session (not the request-scoped one which would be closed).
    Idempotent: won't re-run if already done or running.
    """
    global _sync_state
    async with _sync_lock:
        if _sync_state["status"] in ("running", "done"):
            return
        _sync_state["status"] = "running"
        _sync_state["started_at"] = datetime.utcnow().isoformat()

    try:
        # Open a fresh session — request session is already closed by this point
        with Session(engine) as session:
            benches_added = sync_benchmarks_from_catalog(session)

            try:
                models_added, or_synced = await asyncio.wait_for(
                    sync_openrouter_models(session),
                    timeout=OPENROUTER_TIMEOUT + 2,
                )
            except asyncio.TimeoutError:
                logger.warning("[startup] OpenRouter sync timed out — starter pack used.")
                models_added = sync_starter_models(session)
                or_synced = False

            total_benches = len(session.exec(select(Benchmark)).all())
            total_models = len(session.exec(select(LLMModel)).all())

        _sync_state.update({
            "status": "done",
            "finished_at": datetime.utcnow().isoformat(),
            "benchmarks_added": benches_added,
            "models_added": models_added,
            "total_benchmarks": total_benches,
            "total_models": total_models,
            "openrouter_synced": or_synced,
            "error": None,
        })
        logger.info(f"[startup] Sync done — {benches_added} benchmarks, {models_added} models.")

    except Exception as e:
        logger.error(f"[startup] Sync failed: {e}")
        _sync_state.update({
            "status": "error",
            "finished_at": datetime.utcnow().isoformat(),
            "error": str(e),
        })


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

    # Extended metadata
    top_provider = m.get("top_provider") or {}
    arch = m.get("architecture") or {}
    max_output = int(top_provider.get("max_completion_tokens") or 0)
    is_moderated = bool(top_provider.get("is_moderated", False))
    tokenizer = arch.get("tokenizer") or ""
    instruct_type = arch.get("instruct_type") or ""
    hf_id = m.get("hugging_face_id") or ""
    created_at = int(m.get("created") or 0)
    is_free = (cost_in == 0.0 and cost_out == 0.0 and ":free" in model_id)

    # Detect open-weight models (weights publicly downloadable)
    OPEN_WEIGHT_PREFIXES = [
        "meta-llama/", "google/gemma", "mistralai/mistral-", "mistralai/mixtral",
        "mistralai/mistral-small", "qwen/", "deepseek/", "microsoft/phi",
        "01-ai/", "allenai/", "stabilityai/", "tiiuae/", "nvidia/",
        "databricks/", "internlm/", "cohere/command-r",  # Command-R is open
    ]
    is_open_weight = bool(hf_id) or any(model_id.startswith(p) for p in OPEN_WEIGHT_PREFIXES)

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
        is_free=is_free,
        is_open_weight=is_open_weight,
        max_output_tokens=max_output,
        is_moderated=is_moderated,
        tokenizer=tokenizer,
        instruct_type=instruct_type,
        hugging_face_id=hf_id,
        model_created_at=created_at,
    )


# ── API routes ─────────────────────────────────────────────────────────────────

@router.post("/startup")
async def startup_sync(background_tasks: BackgroundTasks):
    """
    Triggers the startup sync in the background and returns immediately (<5ms).
    Frontend polls GET /sync/startup/status to track progress.
    Idempotent: safe to call multiple times — only runs once.
    """
    if _sync_state["status"] == "idle":
        background_tasks.add_task(_run_startup_sync_task)
    return {"status": _sync_state["status"], "message": "Sync dispatched to background"}


@router.get("/startup/status", response_model=StartupStatus)
async def startup_status():
    """Poll this to know when background sync completed."""
    return StartupStatus(**_sync_state)


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


# ── Ollama Local Models ────────────────────────────────────────────────────────

async def _ollama_fetch_tags() -> tuple[bool, list]:
    """
    Circuit-breaker wrapper for GET /api/tags.
    - Timeout: OLLAMA_TIMEOUT (2s) — was 5s
    - Caches availability for OLLAMA_CACHE_TTL (30s) to avoid hammering
    - Returns (available, models_list)
    """
    global _ollama_available, _ollama_last_check
    now = datetime.utcnow()

    # Cache hit: Ollama known unavailable — skip entirely
    if (
        _ollama_available is False
        and _ollama_last_check is not None
        and (now - _ollama_last_check).total_seconds() < OLLAMA_CACHE_TTL
    ):
        return False, []

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
        _ollama_available = True
        _ollama_last_check = now
        return True, data.get("models", [])
    except Exception as e:
        _ollama_available = False
        _ollama_last_check = now
        logger.debug(f"Ollama unavailable: {e}")
        return False, []


async def sync_ollama_models(session: Session) -> tuple[int, bool]:
    """Discover and import local Ollama models. Uses circuit-breaker — never blocks > 2s."""
    available, models_data = await _ollama_fetch_tags()
    if not available:
        logger.info(f"Ollama not available at {settings.ollama_base_url}")
        return 0, False

    if not models_data:
        return 0, True

    added = 0
    for m in models_data:
        name = m.get("name", "")
        if not name:
            continue

        # Check if already exists
        existing = session.exec(
            select(LLMModel).where(
                LLMModel.model_id == name,
                LLMModel.provider == ModelProvider.OLLAMA,
            )
        ).first()
        if existing:
            continue

        # Parse size info
        size_bytes = m.get("size", 0)
        size_gb = round(size_bytes / 1e9, 1) if size_bytes else 0

        details = m.get("details", {})
        param_size = details.get("parameter_size", "")
        family = details.get("family", "")
        quant = details.get("quantization_level", "")

        display_name = f"{name} (Ollama)"
        if param_size:
            display_name = f"{name} [{param_size}]"

        tags = ["ollama", "local", "free"]
        if family:
            tags.append(family)
        if quant:
            tags.append(quant)

        session.add(LLMModel(
            name=display_name,
            provider=ModelProvider.OLLAMA,
            model_id=name,
            endpoint=settings.ollama_base_url,
            context_length=int(details.get("context_length", 4096)),
            cost_input_per_1k=0.0,
            cost_output_per_1k=0.0,
            is_free=True,
            tags=json.dumps(tags),
            notes=f"Local Ollama model. {param_size} params, {size_gb}GB on disk. Quantization: {quant}",
        ))
        added += 1

    if added:
        session.commit()
    logger.info(f"Ollama sync: {added} new models from {len(models_data)} available")
    return added, True


@router.get("/ollama")
async def check_ollama():
    """Check Ollama availability and list local models. Uses circuit-breaker — max 2s wait."""
    available, raw_models = await _ollama_fetch_tags()
    if not available:
        return {"available": False, "error": "Ollama unreachable", "url": settings.ollama_base_url, "models": []}

    models = []
    for m in raw_models:
        details = m.get("details", {})
        models.append({
            "name": m.get("name", ""),
            "size_gb": round(m.get("size", 0) / 1e9, 1),
            "family": details.get("family", ""),
            "parameter_size": details.get("parameter_size", ""),
            "quantization": details.get("quantization_level", ""),
        })

    return {
        "available": True,
        "url": settings.ollama_base_url,
        "models": models,
        "total": len(models),
    }


@router.post("/ollama/import")
async def import_ollama_models(session: Session = Depends(get_session)):
    """Import all local Ollama models into the platform."""
    added, available = await sync_ollama_models(session)
    if not available:
        return {"added": 0, "available": False, "message": f"Ollama not reachable at {settings.ollama_base_url}"}
    return {"added": added, "available": True}


# ── Ollama Model Mapping (OpenRouter → local equivalent) ──────────────────────

OPENROUTER_TO_OLLAMA = {
    "meta-llama/llama-3.3-70b-instruct": "llama3.3:70b",
    "meta-llama/llama-3.2-3b-instruct": "llama3.2:3b",
    "meta-llama/llama-3.2-1b-instruct": "llama3.2:1b",
    "meta-llama/llama-3.1-8b-instruct": "llama3.1:8b",
    "meta-llama/llama-3.1-70b-instruct": "llama3.1:70b",
    "google/gemma-3-27b-it": "gemma3:27b",
    "google/gemma-3-12b-it": "gemma3:12b",
    "google/gemma-2-9b-it": "gemma2:9b",
    "google/gemma-2-27b-it": "gemma2:27b",
    "mistralai/mistral-7b-instruct": "mistral:7b",
    "mistralai/mixtral-8x7b-instruct": "mixtral:8x7b",
    "mistralai/mistral-small-24b-instruct-2501": "mistral-small:24b",
    "qwen/qwen-2.5-7b-instruct": "qwen2.5:7b",
    "qwen/qwen-2.5-14b-instruct": "qwen2.5:14b",
    "qwen/qwen-2.5-32b-instruct": "qwen2.5:32b",
    "qwen/qwen-2.5-72b-instruct": "qwen2.5:72b",
    "deepseek/deepseek-r1-distill-qwen-7b": "deepseek-r1:7b",
    "deepseek/deepseek-r1-distill-qwen-14b": "deepseek-r1:14b",
    "microsoft/phi-3-mini-128k-instruct": "phi3:mini",
    "microsoft/phi-3-medium-128k-instruct": "phi3:medium",
}

# Also match :free variants
for k in list(OPENROUTER_TO_OLLAMA.keys()):
    OPENROUTER_TO_OLLAMA[k + ":free"] = OPENROUTER_TO_OLLAMA[k]


@router.get("/ollama/suggestions")
async def get_ollama_suggestions(session: Session = Depends(get_session)):
    """For each registered OpenRouter model, check if a local Ollama equivalent exists.
    Returns suggestions for models that could be run locally."""

    # Get all registered models
    models = session.exec(select(LLMModel)).all()

    # Get available Ollama models — circuit-breaker, max 2s, cached 30s
    available, raw_models = await _ollama_fetch_tags()
    if not available:
        return {"suggestions": [], "ollama_available": False}

    local_models = {m.get("name", "") for m in raw_models}

    suggestions = []
    for model in models:
        if model.provider == ModelProvider.OLLAMA:
            continue  # Already local
        model_id = model.model_id.removeprefix("openrouter/")
        ollama_name = OPENROUTER_TO_OLLAMA.get(model_id)
        if not ollama_name:
            continue

        already_installed = any(ollama_name.split(":")[0] in lm for lm in local_models)

        suggestions.append({
            "model_id": model.id,
            "model_name": model.name,
            "openrouter_id": model_id,
            "ollama_name": ollama_name,
            "already_installed": already_installed,
            "install_command": f"ollama pull {ollama_name}",
        })

    return {
        "suggestions": suggestions,
        "ollama_available": True,
        "local_models_count": len(local_models),
    }


@router.post("/ollama/pull")
async def pull_ollama_model(model_name: str):
    """Trigger ollama pull for a model. Returns immediately — pull runs async."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Ollama pull API — streams progress but we just fire and check
            resp = await client.post(
                f"{settings.ollama_base_url}/api/pull",
                json={"name": model_name, "stream": False},
                timeout=600.0,  # Models can be large
            )
            if resp.status_code == 200:
                return {"status": "pulled", "model": model_name}
            else:
                return {"status": "error", "model": model_name, "detail": resp.text[:200]}
    except httpx.TimeoutException:
        return {"status": "pulling", "model": model_name, "message": "Pull started but not yet complete. Large models take time."}
    except Exception as e:
        return {"status": "error", "model": model_name, "detail": str(e)[:200]}


@router.post("/ollama/pull-and-register")
async def pull_and_register_ollama_model(
    openrouter_model_id: str,
    session: Session = Depends(get_session),
):
    """Pull the Ollama equivalent of an OpenRouter model and register it."""
    ollama_name = OPENROUTER_TO_OLLAMA.get(openrouter_model_id)
    if not ollama_name:
        ollama_name = OPENROUTER_TO_OLLAMA.get(openrouter_model_id + ":free")
    if not ollama_name:
        return {"status": "no_mapping", "detail": f"No Ollama equivalent for {openrouter_model_id}"}

    # Pull
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/pull",
                json={"name": ollama_name, "stream": False},
                timeout=600.0,
            )
    except Exception as e:
        return {"status": "pull_failed", "model": ollama_name, "detail": str(e)[:200]}

    # Register in DB
    existing = session.exec(
        select(LLMModel).where(LLMModel.model_id == ollama_name, LLMModel.provider == ModelProvider.OLLAMA)
    ).first()
    if not existing:
        session.add(LLMModel(
            name=f"{ollama_name} (Ollama)",
            provider=ModelProvider.OLLAMA,
            model_id=ollama_name,
            endpoint=settings.ollama_base_url,
            context_length=4096,
            cost_input_per_1k=0.0,
            cost_output_per_1k=0.0,
            is_free=True,
            tags=json.dumps(["ollama", "local", "free"]),
        ))
        session.commit()

    return {
        "status": "ok",
        "ollama_model": ollama_name,
        "openrouter_model": openrouter_model_id,
        "registered": True,
    }
