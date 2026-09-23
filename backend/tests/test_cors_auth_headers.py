"""CORS must allow the headers the browser UI actually sends.

The frontend and API are different origins (localhost:3000 → :8000, and the
Render split deploy). Once NEXT_PUBLIC_API_KEY is set, every call includes
X-API-Key, which forces a preflight. Tenant auth uses X-Tenant-Key and
X-User-Email. If those names are missing from Access-Control-Allow-Headers,
the browser blocks the app before any route runs.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-cors-tests-32-chars!!")
os.environ.setdefault("ADMIN_API_KEY", "")
os.environ.setdefault("MERCURY_DEV_MODE", "true")

import httpx  # noqa: E402
import pytest  # noqa: E402

from main import app  # noqa: E402


async def _preflight(request_headers: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.options(
            "/api/models/",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": request_headers,
            },
        )


@pytest.mark.asyncio
async def test_cors_preflight_allows_auth_headers():
    response = await _preflight("content-type,x-api-key,x-tenant-key,x-user-email")
    assert response.status_code == 200, response.text
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    allowed = response.headers.get("access-control-allow-headers", "").lower()
    for header in ("x-api-key", "x-tenant-key", "x-user-email", "content-type"):
        assert header in allowed, allowed


@pytest.mark.asyncio
async def test_cors_preflight_still_rejects_unknown_headers():
    response = await _preflight("x-not-a-real-header")
    assert response.status_code == 400
    assert "headers" in response.text.lower()
