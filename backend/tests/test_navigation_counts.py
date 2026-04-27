"""Tests for /api/navigation/counts.

Verifies:
  - Known entity types return per-key counts including 0
  - Unknown entity types return 200 with empty dict (graceful degradation)
  - Non-existent entity ids return 200 with empty dict (no info leak)
  - Bad ids return 400
  - Counts reflect actual DB state across model/benchmark/campaign
"""
from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.routers import navigation as nav_router  # noqa: E402
from core.auth import require_tenant  # noqa: E402
from core.database import get_session  # noqa: E402
from core.models import (  # noqa: E402
    Benchmark,
    BenchmarkType,
    Campaign,
    EvalRun,
    LLMModel,
    ModelProvider,
    Tenant,
)


# ═══════════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def session_with_data():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        tenant = Tenant(name="Test", slug="test", api_key_hash="t")
        s.add(tenant)
        s.flush()

        m1 = LLMModel(
            name="gpt-4o-mini",
            provider=ModelProvider.CUSTOM,
            model_id="openai/gpt-4o-mini",
        )
        m2 = LLMModel(
            name="claude-opus",
            provider=ModelProvider.ANTHROPIC,
            model_id="anthropic/claude-opus-4.6",
        )
        s.add_all([m1, m2])
        s.flush()

        b1 = Benchmark(
            name="MMLU",
            type=BenchmarkType.ACADEMIC,
            metric="accuracy",
            num_samples=14000,
        )
        b2 = Benchmark(
            name="CyberSecEval",
            type=BenchmarkType.SAFETY,
            metric="safety_score",
            num_samples=1247,
        )
        s.add_all([b1, b2])
        s.flush()

        c1 = Campaign(name="Test campaign", description="x", status="completed")
        s.add(c1)
        s.flush()

        # Seed runs: 3 for m1×b1, 1 for m1×b2, 0 for m2×*
        for _ in range(3):
            s.add(EvalRun(campaign_id=c1.id, model_id=m1.id, benchmark_id=b1.id, status="completed"))
        s.add(EvalRun(campaign_id=c1.id, model_id=m1.id, benchmark_id=b2.id, status="completed"))
        s.commit()

        # Stash ids for tests
        s.refresh(m1)
        s.refresh(m2)
        s.refresh(b1)
        s.refresh(b2)
        s.refresh(c1)

        yield {
            "session": s,
            "tenant": tenant,
            "m1": m1,
            "m2": m2,
            "b1": b1,
            "b2": b2,
            "c1": c1,
        }


@pytest.fixture
def client(session_with_data):
    app = FastAPI()
    app.include_router(nav_router.router, prefix="/api")

    def _session():
        yield session_with_data["session"]

    def _tenant():
        return session_with_data["tenant"]

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[require_tenant] = _tenant
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
#  Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestModelCounts:
    def test_model_with_runs(self, client, session_with_data):
        m1_id = session_with_data["m1"].id
        r = client.get(f"/api/navigation/counts?entity_type=model&entity_id={m1_id}")
        assert r.status_code == 200
        body = r.json()
        # Model 1 has 4 EvalRuns total (3 on b1 + 1 on b2)
        assert body["runs"] == 4
        # Optional counts default to 0 when those models have no rows
        assert body["redbox"] == 0
        assert body["trajectories"] == 0

    def test_model_with_no_runs(self, client, session_with_data):
        m2_id = session_with_data["m2"].id
        r = client.get(f"/api/navigation/counts?entity_type=model&entity_id={m2_id}")
        assert r.status_code == 200
        assert r.json() == {"runs": 0, "redbox": 0, "trajectories": 0}

    def test_nonexistent_model_returns_empty(self, client):
        r = client.get("/api/navigation/counts?entity_type=model&entity_id=999999")
        assert r.status_code == 200
        assert r.json() == {}


class TestBenchmarkCounts:
    def test_benchmark_with_coverage(self, client, session_with_data):
        b1_id = session_with_data["b1"].id
        r = client.get(f"/api/navigation/counts?entity_type=benchmark&entity_id={b1_id}")
        assert r.status_code == 200
        # b1 has 3 runs (all from m1)
        assert r.json() == {"coverage": 3}

    def test_benchmark_with_no_coverage(self, client, session_with_data):
        # Create a benchmark with zero runs to test the boundary
        sess = session_with_data["session"]
        new_b = Benchmark(
            name="Untested",
            type=BenchmarkType.CUSTOM,
            metric="accuracy",
            num_samples=10,
        )
        sess.add(new_b)
        sess.commit()
        sess.refresh(new_b)

        r = client.get(f"/api/navigation/counts?entity_type=benchmark&entity_id={new_b.id}")
        assert r.status_code == 200
        assert r.json() == {"coverage": 0}


class TestCampaignCounts:
    def test_campaign_with_runs(self, client, session_with_data):
        c1_id = session_with_data["c1"].id
        r = client.get(f"/api/navigation/counts?entity_type=campaign&entity_id={c1_id}")
        assert r.status_code == 200
        # c1 has 4 runs total
        assert r.json() == {"runs": 4}


class TestUnknownEntityType:
    def test_unknown_returns_empty_dict(self, client):
        r = client.get("/api/navigation/counts?entity_type=spaceship&entity_id=42")
        assert r.status_code == 200
        assert r.json() == {}

    def test_no_400_no_404(self, client):
        # Even with garbage entity types, the API stays a 200.
        # The UI just shows links without count badges.
        for kind in ("xyz", "Pluton", "tenant", "scenario"):
            r = client.get(f"/api/navigation/counts?entity_type={kind}&entity_id=1")
            assert r.status_code == 200, f"Failed for entity_type={kind}"


class TestBadInput:
    def test_non_integer_id_returns_400(self, client):
        r = client.get("/api/navigation/counts?entity_type=model&entity_id=not-a-number")
        assert r.status_code == 400

    def test_missing_entity_type_returns_422(self, client):
        r = client.get("/api/navigation/counts?entity_id=1")
        assert r.status_code == 422

    def test_missing_entity_id_returns_422(self, client):
        r = client.get("/api/navigation/counts?entity_type=model")
        assert r.status_code == 422

    def test_oversized_entity_type_rejected(self, client):
        r = client.get(
            "/api/navigation/counts?entity_type=" + "x" * 100 + "&entity_id=1"
        )
        assert r.status_code == 422

    def test_oversized_entity_id_rejected(self, client):
        r = client.get(
            "/api/navigation/counts?entity_type=model&entity_id=" + "1" * 200
        )
        assert r.status_code == 422
