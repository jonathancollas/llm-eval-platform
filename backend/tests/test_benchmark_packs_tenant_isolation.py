"""Benchmark pack tenant isolation.

GET /benchmarks/packs/{slug} previously returned every version for a slug with
no tenant or is_public check, so a private pack's benchmark_ids leaked by slug.
Create also left tenant_id unset, and same-slug public creates could poison
"latest" for another tenant's pack lineage.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import uuid

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-benchmark-packs-tenant-32b")

from core.auth import require_tenant  # noqa: E402
from core.models import (  # noqa: E402
    Benchmark,
    BenchmarkPack,
    BenchmarkType,
    Tenant,
)

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")


def _load_module(name: str, rel_path: str):
    path = os.path.join(BACKEND_DIR, rel_path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


benchmarks = _load_module("benchmark_packs_tenant_isolation_module", "api/routers/benchmarks.py")


def _seed(engine):
    with Session(engine) as session:
        tenant_a = Tenant(
            name="Tenant A",
            slug=f"ta-{uuid.uuid4().hex[:8]}",
            api_key_hash="hash-a",
        )
        tenant_b = Tenant(
            name="Tenant B",
            slug=f"tb-{uuid.uuid4().hex[:8]}",
            api_key_hash="hash-b",
        )
        bench = Benchmark(
            name=f"b-{uuid.uuid4().hex[:8]}",
            type=BenchmarkType.CUSTOM,
            is_builtin=False,
        )
        session.add(tenant_a)
        session.add(tenant_b)
        session.add(bench)
        session.commit()
        session.refresh(tenant_a)
        session.refresh(tenant_b)
        session.refresh(bench)

        secret_slug = f"secret-pack-{uuid.uuid4().hex[:8]}"
        private_pack = BenchmarkPack(
            name="Secret Internal Pack",
            slug=secret_slug,
            version="1.0.0",
            publisher="Lab A",
            family="internal",
            changelog="Private suite.",
            benchmark_ids_json=f"[{bench.id}]",
            is_public=False,
            tenant_id=tenant_a.id,
        )
        session.add(private_pack)
        session.commit()
        session.refresh(private_pack)

        return {
            "tenant_a_slug": tenant_a.slug,
            "tenant_b_slug": tenant_b.slug,
            "tenant_a_id": tenant_a.id,
            "tenant_b_id": tenant_b.id,
            "benchmark_id": bench.id,
            "secret_slug": secret_slug,
            "private_pack_id": private_pack.id,
        }


def _setup():
    db_path = f"/tmp/bench-packs-tenant-{uuid.uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    ids = _seed(engine)

    app = FastAPI()
    app.include_router(benchmarks.router)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    def _require_tenant_override(
        tenant_key: str | None = Header(default=None, alias="X-Tenant-Key"),
    ):
        if not tenant_key:
            raise HTTPException(status_code=401, detail="X-Tenant-Key header required.")
        with Session(engine) as session:
            tenant = session.exec(select(Tenant).where(Tenant.slug == tenant_key)).first()
            if not tenant:
                raise HTTPException(status_code=401, detail="Invalid tenant.")
            return Tenant(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                api_key_hash=tenant.api_key_hash,
                is_active=tenant.is_active,
            )

    app.dependency_overrides[benchmarks.get_session] = _get_session_override
    app.dependency_overrides[benchmarks.require_tenant] = _require_tenant_override
    app.dependency_overrides[require_tenant] = _require_tenant_override

    return TestClient(app), engine, ids


def test_owner_can_read_private_pack_by_slug():
    client, _engine, ids = _setup()
    r = client.get(
        f"/benchmarks/packs/{ids['secret_slug']}",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["latest_version"] == "1.0.0"
    assert ids["benchmark_id"] in body["benchmark_ids"]


def test_other_tenant_cannot_read_private_pack_by_slug():
    client, _engine, ids = _setup()
    r = client.get(
        f"/benchmarks/packs/{ids['secret_slug']}",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 404
    assert ids["secret_slug"] not in r.text or "not found" in r.text.lower()
    assert str(ids["benchmark_id"]) not in r.text


def test_other_tenant_list_excludes_private_pack():
    client, _engine, ids = _setup()
    r = client.get(
        "/benchmarks/packs",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 200, r.text
    packs = r.json()["packs"]
    assert all(p["slug"] != ids["secret_slug"] for p in packs)
    assert all(p.get("is_public") for p in packs) or packs == []


def test_create_stamps_tenant_and_lists_own_private_pack():
    client, _engine, ids = _setup()
    slug = f"owned-{uuid.uuid4().hex[:8]}"
    create = client.post(
        "/benchmarks/packs",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={
            "name": "Tenant B Private",
            "slug": slug,
            "version": "0.1.0",
            "publisher": "Lab B",
            "family": "lab-b",
            "changelog": "mine",
            "benchmark_ids": [ids["benchmark_id"]],
            "is_public": False,
        },
    )
    assert create.status_code == 201, create.text
    assert create.json()["tenant_id"] == ids["tenant_b_id"]

    listed = client.get(
        "/benchmarks/packs",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert listed.status_code == 200, listed.text
    assert any(p["slug"] == slug for p in listed.json()["packs"])

    other = client.get(
        f"/benchmarks/packs/{slug}",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert other.status_code == 404


def test_cannot_poison_foreign_slug_with_public_pack():
    client, _engine, ids = _setup()
    r = client.post(
        "/benchmarks/packs",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={
            "name": "Poisoned Pack",
            "slug": ids["secret_slug"],
            "version": "9.9.9",
            "publisher": "Attacker",
            "family": "evil",
            "changelog": "takeover",
            "benchmark_ids": [ids["benchmark_id"]],
            "is_public": True,
        },
    )
    assert r.status_code == 409, r.text

    owner = client.get(
        f"/benchmarks/packs/{ids['secret_slug']}",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert owner.status_code == 200, owner.text
    assert owner.json()["latest_version"] == "1.0.0"
