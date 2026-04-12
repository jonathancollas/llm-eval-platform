"""
Mercury Retrograde — INESIA AI Evaluation Platform
FastAPI application entry point.
"""
import hmac as _hmac
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlmodel import Session

from core.config import get_settings
from core.database import create_db_and_tables, engine
from api.routers import models, benchmarks, campaigns, results, reports, catalog, leaderboard, sync, genome
from api.routers import redbox
from api.routers import judge
from api.routers import agents
from api.routers import policy
from api.routers import tenants
from api.routers import research
from api.routers import evidence
from api.routers import deep_analysis
from api.routers import multiagent
from api.routers import events as events_router
from eval_engine.event_pipeline import register_default_subscribers
from api.routers import monitoring
from api.routers import science

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Create tables + reset stuck campaigns + update has_dataset flags
    logger.info("Startup — initializing DB...")
    # Run sync DB init in executor to avoid blocking event loop
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, create_db_and_tables)

    # 2. Wire event-sourced pipeline subscribers
    register_default_subscribers()
    logger.info("Startup — event bus subscribers registered.")

    # 3. Sync catalog benchmarks in executor (CPU-bound, no network)
    logger.info("Startup — syncing benchmark catalog...")
    def _sync_catalog():
        from api.routers.sync import sync_benchmarks_from_catalog, sync_starter_models
        from sqlmodel import select as sqlsel
        from core.models import LLMModel
        with Session(engine) as session:
            benches_added = sync_benchmarks_from_catalog(session)
            logger.info(f"Startup — {benches_added} benchmarks added from catalog.")
            model_count = len(session.exec(sqlsel(LLMModel)).all())
            if model_count == 0:
                models_added = sync_starter_models(session)
                logger.info(f"Startup — {models_added} starter models imported.")
    await loop.run_in_executor(None, _sync_catalog)

    # 4. Async OpenRouter sync in background (non-blocking)
    # Store the task so it can be properly cancelled on shutdown.
    app.state.bg_sync_task = asyncio.create_task(_background_openrouter_sync())
    app.state.bg_queue_recovery_task = asyncio.create_task(_background_queue_recovery())

    logger.info(f"Ready ✓  bench_library={settings.bench_library_path}")
    yield
    # Cancel the background task and wait for it to finish cleanly.
    tasks = [app.state.bg_sync_task, app.state.bg_queue_recovery_task]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Shutdown.")


async def _background_openrouter_sync():
    """Sync OpenRouter + Ollama models after startup — runs in background."""
    await asyncio.sleep(2)  # Let server fully start first

    # OpenRouter
    try:
        from api.routers.sync import sync_openrouter_models
        with Session(engine) as session:
            added, synced = await sync_openrouter_models(session)
            logger.info(f"Background OpenRouter sync: +{added} models (synced={synced})")
    except Exception as e:
        logger.warning(f"Background OpenRouter sync failed: {e}")

    # Ollama (local models)
    try:
        from api.routers.sync import sync_ollama_models
        with Session(engine) as session:
            added, available = await sync_ollama_models(session)
            if available:
                logger.info(f"Background Ollama sync: +{added} local models")
            else:
                logger.info("Ollama not available (optional — install from ollama.com)")
    except Exception as e:
        logger.debug(f"Ollama sync skipped: {e}")


async def _background_queue_recovery():
    from core import job_queue

    while True:
        try:
            recovered = job_queue.recover_stale_campaigns()
            if recovered:
                logger.warning(f"Marked {len(recovered)} stale campaigns as FAILED: {recovered}")
        except Exception as e:
            logger.warning(f"Background queue recovery failed: {e}")
        await asyncio.sleep(60)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ── Middleware ─────────────────────────────────────────────────────────────────

app.add_middleware(GZipMiddleware, minimum_size=1000)

import os as _os
import time as _time
from collections import defaultdict as _defaultdict

# ── Simple in-memory rate limiter ──────────────────────────────────────────────
_rate_limit_store: dict[str, list[float]] = _defaultdict(list)
_RATE_LIMIT_RPM = int(_os.getenv("RATE_LIMIT_RPM", "120"))  # requests per minute
_RATE_LIMIT_ENABLED = _os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
# Hard cap on timestamps kept per IP to prevent unbounded memory growth.
# We never need to store more than RPM entries for any single IP.
_RATE_LIMIT_MAX_STORE = _RATE_LIMIT_RPM

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next: Callable) -> Response:
    if not _RATE_LIMIT_ENABLED or request.method == "OPTIONS":
        return await call_next(request)
    # Skip health and docs
    if request.url.path in ("/api/health", "/api/docs", "/api/redoc", "/api/openapi.json"):
        return await call_next(request)
    client_ip = request.client.host if request.client else "unknown"
    now = _time.time()
    # Prune timestamps outside the 60-second window
    window = [t for t in _rate_limit_store[client_ip] if now - t < 60]
    # Cap stored entries to prevent memory growth from burst IPs
    _rate_limit_store[client_ip] = window[-_RATE_LIMIT_MAX_STORE:]
    if len(window) >= _RATE_LIMIT_RPM:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Max {}/min.".format(_RATE_LIMIT_RPM)})
    _rate_limit_store[client_ip].append(now)
    return await call_next(request)


_ALLOWED_ORIGINS = [o.strip() for o in _os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()] or [
    "https://llm-eval-frontend.onrender.com",
    "http://localhost:3000",
    "http://localhost:3001",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next: Callable) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


_ADMIN_API_KEY = _os.getenv("ADMIN_API_KEY", "")

@app.middleware("http")
async def api_key_auth(request: Request, call_next: Callable) -> Response:
    """
    API key authentication (#S1).
    - ADMIN_API_KEY set: all non-public routes require X-API-Key header.
    - ADMIN_API_KEY unset: dev mode — requests pass but response carries warning header.
    Public: /api/health, /docs, /redoc, /openapi.json, OPTIONS preflight.
    """
    public = (
        request.method == "OPTIONS"
        or request.url.path in ("/api/health", "/api/docs", "/api/redoc", "/api/openapi.json")
    )
    if public:
        return await call_next(request)

    if not _ADMIN_API_KEY:
        # Dev mode — warn operator, allow request
        resp = await call_next(request)
        resp.headers["X-Auth-Warning"] = (
            "ADMIN_API_KEY not configured - authentication disabled. "
            "Set ADMIN_API_KEY env var before deploying to production."
        )
        return resp

    # Production mode — enforce key using constant-time comparison to prevent timing attacks
    key = request.headers.get("X-API-Key", "")
    if not key:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing X-API-Key header. Set ADMIN_API_KEY and pass it as X-API-Key."},
        )
    if not _hmac.compare_digest(key, _ADMIN_API_KEY):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={"detail": "Invalid API key."})
    return await call_next(request)


# ── Routers ────────────────────────────────────────────────────────────────────

for router in [models.router, benchmarks.router, campaigns.router, results.router,
               reports.router, catalog.router, leaderboard.router, sync.router, genome.router,
               redbox.router, judge.router, agents.router, policy.router, tenants.router,
               research.router, evidence.router, deep_analysis.router,
               multiagent.router, events_router.router,
               monitoring.router, science.router]:
    app.include_router(router, prefix="/api")


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["health"])
def health():
    from pathlib import Path
    from core import job_queue
    bench_path = Path(settings.bench_library_path)
    bench_exists = bench_path.exists()
    bench_files = list(bench_path.rglob("*.json")) if bench_exists else []
    queue = job_queue.get_queue_status()

    is_postgres = settings.database_url.startswith("postgres")

    return {
        "status": "ok",
        "version": settings.app_version,
        "database": "postgresql" if is_postgres else "sqlite",
        "queue_mode": queue["mode"],
        "queue_active": queue["in_memory_tasks"],
        "bench_library_path": str(bench_path),
        "bench_library_exists": bench_exists,
        "bench_files_count": len(bench_files),
        "ollama_url": settings.ollama_base_url,
    }
