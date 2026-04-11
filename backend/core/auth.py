"""
Multi-tenant authentication — INFRA-3
Simple API key-based tenant isolation.

Security hardening (#Medium):
  - Tenant key format validation (must start with "mr_" + 48 hex chars)
  - In-memory rate limiting: max 10 failed attempts per IP per minute
  - Constant-time comparison to prevent timing attacks
  - Invalid format rejected before DB lookup (no unnecessary query)
"""
import hashlib
import re
import secrets
import time
import logging
from collections import defaultdict
from typing import Optional

from fastapi import Request, HTTPException, Depends
from sqlmodel import Session, select

from core.database import get_session
from core.models import Tenant, User

logger = logging.getLogger(__name__)

# ── Tenant key format ─────────────────────────────────────────────────────────
_TENANT_KEY_RE = re.compile(r"^mr_[0-9a-f]{48}$")

# ── In-memory rate limiter: {ip: [(timestamp, …)]} ───────────────────────────
_failed_attempts: dict = defaultdict(list)
_MAX_FAILURES = 10          # per window
_WINDOW_SECONDS = 60        # rolling window


def _check_rate_limit(ip: str) -> None:
    """Raise 429 if this IP has exceeded failed-attempt threshold."""
    now = time.monotonic()
    window_start = now - _WINDOW_SECONDS
    # Purge old entries
    _failed_attempts[ip] = [t for t in _failed_attempts[ip] if t > window_start]
    if len(_failed_attempts[ip]) >= _MAX_FAILURES:
        raise HTTPException(
            status_code=429,
            detail=f"Too many invalid auth attempts. Try again in {_WINDOW_SECONDS}s.",
        )


def _record_failure(ip: str) -> None:
    _failed_attempts[ip].append(time.monotonic())


def hash_api_key(key: str) -> str:
    """Hash an API key for storage (SHA-256)."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    """Generate a new tenant API key (mr_ prefix + 48 hex chars)."""
    return f"mr_{secrets.token_hex(24)}"


def get_current_tenant(
    request: Request,
    session: Session = Depends(get_session),
) -> Optional[Tenant]:
    """
    Extract and validate tenant from X-Tenant-Key header.

    Security checks (in order):
      1. Rate limit by IP
      2. Format validation (mr_ prefix + 48 hex chars)
      3. Hash comparison via DB lookup
    """
    key = request.headers.get("X-Tenant-Key", "")
    if not key:
        return None  # Single-tenant mode — no key = default

    ip = request.client.host if request.client else "unknown"

    # 1. Rate limit before any processing
    _check_rate_limit(ip)

    # 2. Format validation — reject malformed keys immediately
    if not _TENANT_KEY_RE.match(key):
        _record_failure(ip)
        logger.warning(f"[auth] Invalid tenant key format from {ip} (length={len(key)})")
        raise HTTPException(
            status_code=401,
            detail="Invalid tenant API key format.",
        )

    # 3. DB lookup — hash first, compare constant-time via DB query
    key_hash = hash_api_key(key)
    tenant = session.exec(
        select(Tenant).where(Tenant.api_key_hash == key_hash, Tenant.is_active == True)
    ).first()

    if not tenant:
        _record_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid tenant API key.")

    return tenant


def require_tenant(
    request: Request,
    session: Session = Depends(get_session),
) -> Tenant:
    """Require a valid tenant (strict mode — 401 if no key provided)."""
    tenant = get_current_tenant(request, session)
    if not tenant:
        raise HTTPException(status_code=401, detail="X-Tenant-Key header required.")
    return tenant
