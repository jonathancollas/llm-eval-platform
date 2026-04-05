from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlmodel import Session, select
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import json
import uuid
from pathlib import Path

from core.database import get_session
from core.models import Benchmark, BenchmarkType
from core.config import get_settings

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])
settings = get_settings()


# ── Schemas ────────────────────────────────────────────────────────────────────

class BenchmarkCreate(BaseModel):
    name: str
    type: BenchmarkType
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    metric: str = "accuracy"
    num_samples: Optional[int] = None
    config: dict = Field(default_factory=dict)
    risk_threshold: Optional[float] = None


class BenchmarkRead(BaseModel):
    id: int
    name: str
    type: BenchmarkType
    description: str
    tags: list[str]
    metric: str
    num_samples: Optional[int]
    config: dict
    is_builtin: bool
    risk_threshold: Optional[float]
    has_dataset: bool
    created_at: datetime


def _to_read(b: Benchmark) -> BenchmarkRead:
    has_dataset = False
    if b.dataset_path:
        full = Path(settings.bench_library_path) / b.dataset_path
        has_dataset = full.exists()
    return BenchmarkRead(
        id=b.id,
        name=b.name,
        type=b.type,
        description=b.description,
        tags=json.loads(b.tags),
        metric=b.metric,
        num_samples=b.num_samples,
        config=json.loads(b.config_json),
        is_builtin=b.is_builtin,
        risk_threshold=b.risk_threshold,
        has_dataset=has_dataset,
        created_at=b.created_at,
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[BenchmarkRead])
def list_benchmarks(
    type: Optional[BenchmarkType] = None,
    session: Session = Depends(get_session),
):
    query = select(Benchmark)
    if type:
        query = query.where(Benchmark.type == type)
    return [_to_read(b) for b in session.exec(query).all()]


@router.get("/{benchmark_id}", response_model=BenchmarkRead)
def get_benchmark(benchmark_id: int, session: Session = Depends(get_session)):
    bench = session.get(Benchmark, benchmark_id)
    if not bench:
        raise HTTPException(status_code=404, detail="Benchmark not found.")
    return _to_read(bench)


@router.post("/", response_model=BenchmarkRead, status_code=status.HTTP_201_CREATED)
def create_benchmark(payload: BenchmarkCreate, session: Session = Depends(get_session)):
    """Create a custom benchmark definition (without dataset — upload separately)."""
    bench = Benchmark(
        name=payload.name,
        type=payload.type,
        description=payload.description,
        tags=json.dumps(payload.tags),
        metric=payload.metric,
        num_samples=payload.num_samples,
        config_json=json.dumps(payload.config),
        risk_threshold=payload.risk_threshold,
        is_builtin=False,
    )
    session.add(bench)
    session.commit()
    session.refresh(bench)
    return _to_read(bench)


@router.post("/{benchmark_id}/upload-dataset", response_model=BenchmarkRead)
async def upload_dataset(
    benchmark_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Upload a JSON dataset file for a custom benchmark."""
    bench = session.get(Benchmark, benchmark_id)
    if not bench:
        raise HTTPException(status_code=404, detail="Benchmark not found.")
    if bench.is_builtin:
        raise HTTPException(status_code=400, detail="Cannot override built-in benchmark datasets.")

    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {e}")

    # Validate structure
    items = data if isinstance(data, list) else data.get("items", [])
    if not items:
        raise HTTPException(status_code=422, detail="Dataset must contain a non-empty list of items.")

    # Save to bench_library/custom/
    custom_dir = Path(settings.bench_library_path) / "custom"
    custom_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    dest = custom_dir / filename
    dest.write_bytes(content)

    bench.dataset_path = f"custom/{filename}"
    bench.num_samples = bench.num_samples or len(items)
    session.add(bench)
    session.commit()
    session.refresh(bench)
    return _to_read(bench)


@router.delete("/{benchmark_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_benchmark(benchmark_id: int, session: Session = Depends(get_session)):
    bench = session.get(Benchmark, benchmark_id)
    if not bench:
        raise HTTPException(status_code=404, detail="Benchmark not found.")
    if bench.is_builtin:
        raise HTTPException(status_code=400, detail="Cannot delete built-in benchmarks.")
    session.delete(bench)
    session.commit()

@router.get("/{benchmark_id}/items")
def get_benchmark_items(
    benchmark_id: int,
    page: int = 1,
    page_size: int = 20,
    search: str = "",
    session: Session = Depends(get_session),
):
    """Browse dataset items for a benchmark (paginated)."""
    from pathlib import Path
    from core.config import get_settings
    from core.utils import safe_json_load
    import json

    settings = get_settings()
    benchmark = session.get(Benchmark, benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark not found.")

    if not benchmark.dataset_path:
        return {"items": [], "total": 0, "page": page, "page_size": page_size,
                "source": "lm_eval", "message": "This benchmark uses lm-evaluation-harness datasets (downloaded at runtime)."}

    full_path = Path(settings.bench_library_path) / benchmark.dataset_path
    if not full_path.exists():
        return {"items": [], "total": 0, "page": page, "page_size": page_size,
                "source": "missing", "message": f"Dataset file not found: {benchmark.dataset_path}"}

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data if isinstance(data, list) else data.get("items", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read dataset: {e}")

    # Search filter
    if search:
        search_lower = search.lower()
        items = [
            item for item in items
            if any(search_lower in str(v).lower() for v in item.values())
        ]

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
        "source": "local",
        "dataset_path": benchmark.dataset_path,
    }
