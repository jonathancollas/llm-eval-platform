"""
Real auth tests — exercise the actual require_tenant function, not a mock.

The pre-existing test_campaign_tenant_isolation.py overrode require_tenant
with a fake passing implementation, which masked the fact that the prod
require_tenant was entirely commented out. CI was green; prod was wide open.
This file does NOT use dependency_overrides on require_tenant — it uses the
real one, against an in-memory tenant table.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.auth import (  # noqa: E402
    _check_rate_limit,
    _failed_attempts,
    _record_failure,
    generate_api_key,
    get_current_tenant,
    hash_api_key,
    require_tenant,
)
from core.database import get_session  # noqa: E402
from core.models import Tenant, User  # noqa: E402


# ─── Fixtures ──────────────────────────────────────────────────────────────


from sqlalchemy.pool import StaticPool


@pytest.fixture
def engine():
    """Fresh in-memory engine per test, with all tables created.

    StaticPool ensures all connections share the same in-memory DB —
    without it, each new connection sees an empty database.
    """
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    """A long-lived session for the test body to insert fixtures with."""
    with Session(engine) as s:
        yield s


@pytest.fixture
def tenant_with_key(session: Session):
    """Insert a tenant with a known API key. Returns (tenant, raw_key)."""
    raw_key = generate_api_key()
    t = Tenant(
        name="Acme",
        slug="acme",
        api_key_hash=hash_api_key(raw_key),
        is_active=True,
    )
    session.add(t)
    session.commit()
    session.refresh(t)
    return t, raw_key


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear the in-memory failed-attempts table between tests."""
    _failed_attempts.clear()
    yield
    _failed_attempts.clear()


@pytest.fixture
def strict_mode(monkeypatch):
    """Set AUTH_ENFORCED=true."""
    monkeypatch.setenv("AUTH_ENFORCED", "true")


@pytest.fixture
def permissive_mode(monkeypatch):
    """Set AUTH_ENFORCED=false."""
    monkeypatch.setenv("AUTH_ENFORCED", "false")


@pytest.fixture
def app(engine, session):
    """A FastAPI app exposing a single endpoint that uses the REAL require_tenant.

    NO dependency_overrides on require_tenant — this is the whole point of the
    test file. We only override get_session to bind the in-memory test DB.

    Each request opens a fresh Session bound to the test engine.
    """
    app = FastAPI()

    @app.get("/protected")
    def protected_endpoint(tenant: Tenant = Depends(require_tenant)):
        return {"tenant_slug": tenant.slug, "tenant_id": tenant.id}

    def _session_override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session_override
    return app


# Imported here so the @app fixture above can use Depends
from fastapi import Depends  # noqa: E402


# ─── Permissive mode (rollout default) ─────────────────────────────────────


class TestPermissiveMode:
    """When AUTH_ENFORCED=false, no key falls back to the default tenant."""

    def test_no_key_returns_default_tenant(self, app, permissive_mode):
        client = TestClient(app)
        r = client.get("/protected")
        assert r.status_code == 200
        assert r.json()["tenant_slug"] == "default"

    def test_valid_key_resolves_to_real_tenant(
        self, app, permissive_mode, tenant_with_key
    ):
        tenant, raw_key = tenant_with_key
        client = TestClient(app)
        r = client.get("/protected", headers={"X-Tenant-Key": raw_key})
        assert r.status_code == 200
        assert r.json()["tenant_slug"] == "acme"
        assert r.json()["tenant_id"] == tenant.id

    def test_invalid_format_rejected_even_in_permissive(self, app, permissive_mode):
        """Even when permissive, a malformed key is still 401."""
        client = TestClient(app)
        r = client.get("/protected", headers={"X-Tenant-Key": "not-a-real-key"})
        assert r.status_code == 401
        assert "format" in r.json()["detail"].lower()

    def test_unknown_valid_format_key_rejected(self, app, permissive_mode):
        """A well-formatted key that doesn't match any tenant is 401."""
        client = TestClient(app)
        bogus = generate_api_key()  # well-formed but not in DB
        r = client.get("/protected", headers={"X-Tenant-Key": bogus})
        assert r.status_code == 401
        assert "Invalid tenant API key" in r.json()["detail"]


# ─── Strict mode (production target) ────────────────────────────────────────


class TestStrictMode:
    """When AUTH_ENFORCED=true, missing key is 401 and there is no default fallback."""

    def test_no_key_is_401_in_strict_mode(self, app, strict_mode):
        client = TestClient(app)
        r = client.get("/protected")
        assert r.status_code == 401
        assert "X-Tenant-Key" in r.json()["detail"]

    def test_valid_key_works_in_strict_mode(
        self, app, strict_mode, tenant_with_key
    ):
        _, raw_key = tenant_with_key
        client = TestClient(app)
        r = client.get("/protected", headers={"X-Tenant-Key": raw_key})
        assert r.status_code == 200
        assert r.json()["tenant_slug"] == "acme"

    def test_invalid_key_is_401_in_strict_mode(self, app, strict_mode):
        client = TestClient(app)
        r = client.get("/protected", headers={"X-Tenant-Key": "mr_short"})
        assert r.status_code == 401


# ─── Rate limiting ──────────────────────────────────────────────────────────


class TestRateLimiting:
    """The rate limiter must trip on repeated bad keys from the same IP."""

    def test_rate_limit_after_threshold_failures(self, app, strict_mode):
        client = TestClient(app)
        # 10 bad attempts to the same IP — the 11th should be 429
        bad_key = generate_api_key()  # well-formed but unknown → records failure
        for i in range(10):
            r = client.get("/protected", headers={"X-Tenant-Key": bad_key})
            assert r.status_code == 401, f"attempt {i + 1} should be 401, got {r.status_code}"

        r = client.get("/protected", headers={"X-Tenant-Key": bad_key})
        assert r.status_code == 429, f"11th attempt should be 429, got {r.status_code}"
        assert "Too many" in r.json()["detail"]

    def test_rate_limit_does_not_block_valid_key_after_failures(
        self, app, strict_mode, tenant_with_key
    ):
        """A valid key from the same IP should still work, but only once we've
        actually consumed the bad-attempts counter — the rate limiter triggers
        BEFORE key validation, so a tripped limit blocks even valid keys.
        That's by design: a scanner shouldn't be able to bypass the limiter
        by occasionally guessing a real key.

        This test documents the current behavior.
        """
        _, raw_key = tenant_with_key
        client = TestClient(app)
        # Trigger the limit
        bad_key = generate_api_key()
        for _ in range(10):
            client.get("/protected", headers={"X-Tenant-Key": bad_key})
        # Now even the valid key should be rate-limited
        r = client.get("/protected", headers={"X-Tenant-Key": raw_key})
        assert r.status_code == 429

    def test_format_failures_also_rate_limited(self, app, strict_mode):
        """Format-invalid keys must also count toward the rate limit, otherwise
        a scanner could avoid being throttled by sending obviously-wrong keys.
        """
        client = TestClient(app)
        for _ in range(10):
            client.get("/protected", headers={"X-Tenant-Key": "garbage"})
        # 11th request → 429 because the format failures all bumped the counter
        r = client.get("/protected", headers={"X-Tenant-Key": "garbage"})
        assert r.status_code == 429


# ─── Inactive tenant ────────────────────────────────────────────────────────


class TestInactiveTenant:
    def test_inactive_tenant_is_not_resolved(
        self, app, strict_mode, session: Session
    ):
        raw_key = generate_api_key()
        t = Tenant(
            name="Disabled",
            slug="disabled",
            api_key_hash=hash_api_key(raw_key),
            is_active=False,
        )
        session.add(t)
        session.commit()
        client = TestClient(app)
        r = client.get("/protected", headers={"X-Tenant-Key": raw_key})
        assert r.status_code == 401


# ─── Header-based role escalation must NOT work ─────────────────────────────


class TestRoleEscalationProhibited:
    """The old code read X-Role / X-User-Role from headers — fixed in this PR.

    These tests guard against a regression where someone re-introduces
    header-based role lookups.
    """

    def test_x_role_header_is_ignored(self, app, permissive_mode):
        """Setting X-Role: admin must NOT escalate the request.

        The endpoint here doesn't gate by role, so the test only verifies that
        the header doesn't change tenant resolution. The role resolution itself
        is tested separately in the role tests below.
        """
        client = TestClient(app)
        r1 = client.get("/protected", headers={"X-Role": "admin"})
        r2 = client.get("/protected")
        # Same response regardless of X-Role
        assert r1.status_code == r2.status_code == 200
        assert r1.json() == r2.json()


# ─── Role gating via require_role ────────────────────────────────────────────


class TestRoleGating:
    """require_role(...) must read role from User table, never from headers."""

    @pytest.fixture
    def app_with_role_endpoint(self, engine, session):
        from core.auth import require_role
        from fastapi import Depends, FastAPI

        a = FastAPI()

        @a.get("/admin-only", dependencies=[Depends(require_role("admin"))])
        def admin_only():
            return {"ok": True}

        @a.get("/evaluator-or-admin", dependencies=[Depends(require_role("evaluator", "admin"))])
        def eval_or_admin():
            return {"ok": True}

        def _session_override():
            with Session(engine) as s:
                yield s

        a.dependency_overrides[get_session] = _session_override
        return a

    def test_no_user_email_cannot_admin_in_permissive(
        self, app_with_role_endpoint, permissive_mode
    ):
        """Without X-User-Email, permissive mode is evaluator — not admin."""
        client = TestClient(app_with_role_endpoint)
        r = client.get("/admin-only")
        assert r.status_code == 403

    def test_no_user_email_can_evaluate_in_permissive(
        self, app_with_role_endpoint, permissive_mode
    ):
        """Rollout mode has no login UI; evaluator writes must still work."""
        client = TestClient(app_with_role_endpoint)
        r = client.get("/evaluator-or-admin")
        assert r.status_code == 200

    def test_no_user_email_is_viewer_in_strict(
        self, app_with_role_endpoint, strict_mode, tenant_with_key
    ):
        """Strict mode keeps least privilege when the caller is unidentified."""
        _, raw_key = tenant_with_key
        client = TestClient(app_with_role_endpoint)
        r = client.get(
            "/evaluator-or-admin", headers={"X-Tenant-Key": raw_key}
        )
        assert r.status_code == 403

    def test_x_role_header_does_not_escalate(
        self, app_with_role_endpoint, permissive_mode
    ):
        """Sending X-Role: admin must NOT bypass the role check."""
        client = TestClient(app_with_role_endpoint)
        r = client.get("/admin-only", headers={"X-Role": "admin"})
        assert r.status_code == 403  # not 200

    def test_user_role_resolved_from_db(
        self, app_with_role_endpoint, permissive_mode, session: Session
    ):
        """A real admin User in the default tenant should pass."""
        # The default tenant is created lazily — trigger it once
        client = TestClient(app_with_role_endpoint)
        client.get("/admin-only")  # creates the default tenant

        from sqlmodel import select as sqlsel
        default = session.exec(
            sqlsel(Tenant).where(Tenant.slug == "default")
        ).first()
        assert default is not None
        admin = User(
            tenant_id=default.id,
            email="alice@acme.test",
            name="Alice",
            role="admin",
            is_active=True,
        )
        session.add(admin)
        session.commit()

        r = client.get(
            "/admin-only", headers={"X-User-Email": "alice@acme.test"}
        )
        assert r.status_code == 200

    def test_user_from_other_tenant_is_blocked(
        self, app_with_role_endpoint, permissive_mode, session: Session
    ):
        """A real admin User but in a DIFFERENT tenant must NOT escalate.

        This guards against cross-tenant role leakage: someone who knows
        an admin email at tenant B cannot use it to admin tenant A.
        """
        # Create two tenants and an admin user in tenant B
        tenant_b_key = generate_api_key()
        tenant_b = Tenant(
            name="B", slug="bbb", api_key_hash=hash_api_key(tenant_b_key)
        )
        session.add(tenant_b)
        session.commit()
        session.refresh(tenant_b)

        admin_b = User(
            tenant_id=tenant_b.id,
            email="admin@b.test",
            name="Admin B",
            role="admin",
            is_active=True,
        )
        session.add(admin_b)
        session.commit()

        client = TestClient(app_with_role_endpoint)
        # Hit endpoint with NO tenant key → resolves to default tenant.
        # X-User-Email of admin_b: must NOT be found because admin_b is in
        # tenant B, while the request resolves to default tenant.
        r = client.get(
            "/admin-only", headers={"X-User-Email": "admin@b.test"}
        )
        assert r.status_code == 403

    def test_evaluator_can_call_evaluator_endpoint(
        self, app_with_role_endpoint, permissive_mode, session: Session
    ):
        client = TestClient(app_with_role_endpoint)
        client.get("/evaluator-or-admin")  # ensure default tenant exists

        from sqlmodel import select as sqlsel
        default = session.exec(
            sqlsel(Tenant).where(Tenant.slug == "default")
        ).first()
        u = User(
            tenant_id=default.id,
            email="bob@acme.test",
            name="Bob",
            role="evaluator",
            is_active=True,
        )
        session.add(u)
        session.commit()

        r = client.get(
            "/evaluator-or-admin", headers={"X-User-Email": "bob@acme.test"}
        )
        assert r.status_code == 200


# ─── Hash + key-generation utilities ────────────────────────────────────────


class TestKeyUtilities:
    def test_generate_api_key_format(self):
        for _ in range(20):
            k = generate_api_key()
            assert k.startswith("mr_")
            assert len(k) == 51  # "mr_" + 48 hex chars
            assert all(c in "0123456789abcdef" for c in k[3:])

    def test_hash_api_key_is_deterministic(self):
        k = generate_api_key()
        assert hash_api_key(k) == hash_api_key(k)

    def test_hash_api_key_differs_per_input(self):
        k1 = generate_api_key()
        k2 = generate_api_key()
        assert hash_api_key(k1) != hash_api_key(k2)

    def test_hash_is_64_hex_chars(self):
        h = hash_api_key("anything")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
