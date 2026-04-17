"""
Tests for core/auth.py
Covers: hash_api_key, generate_api_key, _check_rate_limit, _record_failure,
        normalize_role, get_request_role, _get_or_create_default_tenant.
"""
import os
import re
import secrets
import sys
import time
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from sqlmodel import SQLModel, Session, create_engine
from fastapi import HTTPException
from fastapi.testclient import TestClient
from fastapi import FastAPI, Request

import core.auth as auth_module
from core.auth import (
    hash_api_key,
    generate_api_key,
    normalize_role,
    get_request_role,
    _check_rate_limit,
    _record_failure,
    _TENANT_KEY_RE,
    _MAX_FAILURES,
    _WINDOW_SECONDS,
    _MAX_TRACKED_IPS,
)
from core.models import Tenant


# ── DB fixture ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("auth_tests") / "auth.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture()
def session(db_engine):
    with Session(db_engine) as s:
        yield s


# ── hash_api_key ───────────────────────────────────────────────────────────────

def test_hash_api_key_is_deterministic():
    key = "mr_" + "a" * 48
    assert hash_api_key(key) == hash_api_key(key)


def test_hash_api_key_is_sha256():
    import hashlib
    key = "test-key"
    assert hash_api_key(key) == hashlib.sha256(key.encode()).hexdigest()


def test_hash_api_key_different_inputs_differ():
    assert hash_api_key("key1") != hash_api_key("key2")


def test_hash_api_key_returns_64_hex_chars():
    result = hash_api_key("any-key")
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


# ── generate_api_key ──────────────────────────────────────────────────────────

def test_generate_api_key_format():
    key = generate_api_key()
    assert _TENANT_KEY_RE.match(key), f"Key '{key}' does not match expected format"


def test_generate_api_key_prefix():
    assert generate_api_key().startswith("mr_")


def test_generate_api_key_length():
    key = generate_api_key()
    # "mr_" (3) + 48 hex chars = 51
    assert len(key) == 51


def test_generate_api_key_unique():
    keys = {generate_api_key() for _ in range(20)}
    assert len(keys) == 20


# ── Tenant key regex ──────────────────────────────────────────────────────────

def test_tenant_key_regex_accepts_valid():
    valid = "mr_" + "a" * 48
    assert _TENANT_KEY_RE.match(valid)


def test_tenant_key_regex_rejects_short():
    short = "mr_" + "a" * 47
    assert not _TENANT_KEY_RE.match(short)


def test_tenant_key_regex_rejects_wrong_prefix():
    wrong = "xx_" + "a" * 48
    assert not _TENANT_KEY_RE.match(wrong)


def test_tenant_key_regex_rejects_uppercase():
    upper = "mr_" + "A" * 48
    assert not _TENANT_KEY_RE.match(upper)


def test_tenant_key_regex_rejects_non_hex():
    non_hex = "mr_" + "g" * 48
    assert not _TENANT_KEY_RE.match(non_hex)


# ── normalize_role ────────────────────────────────────────────────────────────

def test_normalize_role_lowercase():
    assert normalize_role("ADMIN") == "admin"


def test_normalize_role_strips_whitespace():
    assert normalize_role("  viewer  ") == "viewer"


def test_normalize_role_runner_alias():
    assert normalize_role("runner") == "evaluator"


def test_normalize_role_runner_uppercase():
    assert normalize_role("RUNNER") == "evaluator"


def test_normalize_role_empty_string():
    assert normalize_role("") == ""


def test_normalize_role_none_like():
    assert normalize_role(None) == ""


def test_normalize_role_evaluator_unchanged():
    assert normalize_role("evaluator") == "evaluator"


# ── get_request_role ──────────────────────────────────────────────────────────

def _make_request(headers: dict) -> Request:
    """Build a minimal FastAPI Request with the given headers."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "query_string": b"",
    }
    return Request(scope)


def test_get_request_role_x_role_header():
    req = _make_request({"X-Role": "admin"})
    assert get_request_role(req) == "admin"


def test_get_request_role_x_user_role_header():
    req = _make_request({"X-User-Role": "evaluator"})
    assert get_request_role(req) == "evaluator"


def test_get_request_role_x_role_takes_priority():
    req = _make_request({"X-Role": "admin", "X-User-Role": "viewer"})
    assert get_request_role(req) == "admin"


def test_get_request_role_defaults_to_viewer():
    req = _make_request({})
    assert get_request_role(req) == "viewer"


def test_get_request_role_runner_alias():
    req = _make_request({"X-Role": "runner"})
    assert get_request_role(req) == "evaluator"


# ── Rate limiter ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_rate_limiter():
    """Reset the in-memory rate limiter between tests."""
    with auth_module._failed_attempts_lock:
        auth_module._failed_attempts.clear()
    yield
    with auth_module._failed_attempts_lock:
        auth_module._failed_attempts.clear()


def test_check_rate_limit_below_threshold_passes():
    ip = "10.0.0.1"
    for _ in range(_MAX_FAILURES - 1):
        _record_failure(ip)
    # Should not raise
    _check_rate_limit(ip)


def test_check_rate_limit_at_threshold_raises():
    ip = "10.0.0.2"
    for _ in range(_MAX_FAILURES):
        _record_failure(ip)
    with pytest.raises(HTTPException) as exc_info:
        _check_rate_limit(ip)
    assert exc_info.value.status_code == 429


def test_check_rate_limit_429_detail_mentions_window():
    ip = "10.0.0.3"
    for _ in range(_MAX_FAILURES):
        _record_failure(ip)
    with pytest.raises(HTTPException) as exc_info:
        _check_rate_limit(ip)
    assert str(_WINDOW_SECONDS) in exc_info.value.detail


def test_record_failure_expires_after_window(monkeypatch):
    """Entries older than WINDOW_SECONDS should be pruned on next check."""
    ip = "10.0.0.4"
    # Inject old timestamps directly (outside the rolling window)
    past = time.monotonic() - _WINDOW_SECONDS - 1
    with auth_module._failed_attempts_lock:
        auth_module._failed_attempts[ip] = [past] * _MAX_FAILURES
    # Should not raise — all entries are expired
    _check_rate_limit(ip)


def test_record_failure_evicts_oldest_ip_when_full():
    """When the table is at capacity, recording a new IP evicts the oldest."""
    # Fill to capacity with fake IPs
    with auth_module._failed_attempts_lock:
        for i in range(_MAX_TRACKED_IPS):
            auth_module._failed_attempts[f"192.168.{i // 256}.{i % 256}"] = [time.monotonic()]

    oldest_ip = next(iter(auth_module._failed_attempts))
    new_ip = "1.2.3.4"
    _record_failure(new_ip)

    with auth_module._failed_attempts_lock:
        assert new_ip in auth_module._failed_attempts
        assert oldest_ip not in auth_module._failed_attempts


def test_rate_limiter_thread_safety():
    """Multiple threads recording failures on the same IP must not corrupt state."""
    ip = "10.0.0.99"
    errors = []

    def record_many():
        try:
            for _ in range(5):
                _record_failure(ip)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=record_many) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    with auth_module._failed_attempts_lock:
        assert len(auth_module._failed_attempts[ip]) <= 50  # 10 threads × 5


# ── _get_or_create_default_tenant ─────────────────────────────────────────────

def test_get_or_create_default_tenant_creates_on_first_call(session):
    from core.auth import _get_or_create_default_tenant, _DEFAULT_TENANT_SLUG
    tenant = _get_or_create_default_tenant(session)
    assert tenant is not None
    assert tenant.slug == _DEFAULT_TENANT_SLUG
    assert tenant.is_active


def test_get_or_create_default_tenant_idempotent(session):
    from core.auth import _get_or_create_default_tenant
    t1 = _get_or_create_default_tenant(session)
    t2 = _get_or_create_default_tenant(session)
    assert t1.id == t2.id
