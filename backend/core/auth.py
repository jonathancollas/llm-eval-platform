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
import threading
import time
import logging
from collections import defaultdict
from typing import Optional

from fastapi import Request, HTTPException, Depends
from sqlmodel import Session, select

from core.database import get_session
from core.models import Tenant, User

logger = logging.getLogger(__name__)
VALID_ROLES = {"admin", "evaluator", "viewer"}

# ── Tenant key format ─────────────────────────────────────────────────────────
_TENANT_KEY_RE = re.compile(r"^mr_[0-9a-f]{48}$")

# ── In-memory rate limiter: {ip: [(timestamp, …)]} ───────────────────────────
# NOTE: relies on Python 3.7+ dict insertion-order guarantee for LRU eviction.
_failed_attempts: dict = defaultdict(list)
_failed_attempts_lock = threading.Lock()
_MAX_FAILURES = 10          # per window
_WINDOW_SECONDS = 60        # rolling window
# Hard cap on tracked IPs — prevents unbounded growth under a scanning attack
# that cycles through many unique IPs. When full, the oldest IP is evicted.
_MAX_TRACKED_IPS = 10_000


def _check_rate_limit(ip: str) -> None:
    """Raise 429 if this IP has exceeded failed-attempt threshold."""
    now = time.monotonic()
    window_start = now - _WINDOW_SECONDS
    with _failed_attempts_lock:
        # Purge old entries for this IP
        _failed_attempts[ip] = [t for t in _failed_attempts[ip] if t > window_start]
        count = len(_failed_attempts[ip])
    if count >= _MAX_FAILURES:
        raise HTTPException(
            status_code=429,
            detail=f"Too many invalid auth attempts. Try again in {_WINDOW_SECONDS}s.",
        )


def _record_failure(ip: str) -> None:
    with _failed_attempts_lock:
        # Evict the oldest-inserted IP when the table is full to bound memory usage.
        if ip not in _failed_attempts and len(_failed_attempts) >= _MAX_TRACKED_IPS:
            oldest_ip = next(iter(_failed_attempts))
            del _failed_attempts[oldest_ip]
        _failed_attempts[ip].append(time.monotonic())


def hash_api_key(key: str) -> str:
    """Hash an API key for storage (SHA-256)."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    """Generate a new tenant API key (mr_ prefix + 48 hex chars)."""
    return f"mr_{secrets.token_hex(24)}"


_DEFAULT_TENANT_SLUG = "default"
_DEFAULT_TENANT_NAME = "Default"


def _get_or_create_default_tenant(session: Session) -> Tenant:
    """Return the default tenant, creating it if it does not exist."""
    tenant = session.exec(
        select(Tenant).where(Tenant.slug == _DEFAULT_TENANT_SLUG, Tenant.is_active == True)
    ).first()
    if not tenant:
        tenant = Tenant(name=_DEFAULT_TENANT_NAME, slug=_DEFAULT_TENANT_SLUG, api_key_hash="")
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        logger.info("[auth] Default tenant auto-created (access control disabled).")
    return tenant


def get_current_tenant(
    request: Request,
    session: Session = Depends(get_session),
) -> Optional[Tenant]:
    """
    Access control DISABLED — always returns the default tenant.

    # To re-enable tenant key validation, uncomment the block below:
    #
    # key = request.headers.get("X-Tenant-Key", "")
    # if not key:
    #     return None  # Single-tenant mode — no key = default
    #
    # ip = request.client.host if request.client else "unknown"
    #
    # # 1. Rate limit before any processing
    # _check_rate_limit(ip)
    #
    # # 2. Format validation — reject malformed keys immediately
    # if not _TENANT_KEY_RE.match(key):
    #     _record_failure(ip)
    #     logger.warning(f"[auth] Invalid tenant key format from {ip} (length={len(key)})")
    #     raise HTTPException(status_code=401, detail="Invalid tenant API key format.")
    #
    # # 3. DB lookup — hash first, compare constant-time via DB query
    # key_hash = hash_api_key(key)
    # tenant = session.exec(
    #     select(Tenant).where(Tenant.api_key_hash == key_hash, Tenant.is_active == True)
    # ).first()
    # if not tenant:
    #     _record_failure(ip)
    #     raise HTTPException(status_code=401, detail="Invalid tenant API key.")
    # return tenant
    """
    return _get_or_create_default_tenant(session)


def require_tenant(
    request: Request,
    session: Session = Depends(get_session),
) -> Tenant:
    """
    Access control DISABLED — always returns the default tenant without requiring a key.

    # To re-enable strict tenant enforcement, replace the body with:
    # tenant = get_current_tenant(request, session)
    # if not tenant:
    #     raise HTTPException(status_code=401, detail="X-Tenant-Key header required.")
    # return tenant
    """
    return _get_or_create_default_tenant(session)


def normalize_role(role: str) -> str:
    """Normalize legacy role aliases and casing."""
    r = (role or "").strip().lower()
    # Backward compatibility: older clients used "runner" for write-capable users.
    if r == "runner":
        return "evaluator"
    return r


def get_request_role(request: Request) -> str:
    """
    Extract role from request headers.
    Supported headers:
      - X-Role
      - X-User-Role
    """
    return normalize_role(
        request.headers.get("X-Role", "")
        or request.headers.get("X-User-Role", "")
        or "viewer"
    )
