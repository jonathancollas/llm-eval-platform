"""
Mercury Retrograde — INESIA AI Evaluation Platform
FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from core.config import get_settings
from core.database import create_db_and_tables
from api.routers import models, benchmarks, campaigns, results, reports, catalog, leaderboard, sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — creating DB tables and seeding benchmarks…")
    create_db_and_tables()
    logger.info(f"Ready. bench_library_path={settings.bench_library_path}")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(GZipMiddleware, minimum_size=1000)

import os as _os
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
    """Add security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


# ── Routers ───────────────────────────────────────────────────────────────────

for router in [
    models.router,
    benchmarks.router,
    campaigns.router,
    results.router,
    reports.router,
    catalog.router,
    leaderboard.router,
    sync.router,
]:
    app.include_router(router, prefix="/api")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["health"])
def health():
    from pathlib import Path
    bench_ok = Path(settings.bench_library_path).exists()
    return {
        "status": "ok",
        "version": settings.app_version,
        "bench_library": settings.bench_library_path,
        "bench_library_exists": bench_ok,
    }
