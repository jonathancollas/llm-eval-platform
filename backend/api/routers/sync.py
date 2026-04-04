"""
Sync endpoint — returns only NEW benchmarks not yet in the local DB.
Called silently at app startup.
"""
import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from core.database import get_session
from core.models import Benchmark, BenchmarkType
from api.routers.catalog import BENCHMARK_CATALOG

router = APIRouter(prefix="/sync", tags=["sync"])


class SyncResult(BaseModel):
    new_benchmarks: list[dict]
    new_count: int
    total_catalog: int
    total_local: int


@router.get("/benchmarks", response_model=SyncResult)
def sync_benchmarks(session: Session = Depends(get_session)):
    """
    Compare catalog vs local DB.
    Returns only benchmarks not yet present locally (by name).
    """
    local_names = {b.name for b in session.exec(select(Benchmark)).all()}
    total_local = len(local_names)

    new_items = []
    for item in BENCHMARK_CATALOG:
        if item["name"] not in local_names:
            new_items.append(item)

    return SyncResult(
        new_benchmarks=new_items,
        new_count=len(new_items),
        total_catalog=len(BENCHMARK_CATALOG),
        total_local=total_local,
    )


@router.post("/benchmarks/import-all")
def import_all_new(session: Session = Depends(get_session)):
    """Import all catalog benchmarks not yet in DB."""
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
    return {"added": added, "message": f"{added} nouveaux benchmarks importés."}
