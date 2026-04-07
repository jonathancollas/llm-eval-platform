"""
Multi-tenant authentication — INFRA-3
Simple API key-based tenant isolation.

Usage:
  - Each tenant gets an API key
  - Requests include X-Tenant-Key header
  - All queries are scoped to the tenant

This is scaffolding — production should use JWT/OAuth.
"""
import hashlib
import secrets
import logging
from typing import Optional

from fastapi import Request, HTTPException, Depends
from sqlmodel import Session, select

from core.database import get_session
from core.models import Tenant, User

logger = logging.getLogger(__name__)


def hash_api_key(key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    """Generate a new tenant API key."""
    return f"mr_{secrets.token_hex(24)}"


def get_current_tenant(
    request: Request,
    session: Session = Depends(get_session),
) -> Optional[Tenant]:
    """Extract tenant from X-Tenant-Key header.
    Returns None if multi-tenant is not enabled (single-tenant mode).
    """
    key = request.headers.get("X-Tenant-Key", "")
    if not key:
        # Single-tenant mode: no key = default tenant
        return None

    key_hash = hash_api_key(key)
    tenant = session.exec(
        select(Tenant).where(Tenant.api_key_hash == key_hash, Tenant.is_active == True)
    ).first()

    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid tenant API key.")

    return tenant


def require_tenant(
    request: Request,
    session: Session = Depends(get_session),
) -> Tenant:
    """Require a valid tenant (strict mode)."""
    tenant = get_current_tenant(request, session)
    if not tenant:
        raise HTTPException(status_code=401, detail="X-Tenant-Key header required.")
    return tenant
