"""
Model Registry — CRUD + connection testing.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime, UTC
import json
from urllib.parse import urlparse

from core.database import get_session
from core.models import LLMModel, ModelProvider
from core.security import encrypt_api_key, decrypt_api_key
from core.utils import safe_json_load

router = APIRouter(prefix="/models", tags=["models"])


def _validate_endpoint(url: Optional[str]) -> Optional[str]:
    """Reject endpoints whose scheme or host could enable SSRF attacks."""
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Endpoint scheme '{parsed.scheme}' is not allowed. Use http or https.")
    host = parsed.hostname or ""
    # Resolve to a numeric IP when possible so hostname aliases are also caught
    import ipaddress
    try:
        import socket
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(5)
        try:
            numeric = socket.getaddrinfo(host, None)[0][4][0]
        finally:
            socket.setdefaulttimeout(old_timeout)
        addr = ipaddress.ip_address(numeric)
        if (
            addr.is_loopback
            or addr.is_link_local
            or addr.is_private
            or addr.is_unspecified
            or addr.is_multicast
            or addr.is_reserved
        ):
            raise ValueError(f"Endpoint host '{host}' resolves to a non-routable address and is not allowed.")
    except (ValueError, OSError):
        # If we can't resolve the name, fall back to simple string checks so that
        # obviously dangerous literals are still rejected.
        blocked_prefixes = ("127.", "10.", "0.0.0.0", "169.254.", "192.168.", "::1", "fd", "fc")  # nosec B104
        if host == "localhost" or any(host.startswith(p) for p in blocked_prefixes):
            raise ValueError(f"Endpoint host '{host}' is not allowed.")
    return url


# ── Pydantic schemas ────────────────────────────────────────────────────────────

class ModelCreate(BaseModel):
    name: str
    provider: ModelProvider
    model_id: str
    endpoint: Optional[str] = None
    api_key: Optional[str] = None   # plaintext — encrypted before storage
    context_length: int = 4096
    cost_input_per_1k: float = 0.0
    cost_output_per_1k: float = 0.0
    tags: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: Optional[str]) -> Optional[str]:
        return _validate_endpoint(v)


class ModelUpdate(BaseModel):
    name: Optional[str] = None
    model_id: Optional[str] = None
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    context_length: Optional[int] = None
    cost_input_per_1k: Optional[float] = None
    cost_output_per_1k: Optional[float] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: Optional[str]) -> Optional[str]:
        return _validate_endpoint(v)


class ModelRead(BaseModel):
    id: int
    name: str
    provider: ModelProvider
    model_id: str
    endpoint: Optional[str]
    has_api_key: bool
    context_length: int
    cost_input_per_1k: float
    cost_output_per_1k: float
    tags: list[str]
    notes: str
    is_active: bool
    supports_vision: bool
    supports_tools: bool
    supports_reasoning: bool
    is_free: bool
    max_output_tokens: int
    is_moderated: bool
    tokenizer: str
    instruct_type: str
    hugging_face_id: str
    model_created_at: int
    created_at: datetime
    updated_at: datetime


def _to_read(m: LLMModel) -> ModelRead:
    return ModelRead(
        id=m.id,
        name=m.name,
        provider=m.provider,
        model_id=m.model_id,
        endpoint=m.endpoint,
        has_api_key=bool(m.api_key_encrypted),
        context_length=m.context_length,
        cost_input_per_1k=m.cost_input_per_1k,
        cost_output_per_1k=m.cost_output_per_1k,
        tags=safe_json_load(m.tags, []),
        notes=m.notes,
        is_active=m.is_active,
        supports_vision=getattr(m, 'supports_vision', False),
        supports_tools=getattr(m, 'supports_tools', False),
        supports_reasoning=getattr(m, 'supports_reasoning', False),
        is_free=getattr(m, 'is_free', False),
        max_output_tokens=getattr(m, 'max_output_tokens', 0),
        is_moderated=getattr(m, 'is_moderated', False),
        tokenizer=getattr(m, 'tokenizer', ''),
        instruct_type=getattr(m, 'instruct_type', ''),
        hugging_face_id=getattr(m, 'hugging_face_id', ''),
        model_created_at=getattr(m, 'model_created_at', 0),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/slim")
def list_models_slim(session: Session = Depends(get_session)):
    """
    Lightweight model list — only fields needed for selectors and dropdowns.
    ~10x smaller payload than GET /models/ — use this in ModelSelector, wizards, etc.
    Returns: id, name, model_id, provider, is_free, is_open_weight, is_local
    """
    # Only fetch the columns we actually need
    models = session.exec(
        select(LLMModel.id, LLMModel.name, LLMModel.model_id,
               LLMModel.provider, LLMModel.is_free, LLMModel.is_open_weight,
               LLMModel.cost_input_per_1k, LLMModel.tags)
        .order_by(LLMModel.name)
    ).all()

    # Dedup by model_id
    seen: set[str] = set()
    result = []
    for row in models:
        mid = row[2]  # model_id
        if mid not in seen:
            seen.add(mid)
            is_local = row[3] == "ollama"  # provider
            result.append({
                "id": row[0],
                "name": row[1],
                "model_id": mid,
                "provider": row[3],
                "is_free": row[4],
                "is_open_weight": row[5],
                "is_local": is_local,
                "cost_input_per_1k": row[6],
            })
    return result


@router.get("/", response_model=list[ModelRead])
def list_models(
    session: Session = Depends(get_session),
    limit: int = 500,
    offset: int = 0,
    provider: Optional[str] = None,
    search: Optional[str] = None,
    free_only: bool = False,
    open_weight_only: bool = False,
):
    """
    List models with optional filtering and pagination.
    Default limit=500 covers all models in one call while staying fast.
    Use search/provider/free_only to reduce payload for the UI.
    """
    from sqlmodel import func

    # Use a subquery to pick the row with the lowest id for each model_id so
    # deduplication is done in SQL instead of loading all rows into memory.
    min_id_subq = (
        select(func.min(LLMModel.id).label("min_id"))
        .group_by(LLMModel.model_id)
        .subquery()
    )
    query = select(LLMModel).where(LLMModel.id.in_(select(min_id_subq.c.min_id)))

    if provider:
        query = query.where(LLMModel.provider == provider)
    if free_only:
        query = query.where(LLMModel.is_free == True)
    if open_weight_only:
        query = query.where(LLMModel.is_open_weight == True)
    if search:
        s = f"%{search}%"
        query = query.where(
            LLMModel.name.ilike(s) | LLMModel.model_id.ilike(s)
        )

    query = query.order_by(LLMModel.id).offset(offset).limit(limit)
    models_page = session.exec(query).all()
    return [_to_read(m) for m in models_page]


@router.post("/", response_model=ModelRead, status_code=status.HTTP_201_CREATED)
def create_model(payload: ModelCreate, session: Session = Depends(get_session)):
    # Deduplicate by model_id (prevents double-importing same OpenRouter model)
    existing = session.exec(
        select(LLMModel).where(LLMModel.model_id == payload.model_id)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Model '{payload.model_id}' already registered.")

    model = LLMModel(
        name=payload.name,
        provider=payload.provider,
        model_id=payload.model_id,
        endpoint=payload.endpoint,
        api_key_encrypted=encrypt_api_key(payload.api_key) if payload.api_key else None,
        context_length=payload.context_length,
        cost_input_per_1k=payload.cost_input_per_1k,
        cost_output_per_1k=payload.cost_output_per_1k,
        tags=json.dumps(payload.tags),
        notes=payload.notes,
    )
    session.add(model)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        # DB-level UNIQUE constraint violation — safety net for race conditions
        if "UNIQUE" in str(e).upper() or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Model '{payload.model_id}' already registered (concurrent import).")
        raise
    session.refresh(model)
    return _to_read(model)


@router.get("/{model_id}", response_model=ModelRead)
def get_model(model_id: int, session: Session = Depends(get_session)):
    model = session.get(LLMModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")
    return _to_read(model)


@router.patch("/{model_id}", response_model=ModelRead)
def update_model(model_id: int, payload: ModelUpdate, session: Session = Depends(get_session)):
    model = session.get(LLMModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")

    for field, value in payload.model_dump(exclude_none=True).items():
        if field == "api_key":
            model.api_key_encrypted = encrypt_api_key(value) if value else None
        elif field == "tags":
            model.tags = json.dumps(value)
        else:
            setattr(model, field, value)

    model.updated_at = datetime.now(UTC)
    session.add(model)
    session.commit()
    session.refresh(model)
    return _to_read(model)


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(model_id: int, session: Session = Depends(get_session)):
    model = session.get(LLMModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")
    session.delete(model)
    session.commit()


@router.post("/{model_id}/test")
async def test_model_connection(model_id: int, session: Session = Depends(get_session)):
    """Live connection test — returns latency and a sample response."""
    model = session.get(LLMModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")

    from eval_engine.litellm_client import test_connection
    result = await test_connection(model)
    return result


# ── Inference adapter health dashboard ──────────────────────────────────────

@router.get("/inference/adapters")
async def inference_adapter_health():
    """Returns health status of all configured inference providers."""
    from inference.adapter import adapter_health_dashboard
    return {"adapters": await adapter_health_dashboard()}


# ── Unified model explorer ────────────────────────────────────────────────────

@router.get("/explorer")
async def model_explorer(session: Session = Depends(get_session)):
    """
    Unified model explorer — aggregates models from all sources:
    - Database (imported models from OpenRouter, custom, Ollama)
    - Ollama local (live query)
    Returns provenance, access type, and status for each model.
    """
    from core.config import get_settings
    settings = get_settings()
    import httpx

    # 1. All imported models from DB
    db_models = session.exec(select(LLMModel)).all()

    # 2. Ollama locally installed models (live)
    ollama_installed: set[str] = set()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/tags")
            if r.status_code == 200:
                for m in r.json().get("models", []):
                    ollama_installed.add(m["name"].split(":")[0])
    except Exception:
        pass

    result = []
    for m in db_models:
        access_type = (
            "local" if m.provider == "ollama"
            else "open-weight" if m.is_open_weight
            else "api-only"
        )
        result.append({
            "id": m.id,
            "name": m.name,
            "model_id": m.model_id,
            "provider": m.provider,
            "access_type": access_type,
            "is_open_weight": m.is_open_weight,
            "is_free": m.is_free,
            "context_length": m.context_length,
            "supports_vision": m.supports_vision,
            "supports_tools": m.supports_tools,
            "supports_reasoning": m.supports_reasoning,
            "local_available": m.provider == "ollama" or any(
                m.model_id.startswith(n) for n in ollama_installed
            ),
            "ollama_name": next(
                (n for n in ollama_installed if m.model_id.startswith(n)), None
            ),
        })

    return {
        "models": result,
        "total": len(result),
        "ollama_installed": len(ollama_installed),
        "open_weight": sum(1 for m in result if m["is_open_weight"]),
        "api_only": sum(1 for m in result if m["access_type"] == "api-only"),
        "local": sum(1 for m in result if m["access_type"] == "local"),
    }
