import os
import sys
import secrets

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from core.auth import get_current_tenant, hash_api_key, require_tenant
from core.models import Tenant, Workspace


@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("auth_test") / "auth.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine):
    test_app = FastAPI()

    def _get_session():
        with Session(db_engine) as session:
            yield session

    def _require_tenant_override(request: Request):
        with Session(db_engine) as session:
            tenant = get_current_tenant(request, session)
            if not tenant:
                raise HTTPException(status_code=401, detail="X-Tenant-Key header required.")
            return tenant

    @test_app.get("/secure")
    def secure_endpoint(tenant: Tenant = Depends(require_tenant)):
        return {"tenant_id": tenant.id}

    @test_app.get("/workspaces/{workspace_id}")
    def get_workspace(workspace_id: int, tenant: Tenant = Depends(require_tenant), session: Session = Depends(_get_session)):
        workspace = session.get(Workspace, workspace_id)
        if not workspace or workspace.tenant_id != tenant.id:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        return {"id": workspace.id, "tenant_id": workspace.tenant_id}

    test_app.dependency_overrides[require_tenant] = _require_tenant_override
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def seeded_tenants(db_engine):
    tenant_a_key = "mr_" + "a" * 48
    tenant_b_key = "mr_" + "b" * 48
    with Session(db_engine) as session:
        tenant_a = Tenant(name="Tenant A", slug="tenant-a", api_key_hash=hash_api_key(tenant_a_key))
        tenant_b = Tenant(name="Tenant B", slug="tenant-b", api_key_hash=hash_api_key(tenant_b_key))
        session.add(tenant_a)
        session.add(tenant_b)
        session.commit()
        session.refresh(tenant_a)
        session.refresh(tenant_b)

        workspace_a = Workspace(name="WS A", slug="ws-a", tenant_id=tenant_a.id)
        workspace_b = Workspace(name="WS B", slug="ws-b", tenant_id=tenant_b.id)
        session.add(workspace_a)
        session.add(workspace_b)
        session.commit()
        session.refresh(workspace_a)
        session.refresh(workspace_b)

        return {
            "tenant_a_key": tenant_a_key,
            "tenant_b_key": tenant_b_key,
            "workspace_a_id": workspace_a.id,
            "workspace_b_id": workspace_b.id,
        }


def test_unauthenticated_request_returns_401(client):
    response = client.get("/secure")
    assert response.status_code == 401
    assert "X-Tenant-Key header required" in response.json()["detail"]


def test_tenant_a_cannot_read_tenant_b_data(client, seeded_tenants):
    response = client.get(
        f"/workspaces/{seeded_tenants['workspace_b_id']}",
        headers={"X-Tenant-Key": seeded_tenants["tenant_a_key"]},
    )
    assert response.status_code == 404


def test_tenant_can_read_its_own_data(client, seeded_tenants):
    response = client.get(
        f"/workspaces/{seeded_tenants['workspace_a_id']}",
        headers={"X-Tenant-Key": seeded_tenants["tenant_a_key"]},
    )
    assert response.status_code == 200
    assert response.json()["tenant_id"] is not None
