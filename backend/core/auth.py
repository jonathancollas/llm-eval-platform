"""
Multi-tenant authentication.

Per-tenant API key with rate-limited, format-validated, constant-time-compared
key lookup. Roles are read from the persisted User row, never from a client
header — a header-based role lookup is an escalation footgun and is no longer
supported.

Rollout strategy
----------------
A boolean env var ``AUTH_ENFORCED`` controls strict mode:

  AUTH_ENFORCED=true   strict — all protected endpoints require X-Tenant-Key.
                       Missing or invalid keys → 401 (or 429 under abuse).
                       This is the production-correct value.

  AUTH_ENFORCED=false  permissive — when no key is provided, the request
                       falls back to the default tenant. When a key IS
                       provided, it is still validated; an invalid key is
                       still rejected. This lets existing clients that
                       never sent a key keep working during rollout.

Default: ``false`` (this PR is the rollout step). After clients migrate, flip
to ``true`` in production via env var.

Set explicitly in your environment:

    AUTH_ENFORCED=true                # for production
    AUTH_ENFORCED=false               # for the rollout window only
    ADMIN_API_KEY=mr_<48 hex chars>   # bootstraps the first tenant

Mitigations vs the old, fully-disabled code:
  - Tenant key format validation (must start with ``mr_`` + 48 hex chars)
  - In-memory rate limiting: max 10 failed attempts per IP per 60s
  - Constant-time DB lookup via SHA-256 hash comparison
  - Invalid format rejected before DB lookup (no unnecessary query)
  - Role gating now reads from the persisted User row, NEVER from a header

Security audit reference: P0-1.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import threading
import time
from collections import defaultdict
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from core.database import get_session
from core.models import Tenant, User

logger = logging.getLogger(__name__)

VALID_ROLES = {"admin", "evaluator", "viewer"}

# ── Configuration ─────────────────────────────────────────────────────────────


def _is_strict_mode() -> bool:
    """Return True if auth is strictly enforced.

    Read at every call (not cached) so tests can monkeypatch the env var.
    """
    return os.getenv("AUTH_ENFORCED", "false").lower() in ("true", "1", "yes")


# ── Tenant key format ─────────────────────────────────────────────────────────

_TENANT_KEY_RE = re.compile(r"^mr_[0-9a-f]{48}$")


# ── In-memory rate limiter ────────────────────────────────────────────────────
# {ip: [monotonic_timestamp, ...]}
# Per-process and per-pod. Adequate for slowing down credential scanning;
# not a substitute for a Redis-backed limiter (audit P1-14, separate PR).

_failed_attempts: dict[str, list[float]] = defaultdict(list)
_failed_attempts_lock = threading.Lock()
_MAX_FAILURES = 10           # per window per IP
_WINDOW_SECONDS = 60         # rolling window
_MAX_TRACKED_IPS = 10_000    # bound memory under IP-cycling scans


def _check_rate_limit(ip: str) -> None:
    """Raise 429 if this IP has exceeded the failed-attempt threshold."""
    now = time.monotonic()
    window_start = now - _WINDOW_SECONDS
    with _failed_attempts_lock:
        # Purge old entries for this IP, then count
        _failed_attempts[ip] = [t for t in _failed_attempts[ip] if t > window_start]
        count = len(_failed_attempts[ip])
    if count >= _MAX_FAILURES:
        raise HTTPException(
            status_code=429,
            detail=f"Too many invalid auth attempts. Try again in {_WINDOW_SECONDS}s.",
        )


def _record_failure(ip: str) -> None:
    """Record a failed auth attempt for rate-limiting. Bounded memory."""
    with _failed_attempts_lock:
        # Evict oldest IP if table is full (Python 3.7+ dict insertion order).
        if ip not in _failed_attempts and len(_failed_attempts) >= _MAX_TRACKED_IPS:
            oldest_ip = next(iter(_failed_attempts))
            del _failed_attempts[oldest_ip]
        _failed_attempts[ip].append(time.monotonic())


# ── Key utilities ─────────────────────────────────────────────────────────────


def hash_api_key(key: str) -> str:
    """Hash an API key for storage (SHA-256 hex digest)."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    """Generate a new tenant API key (`mr_` prefix + 48 hex chars)."""
    return f"mr_{secrets.token_hex(24)}"


# ── Default tenant (permissive-mode fallback only) ────────────────────────────

_DEFAULT_TENANT_SLUG = "default"
_DEFAULT_TENANT_NAME = "Default"


def _get_or_create_default_tenant(session: Session) -> Tenant:
    """Return the default tenant, creating it if missing.

    Used only in permissive (non-strict) mode when no key is presented.
    """
    tenant = session.exec(
        select(Tenant).where(
            Tenant.slug == _DEFAULT_TENANT_SLUG, Tenant.is_active == True  # noqa: E712
        )
    ).first()
    if not tenant:
        tenant = Tenant(
            name=_DEFAULT_TENANT_NAME, slug=_DEFAULT_TENANT_SLUG, api_key_hash=""
        )
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        logger.info("[auth] Default tenant auto-created (permissive mode).")
    return tenant


# ── Public dependencies ───────────────────────────────────────────────────────


def get_current_tenant(
    request: Request,
    session: Session = Depends(get_session),
) -> Optional[Tenant]:
    """Resolve the tenant from the X-Tenant-Key header.

    Returns:
      - The Tenant row when a valid key is presented.
      - ``None`` when no key is presented AND strict mode is OFF.
      - Raises 401 when no key is presented AND strict mode is ON.
      - Raises 401 when an invalid key is presented (any mode).
      - Raises 429 when this IP has too many recent failures (any mode).
    """
    key = request.headers.get("X-Tenant-Key", "")

    if not key:
        if _is_strict_mode():
            raise HTTPException(
                status_code=401, detail="X-Tenant-Key header required."
            )
        return None  # permissive: caller falls back to default tenant

    ip = request.client.host if request.client else "unknown"

    # 1. Rate-limit before doing any DB or crypto work
    _check_rate_limit(ip)

    # 2. Reject malformed keys before DB lookup
    if not _TENANT_KEY_RE.match(key):
        _record_failure(ip)
        logger.warning("[auth] Invalid tenant key format from %s (length=%d)", ip, len(key))
        raise HTTPException(status_code=401, detail="Invalid tenant API key format.")

    # 3. DB lookup by hash. The hash comparison happens inside SQLite/Postgres
    # at the ``=`` operator on indexed bytes — constant-time per row.
    key_hash = hash_api_key(key)
    tenant = session.exec(
        select(Tenant).where(
            Tenant.api_key_hash == key_hash, Tenant.is_active == True  # noqa: E712
        )
    ).first()
    if not tenant:
        _record_failure(ip)
        logger.warning("[auth] Unknown tenant key from %s", ip)
        raise HTTPException(status_code=401, detail="Invalid tenant API key.")
    return tenant


def require_tenant(
    request: Request,
    session: Session = Depends(get_session),
) -> Tenant:
    """Strict version: always returns a Tenant or raises.

    In permissive mode and no key, falls back to the default tenant
    (legacy behavior). In strict mode, missing key → 401.
    """
    tenant = get_current_tenant(request, session)
    if tenant is not None:
        return tenant
    # Permissive mode + no key → default tenant
    return _get_or_create_default_tenant(session)


# ── Roles ─────────────────────────────────────────────────────────────────────


def normalize_role(role: str) -> str:
    """Normalize legacy role aliases and casing."""
    r = (role or "").strip().lower()
    # Backward compatibility: older clients used "runner" for write-capable users.
    if r == "runner":
        return "evaluator"
    return r


def get_user_role(
    request: Request,
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
) -> str:
    """Resolve the calling user's role from the persisted User row.

    Identification flow:
      - When ``X-User-Email`` is present, look up that user within the resolved
        tenant. The user must belong to ``tenant`` — cross-tenant lookup is
        forbidden even if a valid email is provided.
      - When the header is absent and AUTH_ENFORCED is on, return the lowest
        privilege ("viewer").
      - When the header is absent and AUTH_ENFORCED is off, return "evaluator".
        There is no login UI yet; anonymous callers already create campaigns
        and models via require_tenant's default-tenant fallback. Defaulting
        to viewer uniquely 403'd Red Room v2 POSTs from /redbox/v2.

    The previous implementation read a role straight from an X-Role / X-User-Role
    header, which let any caller claim ``admin`` simply by adding a header.
    That endpoint is gone and will not be restored. If you need to identify
    a user, you authenticate the user — not pretend they have a role.
    """
    email = (request.headers.get("X-User-Email") or "").strip().lower()
    if not email:
        # Strict mode: unidentified → least privilege.
        # Permissive/rollout mode: unidentified → evaluator, matching the
        # write access the rest of the app already grants without a User row.
        return "viewer" if _is_strict_mode() else "evaluator"

    user = session.exec(
        select(User).where(
            User.email == email,
            User.tenant_id == tenant.id,
            User.is_active == True,  # noqa: E712
        )
    ).first()
    if not user:
        # Unknown user, or user from a different tenant — no privilege.
        return "viewer"
    return normalize_role(user.role)


def require_role(*allowed: str):
    """Dependency factory: only allow callers whose role is in ``allowed``.

    Usage::

        @router.post("/dangerous", dependencies=[Depends(require_role("admin"))])
        def dangerous(...): ...
    """
    allowed_set = {normalize_role(r) for r in allowed}
    if not allowed_set.issubset(VALID_ROLES):
        raise ValueError(
            f"require_role: unknown role(s) {allowed_set - VALID_ROLES}"
        )

    def _check(role: str = Depends(get_user_role)) -> str:
        if role not in allowed_set:
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden — requires role in {sorted(allowed_set)}.",
            )
        return role

    return _check


# ── Migration helper (called from main.py at startup) ─────────────────────────


def warn_if_unsafe_config() -> None:
    """Emit a startup warning if the configuration is unsafe.

    Called from main.py's startup hook. Doesn't raise — just logs prominently
    so the warning shows up in deployment logs.
    """
    if not _is_strict_mode():
        logger.warning(
            "[auth] AUTH_ENFORCED is OFF — endpoints accept requests without "
            "X-Tenant-Key and fall back to the default tenant. Set "
            "AUTH_ENFORCED=true in production."
        )
    if not os.getenv("ADMIN_API_KEY"):
        logger.warning(
            "[auth] ADMIN_API_KEY is not set — bootstrap admin tenant is not "
            "available. New tenants must be created via direct DB write or "
            "via the /tenants endpoint by an existing admin."
        )


# ── Backward-compat shim (deprecated) ─────────────────────────────────────────


def get_request_role(request: Request) -> str:
    """**DEPRECATED**. Reads role from a client header — fundamentally insecure.

    Kept temporarily so legacy callers don't break at import time. Always
    returns ``"viewer"`` regardless of headers.

    Migrate to ``get_user_role`` (which validates against the User table) or
    ``require_role(...)`` (which gates the endpoint at the dependency layer).
    """
    logger.warning(
        "[auth] get_request_role() is deprecated — returning 'viewer'. "
        "Use Depends(get_user_role) or Depends(require_role(...)) instead."
    )
    return "viewer"
