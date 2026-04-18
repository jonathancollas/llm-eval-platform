"""
Task Registry API — query tasks by capability, domain, difficulty.

Endpoints
─────────
GET  /tasks              — list / filter tasks
GET  /tasks/stats        — aggregate statistics
GET  /tasks/{canonical_id} — get a single task by its canonical ID
POST /tasks              — register a new custom task
DELETE /tasks/{canonical_id} — remove a custom task
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from core.database import get_session
from core.models import TaskRegistryEntry
from datetime import datetime
from eval_engine.task_registry import task_registry, TaskEntry

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class TaskRead(BaseModel):
    canonical_id: str
    name: str
    description: str
    domain: str
    capability_tags: list[str]
    difficulty: str
    benchmark_name: str
    namespace: str
    source_url: str
    paper_url: str
    year: Optional[int]
    license: str
    provenance: str
    contamination_risk: str
    known_contamination_notes: str
    required_environment: str
    dependencies: list[str]
    created_at: str
    updated_at: str


class TaskCreate(BaseModel):
    canonical_id: str = Field(..., min_length=3, pattern=r"^[a-z0-9_]+:[a-z0-9_]+:[a-z0-9_]+$")
    name: str = Field(..., min_length=1, max_length=300)
    description: str = ""
    domain: str = ""
    capability_tags: list[str] = Field(default_factory=list)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard|expert)$")
    benchmark_name: str = ""
    namespace: str = Field(default="community", pattern="^(public|inesia|community)$")
    source_url: str = ""
    paper_url: str = ""
    year: Optional[int] = None
    license: str = "unknown"
    provenance: str = ""
    contamination_risk: str = Field(default="low", pattern="^(low|medium|high|critical)$")
    known_contamination_notes: str = ""
    required_environment: str = Field(default="none", pattern="^(none|sandbox|docker|network)$")
    dependencies: list[str] = Field(default_factory=list)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _entry_to_read(entry: TaskRegistryEntry) -> TaskRead:
    return TaskRead(
        canonical_id=entry.canonical_id,
        name=entry.name,
        description=entry.description,
        domain=entry.domain,
        capability_tags=json.loads(entry.capability_tags or "[]"),
        difficulty=entry.difficulty,
        benchmark_name=entry.benchmark_name,
        namespace=entry.namespace,
        source_url=entry.source_url,
        paper_url=entry.paper_url,
        year=entry.year,
        license=entry.license,
        provenance=entry.provenance,
        contamination_risk=entry.contamination_risk,
        known_contamination_notes=entry.known_contamination_notes,
        required_environment=entry.required_environment,
        dependencies=json.loads(entry.dependencies or "[]"),
        created_at=entry.created_at.isoformat(),
        updated_at=entry.updated_at.isoformat(),
    )


def _task_entry_to_db(task: TaskEntry) -> TaskRegistryEntry:
    now = datetime.utcnow()
    return TaskRegistryEntry(
        canonical_id=task.canonical_id,
        name=task.name,
        description=task.description,
        domain=task.domain,
        capability_tags=json.dumps(task.capability_tags),
        difficulty=task.difficulty,
        benchmark_name=task.benchmark_name,
        namespace=task.namespace,
        source_url=task.source_url,
        paper_url=task.paper_url,
        year=task.year,
        license=task.license,
        provenance=task.provenance,
        contamination_risk=task.contamination_risk,
        known_contamination_notes=task.known_contamination_notes,
        required_environment=task.required_environment,
        dependencies=json.dumps(task.dependencies),
        created_at=now,
        updated_at=now,
    )


def _ensure_seeded(session: Session) -> None:
    """Sync the in-memory registry into the DB on first use (idempotent)."""
    existing = set(
        session.exec(select(TaskRegistryEntry.canonical_id)).all()
    )
    to_add = [
        _task_entry_to_db(task)
        for task in task_registry.list_all()
        if task.canonical_id not in existing
    ]
    if to_add:
        for entry in to_add:
            session.add(entry)
        session.commit()
        logger.info(f"Task registry: seeded {len(to_add)} tasks into DB.")


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(session: Session = Depends(get_session)) -> dict:
    """Return aggregate statistics about the task registry."""
    _ensure_seeded(session)

    entries = session.exec(select(TaskRegistryEntry)).all()

    domains: dict[str, int] = {}
    difficulties: dict[str, int] = {}
    namespaces: dict[str, int] = {}
    cap_counts: dict[str, int] = {}

    for e in entries:
        domains[e.domain] = domains.get(e.domain, 0) + 1
        difficulties[e.difficulty] = difficulties.get(e.difficulty, 0) + 1
        namespaces[e.namespace] = namespaces.get(e.namespace, 0) + 1
        for cap in json.loads(e.capability_tags or "[]"):
            cap_counts[cap] = cap_counts.get(cap, 0) + 1

    return {
        "total": len(entries),
        "by_domain": domains,
        "by_difficulty": difficulties,
        "by_namespace": namespaces,
        "top_capabilities": sorted(cap_counts.items(), key=lambda x: -x[1])[:20],
    }


@router.get("", response_model=list[TaskRead])
def list_tasks(
    capability: Optional[str] = Query(None, description="Filter by capability tag"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    difficulty: Optional[str] = Query(None, description="Filter by difficulty: easy|medium|hard|expert"),
    namespace: Optional[str] = Query(None, description="Filter by namespace: public|inesia|community"),
    search: Optional[str] = Query(None, description="Full-text search in name/description"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[TaskRead]:
    """List tasks with optional filters."""
    _ensure_seeded(session)

    stmt = select(TaskRegistryEntry)

    if domain:
        stmt = stmt.where(TaskRegistryEntry.domain == domain.lower())
    if difficulty:
        stmt = stmt.where(TaskRegistryEntry.difficulty == difficulty.lower())
    if namespace:
        stmt = stmt.where(TaskRegistryEntry.namespace == namespace.lower())

    entries = session.exec(stmt).all()

    # Apply in-memory filters that require JSON parsing
    if capability:
        cap_lower = capability.lower()
        entries = [
            e for e in entries
            if any(cap_lower in c.lower() for c in json.loads(e.capability_tags or "[]"))
        ]
    if search:
        s = search.lower()
        entries = [
            e for e in entries
            if s in e.name.lower() or s in e.description.lower()
        ]

    # Pagination
    entries = entries[offset: offset + limit]
    return [_entry_to_read(e) for e in entries]


@router.get("/{canonical_id}", response_model=TaskRead)
def get_task(
    canonical_id: str,
    session: Session = Depends(get_session),
) -> TaskRead:
    """Retrieve a single task by its canonical ID (namespace:benchmark:task_id)."""
    _ensure_seeded(session)
    entry = session.get(TaskRegistryEntry, canonical_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Task '{canonical_id}' not found.")
    return _entry_to_read(entry)


@router.post("", response_model=TaskRead, status_code=201)
def create_task(
    body: TaskCreate,
    session: Session = Depends(get_session),
) -> TaskRead:
    """Register a new custom task in the registry."""
    _ensure_seeded(session)

    existing = session.get(TaskRegistryEntry, body.canonical_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Task '{body.canonical_id}' already exists.")

    now = datetime.utcnow()
    entry = TaskRegistryEntry(
        canonical_id=body.canonical_id,
        name=body.name,
        description=body.description,
        domain=body.domain,
        capability_tags=json.dumps(body.capability_tags),
        difficulty=body.difficulty,
        benchmark_name=body.benchmark_name,
        namespace=body.namespace,
        source_url=body.source_url,
        paper_url=body.paper_url,
        year=body.year,
        license=body.license,
        provenance=body.provenance,
        contamination_risk=body.contamination_risk,
        known_contamination_notes=body.known_contamination_notes,
        required_environment=body.required_environment,
        dependencies=json.dumps(body.dependencies),
        created_at=now,
        updated_at=now,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)

    # Also register in the in-memory registry
    task_registry.register(TaskEntry(
        canonical_id=body.canonical_id,
        name=body.name,
        description=body.description,
        domain=body.domain,
        capability_tags=body.capability_tags,
        difficulty=body.difficulty,
        benchmark_name=body.benchmark_name,
        namespace=body.namespace,
        source_url=body.source_url,
        paper_url=body.paper_url,
        year=body.year,
        license=body.license,
        provenance=body.provenance,
        contamination_risk=body.contamination_risk,
        known_contamination_notes=body.known_contamination_notes,
        required_environment=body.required_environment,
        dependencies=body.dependencies,
    ))

    return _entry_to_read(entry)


@router.delete("/{canonical_id}", status_code=204)
def delete_task(
    canonical_id: str,
    session: Session = Depends(get_session),
) -> None:
    """Remove a task from the registry (non-destructive — does not delete eval runs)."""
    entry = session.get(TaskRegistryEntry, canonical_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Task '{canonical_id}' not found.")
    session.delete(entry)
    session.commit()
    # Remove from in-memory registry so it won't be re-seeded
    task_registry._tasks.pop(canonical_id, None)
