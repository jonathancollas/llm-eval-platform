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
async def get_benchmark_items(
    benchmark_id: int,
    page: int = 1,
    page_size: int = 20,
    search: str = "",
    session: Session = Depends(get_session),
):
    """Browse dataset items for a benchmark (paginated).
    Supports: local JSON files, lm-eval HuggingFace datasets.
    """
    from pathlib import Path
    from core.config import get_settings
    import json, asyncio

    settings = get_settings()
    benchmark = session.get(Benchmark, benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark not found.")

    items = []
    source = "unknown"

    # 1. Try local JSON file first
    if benchmark.dataset_path:
        full_path = Path(settings.bench_library_path) / benchmark.dataset_path
        if full_path.exists():
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                items = data if isinstance(data, list) else data.get("items", [])
                source = "local"
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to read dataset: {e}")

    # 2. If no local file, try loading from lm-eval / HuggingFace
    if not items:
        from eval_engine.registry import _find_harness_task
        task_name = _find_harness_task(benchmark.name) if benchmark.name else None

        if task_name:
            try:
                hf_items = await asyncio.get_event_loop().run_in_executor(
                    None, _load_hf_items, task_name, page_size * 3
                )
                if hf_items:
                    items = hf_items
                    source = f"huggingface:{task_name}"
            except Exception as e:
                return {
                    "items": [], "total": 0, "page": page, "page_size": page_size,
                    "source": "hf_error",
                    "message": f"Could not load HuggingFace dataset for '{task_name}': {str(e)[:200]}",
                }
        else:
            return {
                "items": [], "total": 0, "page": page, "page_size": page_size,
                "source": "no_dataset",
                "message": "No local dataset and no matching lm-eval task found. Upload a JSON dataset.",
            }

    # Search filter
    if search:
        s = search.lower()
        items = [it for it in items if any(s in str(v).lower() for v in it.values())]

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "source": source,
        "dataset_path": benchmark.dataset_path,
    }


def _load_hf_items(task_name: str, limit: int = 60) -> list[dict]:
    """Load items from HuggingFace via lm-eval task (synchronous, runs in thread)."""
    from lm_eval.tasks import TaskManager
    import logging
    logger = logging.getLogger(__name__)

    try:
        tm = TaskManager()
        task_dict = tm.load_task_or_group([task_name])
        task = task_dict.get(task_name)
        if not task:
            return []

        # Build the task to get the dataset
        task.build_all_requests(rank=0, world_size=1)
        docs = list(task.test_docs() or task.validation_docs() or [])
        if not docs:
            docs = list(task.test_docs() or [])

        items = []
        for doc in docs[:limit]:
            if hasattr(task, "doc_to_text"):
                try:
                    item = dict(doc) if hasattr(doc, "items") else {"text": str(doc)}
                    # Add the rendered prompt
                    item["_prompt"] = task.doc_to_text(doc)
                    if hasattr(task, "doc_to_target"):
                        item["_answer"] = task.doc_to_target(doc)
                    items.append(item)
                except Exception:
                    items.append(dict(doc) if hasattr(doc, "items") else {"text": str(doc)})
            else:
                items.append(dict(doc) if hasattr(doc, "items") else {"text": str(doc)})

        logger.info(f"Loaded {len(items)} items from HuggingFace for task '{task_name}'")
        return items

    except Exception as e:
        logger.warning(f"HuggingFace load failed for '{task_name}': {e}")
        raise


# ── CATALOG-2: HuggingFace Dataset Import ──────────────────────────────────────

class HuggingFaceImportRequest(BaseModel):
    repo_id: str = Field(..., description="HuggingFace repo ID (e.g. 'cais/mmlu', 'tatsu-lab/alpaca_eval')")
    split: str = Field(default="test", description="Dataset split: train, test, validation")
    subset: Optional[str] = Field(default=None, description="Dataset subset/config name")
    max_items: int = Field(default=500, ge=10, le=5000)
    benchmark_name: Optional[str] = Field(default=None, description="Custom name, defaults to repo_id")
    benchmark_type: BenchmarkType = Field(default=BenchmarkType.CUSTOM)


@router.post("/import-huggingface")
async def import_huggingface_dataset(
    payload: HuggingFaceImportRequest,
    session: Session = Depends(get_session),
):
    """Import a dataset from HuggingFace Hub and create a benchmark."""
    import httpx
    import logging as _log

    logger = _log.getLogger(__name__)

    # Build HuggingFace API URL
    base = "https://datasets-server.huggingface.co/rows"
    params = {
        "dataset": payload.repo_id,
        "split": payload.split,
        "offset": 0,
        "length": min(payload.max_items, 100),  # API max 100 per page
    }
    if payload.subset:
        params["config"] = payload.subset

    all_items = []
    offset = 0

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(all_items) < payload.max_items:
                params["offset"] = offset
                params["length"] = min(100, payload.max_items - len(all_items))

                resp = await client.get(base, params=params)
                if resp.status_code == 404:
                    raise HTTPException(404, detail=f"Dataset '{payload.repo_id}' not found on HuggingFace.")
                resp.raise_for_status()
                data = resp.json()

                rows = data.get("rows", [])
                if not rows:
                    break

                for row in rows:
                    item = row.get("row", {})
                    # Normalize common field names
                    normalized = {}
                    for k, v in item.items():
                        normalized[k] = v
                    # Try to detect question/answer fields
                    q_fields = ["question", "input", "prompt", "text", "query", "instruction"]
                    a_fields = ["answer", "output", "target", "expected", "response", "label"]
                    for qf in q_fields:
                        if qf in normalized and "question" not in normalized:
                            normalized["question"] = normalized[qf]
                            break
                    for af in a_fields:
                        if af in normalized and "answer" not in normalized:
                            normalized["answer"] = str(normalized[af])
                            break
                    all_items.append(normalized)

                offset += len(rows)
                if len(rows) < params["length"]:
                    break  # No more data

    except httpx.HTTPError as e:
        raise HTTPException(502, detail=f"HuggingFace API error: {str(e)[:200]}")

    if not all_items:
        raise HTTPException(400, detail=f"No items found in '{payload.repo_id}' split='{payload.split}'")

    # Save as JSON
    bench_name = payload.benchmark_name or payload.repo_id.replace("/", "_")
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in bench_name)
    filename = f"huggingface_{safe_name}_{payload.split}.json"
    dataset_dir = Path(settings.bench_library_path) / "custom"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = dataset_dir / filename

    with open(dataset_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    # Create or update benchmark
    existing = session.exec(
        select(Benchmark).where(Benchmark.name == bench_name)
    ).first()

    if existing:
        existing.dataset_path = f"custom/{filename}"
        existing.has_dataset = True
        existing.num_samples = len(all_items)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        bench = existing
    else:
        bench = Benchmark(
            name=bench_name,
            type=payload.benchmark_type,
            description=f"Imported from HuggingFace: {payload.repo_id} ({payload.split} split, {len(all_items)} items)",
            tags=json.dumps(["huggingface", payload.repo_id.split("/")[0], payload.split]),
            dataset_path=f"custom/{filename}",
            metric="accuracy",
            num_samples=min(len(all_items), 50),
            config_json=json.dumps({"source": "huggingface", "repo_id": payload.repo_id, "split": payload.split, "subset": payload.subset}),
            is_builtin=False,
            has_dataset=True,
        )
        session.add(bench)
        session.commit()
        session.refresh(bench)

    # Detect fields for preview
    sample = all_items[0] if all_items else {}
    detected_fields = list(sample.keys())[:10]

    return {
        "benchmark_id": bench.id,
        "benchmark_name": bench.name,
        "items_imported": len(all_items),
        "dataset_path": f"custom/{filename}",
        "detected_fields": detected_fields,
        "sample_item": {k: str(v)[:200] for k, v in sample.items()} if sample else {},
        "source": f"huggingface:{payload.repo_id}/{payload.split}",
    }
