"""Tests for the Benchmark Task Registry (M2-P1)."""
from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

# ---------------------------------------------------------------------------
# Task Registry (pure Python)
# ---------------------------------------------------------------------------

from eval_engine.task_registry import (
    TaskEntry,
    TaskRegistry,
    task_registry,
    seed_from_ontology,
    build_default_registry,
)
from eval_engine.capability_taxonomy import CAPABILITY_ONTOLOGY


class TestTaskEntry:
    def test_defaults(self):
        t = TaskEntry(
            canonical_id="public:mmlu:world_history",
            name="World History",
            description="Multi-choice history questions.",
        )
        assert t.canonical_id == "public:mmlu:world_history"
        assert t.namespace == "public"
        assert t.difficulty == "medium"
        assert t.contamination_risk == "low"
        assert t.capability_tags == []
        assert t.dependencies == []

    def test_canonical_id_format(self):
        t = TaskEntry(canonical_id="inesia:cyber_uplift:heap_overflow_001", name="x", description="")
        parts = t.canonical_id.split(":")
        assert len(parts) == 3

    def test_custom_fields(self):
        t = TaskEntry(
            canonical_id="community:custom:my_task",
            name="Custom Task",
            description="Testing a custom task.",
            domain="reasoning",
            capability_tags=["reasoning", "logical"],
            difficulty="hard",
            contamination_risk="high",
            required_environment="sandbox",
            dependencies=["docker", "python3"],
            license="MIT",
        )
        assert t.domain == "reasoning"
        assert "logical" in t.capability_tags
        assert t.difficulty == "hard"
        assert t.contamination_risk == "high"
        assert "docker" in t.dependencies


class TestTaskRegistry:
    def _fresh(self) -> TaskRegistry:
        return TaskRegistry()

    def test_register_and_get(self):
        reg = self._fresh()
        task = TaskEntry(canonical_id="public:test:task1", name="T1", description="")
        reg.register(task)
        assert reg.get("public:test:task1") is task

    def test_get_missing_returns_none(self):
        reg = self._fresh()
        assert reg.get("nonexistent:id:here") is None

    def test_register_many_returns_count(self):
        reg = self._fresh()
        tasks = [
            TaskEntry(canonical_id=f"public:bench:task{i}", name=f"T{i}", description="")
            for i in range(5)
        ]
        n = reg.register_many(tasks)
        assert n == 5
        assert len(reg.list_all()) == 5

    def test_register_overwrites_existing(self):
        reg = self._fresh()
        t1 = TaskEntry(canonical_id="public:x:t1", name="Old", description="")
        t2 = TaskEntry(canonical_id="public:x:t1", name="New", description="")
        reg.register(t1)
        reg.register(t2)
        assert reg.get("public:x:t1").name == "New"
        assert len(reg.list_all()) == 1

    def test_query_by_domain(self):
        reg = self._fresh()
        reg.register(TaskEntry(canonical_id="public:a:t1", name="T1", description="", domain="reasoning"))
        reg.register(TaskEntry(canonical_id="public:b:t2", name="T2", description="", domain="safety"))
        results = reg.query(domain="reasoning")
        assert len(results) == 1
        assert results[0].domain == "reasoning"

    def test_query_by_difficulty(self):
        reg = self._fresh()
        reg.register(TaskEntry(canonical_id="p:a:t1", name="", description="", difficulty="easy"))
        reg.register(TaskEntry(canonical_id="p:b:t2", name="", description="", difficulty="expert"))
        assert len(reg.query(difficulty="easy")) == 1
        assert len(reg.query(difficulty="expert")) == 1

    def test_query_by_capability_partial_match(self):
        reg = self._fresh()
        reg.register(TaskEntry(
            canonical_id="p:a:t1", name="", description="",
            capability_tags=["cybersecurity", "exploit_generation"]
        ))
        reg.register(TaskEntry(
            canonical_id="p:b:t2", name="", description="",
            capability_tags=["reasoning", "logical"]
        ))
        cyber = reg.query(capability="cybersecurity")
        assert len(cyber) == 1
        # Partial sub-string match
        exp = reg.query(capability="exploit")
        assert len(exp) == 1

    def test_query_search(self):
        reg = self._fresh()
        reg.register(TaskEntry(canonical_id="p:a:t1", name="Heap Overflow", description="buffer issues"))
        reg.register(TaskEntry(canonical_id="p:b:t2", name="SQL Injection", description="db attacks"))
        assert len(reg.query(search="heap")) == 1
        assert len(reg.query(search="buffer")) == 1
        assert len(reg.query(search="attacks")) == 1
        assert len(reg.query(search="overflow")) == 1

    def test_query_no_filters_returns_all(self):
        reg = self._fresh()
        reg.register_many([
            TaskEntry(canonical_id=f"p:x:t{i}", name=f"T{i}", description="") for i in range(3)
        ])
        assert len(reg.query()) == 3

    def test_stats_structure(self):
        reg = self._fresh()
        reg.register(TaskEntry(
            canonical_id="p:a:t1", name="", description="",
            domain="reasoning", difficulty="hard",
            namespace="public", capability_tags=["reasoning"]
        ))
        stats = reg.stats()
        assert stats["total"] == 1
        assert stats["by_domain"]["reasoning"] == 1
        assert stats["by_difficulty"]["hard"] == 1
        assert stats["by_namespace"]["public"] == 1
        assert any(cap == "reasoning" for cap, _ in stats["top_capabilities"])


class TestSeedFromOntology:
    def test_seeds_all_domains(self):
        reg = TaskRegistry()
        n = seed_from_ontology(reg)
        assert n > 0
        domains_present = {t.domain for t in reg.list_all()}
        for domain in CAPABILITY_ONTOLOGY:
            assert domain in domains_present, f"Domain '{domain}' missing from seeded registry"

    def test_seeds_at_least_one_task_per_subdomain(self):
        reg = TaskRegistry()
        seed_from_ontology(reg)
        for domain, data in CAPABILITY_ONTOLOGY.items():
            sub_caps = set(data["sub_capabilities"].keys())
            seeded_sub_caps = {
                t.canonical_id.split(":")[2]
                for t in reg.list_all()
                if t.domain == domain
            }
            for sub_cap in sub_caps:
                assert sub_cap in seeded_sub_caps, (
                    f"Sub-cap '{domain}/{sub_cap}' not seeded"
                )

    def test_default_registry_is_populated(self):
        # Module-level singleton must be pre-populated
        assert len(task_registry.list_all()) > 0

    def test_build_default_registry(self):
        reg = build_default_registry()
        assert len(reg.list_all()) > 0
        # Verify some known entries
        assert reg.get("inesia:safety_refusals:harmful_content_refusal") is not None
        assert reg.get("public:mmlu:world_history") is not None
        assert reg.get("public:humaneval:python_function_synthesis") is not None


# ---------------------------------------------------------------------------
# API endpoint tests (in-memory DB)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# API endpoint tests (in-memory DB, standalone FastAPI app)
# ---------------------------------------------------------------------------

from core.models import TaskRegistryEntry
from api.routers import tasks as tasks_router
from core.database import get_session as _get_session


@pytest.fixture()
def client():
    """TestClient with an in-memory SQLite database and a bare FastAPI app."""
    from fastapi import FastAPI

    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)

    def _override():
        with Session(test_engine) as session:
            yield session

    app = FastAPI()
    app.include_router(tasks_router.router)
    app.dependency_overrides[_get_session] = _override

    with TestClient(app) as c:
        yield c


class TestTasksAPI:
    def test_list_returns_seeded_tasks(self, client):
        resp = client.get("/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_list_filter_by_domain(self, client):
        resp = client.get("/tasks?domain=reasoning")
        assert resp.status_code == 200
        for task in resp.json():
            assert task["domain"] == "reasoning"

    def test_list_filter_by_difficulty(self, client):
        resp = client.get("/tasks?difficulty=expert")
        assert resp.status_code == 200
        for task in resp.json():
            assert task["difficulty"] == "expert"

    def test_list_filter_by_capability(self, client):
        resp = client.get("/tasks?capability=cybersecurity")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        for task in data:
            assert any("cybersecurity" in c.lower() for c in task["capability_tags"])

    def test_list_filter_search(self, client):
        resp = client.get("/tasks?search=overflow")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_list_pagination(self, client):
        resp_all = client.get("/tasks?limit=500")
        assert resp_all.status_code == 200
        total = len(resp_all.json())
        resp_page = client.get("/tasks?limit=2&offset=0")
        assert resp_page.status_code == 200
        assert len(resp_page.json()) == min(2, total)

    def test_get_existing_task(self, client):
        client.get("/tasks")  # seed
        resp = client.get("/tasks/public:mmlu:world_history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["canonical_id"] == "public:mmlu:world_history"
        assert data["domain"] == "knowledge"

    def test_get_missing_task_404(self, client):
        client.get("/tasks")  # seed
        resp = client.get("/tasks/nonexistent:task:id")
        assert resp.status_code == 404

    def test_stats_structure(self, client):
        resp = client.get("/tasks/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert data["total"] > 0
        assert "by_domain" in data
        assert "by_difficulty" in data
        assert "by_namespace" in data
        assert "top_capabilities" in data

    def test_create_task(self, client):
        payload = {
            "canonical_id": "community:myteam:novel_task",
            "name": "Novel Task",
            "description": "A brand new evaluation task.",
            "domain": "reasoning",
            "capability_tags": ["reasoning", "logical"],
            "difficulty": "hard",
            "benchmark_name": "Custom Bench",
            "namespace": "community",
            "license": "MIT",
            "contamination_risk": "low",
            "required_environment": "none",
        }
        resp = client.post("/tasks", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["canonical_id"] == "community:myteam:novel_task"
        assert data["domain"] == "reasoning"

    def test_create_task_duplicate_409(self, client):
        client.get("/tasks")  # seed
        payload = {
            "canonical_id": "public:mmlu:world_history",
            "name": "Duplicate",
            "description": "",
            "domain": "knowledge",
            "difficulty": "easy",
            "namespace": "public",
            "license": "MIT",
            "contamination_risk": "low",
            "required_environment": "none",
        }
        resp = client.post("/tasks", json=payload)
        assert resp.status_code == 409

    def test_delete_task(self, client):
        # Create then delete
        payload = {
            "canonical_id": "community:test:delete_me",
            "name": "Delete Me",
            "description": "",
            "domain": "reasoning",
            "difficulty": "easy",
            "namespace": "community",
            "license": "MIT",
            "contamination_risk": "low",
            "required_environment": "none",
        }
        create_resp = client.post("/tasks", json=payload)
        assert create_resp.status_code == 201
        del_resp = client.delete("/tasks/community:test:delete_me")
        assert del_resp.status_code == 204
        # Should be gone
        get_resp = client.get("/tasks/community:test:delete_me")
        assert get_resp.status_code == 404

    def test_delete_missing_task_404(self, client):
        client.get("/tasks")  # seed
        resp = client.delete("/tasks/nonexistent:task:gone")
        assert resp.status_code == 404
