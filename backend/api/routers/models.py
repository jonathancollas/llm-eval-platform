"""
Model Registry — CRUD + connection testing.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import json

from core.database import get_session
from core.models import LLMModel, ModelProvider
from core.security import encrypt_api_key, decrypt_api_key
from core.utils import safe_json_load

router = APIRouter(prefix="/models", tags=["models"])


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

@router.get("/", response_model=list[ModelRead])
def list_models(session: Session = Depends(get_session)):
    return [_to_read(m) for m in session.exec(select(LLMModel)).all()]


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

    model.updated_at = datetime.utcnow()
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
