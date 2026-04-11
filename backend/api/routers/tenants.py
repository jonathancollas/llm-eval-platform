"""
Tenant management — INFRA-3
CRUD for tenants and users. Admin-only endpoints.
"""
import json
import logging
import os
import hmac
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from core.database import get_session
from core.models import Tenant, User
from core.auth import hash_api_key, generate_api_key

router = APIRouter(prefix="/tenants", tags=["tenants"])
logger = logging.getLogger(__name__)

_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


def _require_admin(request: Request) -> None:
    """
    Explicit admin-key guard for tenant management endpoints.
    Provides defence-in-depth on top of the global middleware:
    even without the middleware (e.g. during testing) these routes
    are protected when ADMIN_API_KEY is configured.
    In dev mode (no ADMIN_API_KEY set) a warning header is added but
    access is allowed to preserve the current dev-mode behaviour.
    """
    if not _ADMIN_API_KEY:
        # Dev mode — same lenient behaviour as the global middleware.
        return
    key = request.headers.get("X-API-Key", "")
    if not key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header. Admin key required for tenant management.",
        )
    if not hmac.compare_digest(key, _ADMIN_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid admin API key.")


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=50, pattern=r'^[a-z0-9\-]+$')
    plan: str = Field(default="free")


class UserCreate(BaseModel):
    email: str = Field(..., min_length=5, max_length=200)
    name: str = Field(default="")
    role: str = Field(default="viewer")


@router.post("/")
def create_tenant(payload: TenantCreate, session: Session = Depends(get_session), _: None = Depends(_require_admin)):
    """Create a new tenant and return its API key (shown only once)."""
    existing = session.exec(select(Tenant).where(Tenant.slug == payload.slug)).first()
    if existing:
        raise HTTPException(409, detail=f"Tenant slug '{payload.slug}' already exists.")

    api_key = generate_api_key()

    tenant = Tenant(
        name=payload.name,
        slug=payload.slug,
        api_key_hash=hash_api_key(api_key),
        plan=payload.plan,
    )
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "plan": tenant.plan,
        "api_key": api_key,  # Shown only once!
        "warning": "Save this API key — it cannot be retrieved later.",
    }


@router.get("/")
def list_tenants(session: Session = Depends(get_session), _: None = Depends(_require_admin)):
    tenants = session.exec(select(Tenant).where(Tenant.is_active == True)).all()
    return {
        "tenants": [
            {"id": t.id, "name": t.name, "slug": t.slug, "plan": t.plan,
             "max_campaigns": t.max_campaigns, "created_at": t.created_at.isoformat()}
            for t in tenants
        ]
    }


@router.get("/{tenant_id}")
def get_tenant(tenant_id: int, session: Session = Depends(get_session), _: None = Depends(_require_admin)):
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, detail="Tenant not found.")

    users = session.exec(select(User).where(User.tenant_id == tenant_id)).all()

    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "plan": tenant.plan,
        "max_campaigns": tenant.max_campaigns,
        "max_models": tenant.max_models,
        "is_active": tenant.is_active,
        "users": [
            {"id": u.id, "email": u.email, "name": u.name, "role": u.role}
            for u in users
        ],
        "created_at": tenant.created_at.isoformat(),
    }


@router.post("/{tenant_id}/rotate-key")
def rotate_api_key(tenant_id: int, session: Session = Depends(get_session), _: None = Depends(_require_admin)):
    """Rotate tenant API key."""
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, detail="Tenant not found.")

    new_key = generate_api_key()
    tenant.api_key_hash = hash_api_key(new_key)
    session.add(tenant)
    session.commit()

    return {
        "tenant_id": tenant_id,
        "new_api_key": new_key,
        "warning": "Save this API key — the old key is now invalid.",
    }


@router.post("/{tenant_id}/users")
def add_user(tenant_id: int, payload: UserCreate, session: Session = Depends(get_session), _: None = Depends(_require_admin)):
    """Add a user to a tenant."""
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, detail="Tenant not found.")

    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing:
        raise HTTPException(409, detail=f"User '{payload.email}' already exists.")

    user = User(
        tenant_id=tenant_id,
        email=payload.email,
        name=payload.name,
        role=payload.role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    return {"id": user.id, "email": user.email, "role": user.role, "tenant": tenant.name}
