import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.database import create_db_and_tables
from api.routers import models, benchmarks, campaigns, results, reports, catalog

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
    logger.info("Ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(models.router,     prefix="/api")
app.include_router(benchmarks.router, prefix="/api")
app.include_router(campaigns.router,  prefix="/api")
app.include_router(results.router,    prefix="/api")
app.include_router(reports.router,    prefix="/api")
app.include_router(catalog.router,    prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "version": settings.app_version}
