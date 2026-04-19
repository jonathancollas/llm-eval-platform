"""
Tests for the lm-eval harness full-library search (maximize-benchmark-loading).

These tests verify that search_harness_tasks and the catalog endpoint expose all
available lm-eval tasks, not just the 62 curated ones.
"""
import os
import sys
import secrets

import pytest

os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── search_harness_tasks unit tests ──────────────────────────────────────────

def test_search_returns_curated_first():
    from eval_engine.harness_runner import search_harness_tasks, HARNESS_CATALOG

    results = search_harness_tasks("mmlu", limit=20)
    assert len(results) > 0

    # Curated tasks must appear before non-curated
    curated_indices = [i for i, r in enumerate(results) if r["is_curated"]]
    non_curated_indices = [i for i, r in enumerate(results) if not r["is_curated"]]
    if curated_indices and non_curated_indices:
        assert max(curated_indices) < min(non_curated_indices), (
            "Curated tasks should all appear before non-curated tasks"
        )


def test_search_respects_limit():
    from eval_engine.harness_runner import search_harness_tasks

    for limit in [1, 5, 10, 50]:
        results = search_harness_tasks("", limit=limit)
        assert len(results) <= limit, f"Expected ≤{limit} results, got {len(results)}"


def test_search_curated_tasks_have_rich_metadata():
    from eval_engine.harness_runner import search_harness_tasks, HARNESS_CATALOG

    results = search_harness_tasks("gsm8k", limit=10)
    curated = [r for r in results if r["is_curated"]]
    assert len(curated) > 0, "Expected at least one curated gsm8k task"

    for r in curated:
        assert r["key"] in HARNESS_CATALOG, f"Curated task {r['key']} must be in HARNESS_CATALOG"
        assert r["few_shot"] >= 0
        assert r["description"]
        assert r["metric"]


def test_search_non_curated_tasks_have_auto_metadata():
    from eval_engine.harness_runner import search_harness_tasks, HARNESS_CATALOG

    # Search for something not in the curated catalog
    results = search_harness_tasks("AraDiCE", limit=5)
    for r in results:
        assert r["key"] not in HARNESS_CATALOG
        assert r["is_curated"] is False
        assert r["description"].startswith("lm-evaluation-harness task:")
        assert r["metric"] == "acc,none"
        assert r["few_shot"] == 0


def test_search_empty_query_returns_results():
    from eval_engine.harness_runner import search_harness_tasks

    results = search_harness_tasks("", limit=10)
    assert len(results) == 10


def test_search_no_match_returns_empty():
    from eval_engine.harness_runner import search_harness_tasks

    results = search_harness_tasks("__this_task_definitely_does_not_exist__", limit=10)
    assert results == []


def test_infer_domain_known_prefixes():
    from eval_engine.harness_runner import _infer_domain

    assert _infer_domain("mmlu_pro") == "knowledge"
    assert _infer_domain("gsm8k_cot") == "maths"
    assert _infer_domain("humaneval") == "code"
    assert _infer_domain("hellaswag") == "raisonnement"
    assert _infer_domain("truthfulqa_mc1") == "factuality"
    assert _infer_domain("ifeval") == "instruction following"
    assert _infer_domain("french_bench") == "français"
    assert _infer_domain("wmdp_bio") == "safety"
    assert _infer_domain("completely_unknown_xyzzy") == "other"


# ── HTTP endpoint tests ───────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def catalog_client():
    """Lightweight FastAPI test client for the catalog router only."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlmodel import Session, SQLModel, create_engine

    from api.routers import catalog as catalog_router

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    app = FastAPI()
    app.include_router(catalog_router.router)

    def _override_session():
        with Session(engine) as session:
            yield session

    from core.database import get_session
    app.dependency_overrides[get_session] = _override_session

    return TestClient(app)


def test_harness_search_endpoint_basic(catalog_client):
    resp = catalog_client.get("/catalog/benchmarks/harness-search?q=gsm8k&limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) <= 5
    # gsm8k is curated — should appear
    keys = [r["key"] for r in data]
    assert "gsm8k" in keys


def test_harness_search_endpoint_curated_first(catalog_client):
    resp = catalog_client.get("/catalog/benchmarks/harness-search?q=mmlu&limit=20")
    assert resp.status_code == 200
    data = resp.json()
    curated_indices = [i for i, r in enumerate(data) if r["is_curated"]]
    non_curated_indices = [i for i, r in enumerate(data) if not r["is_curated"]]
    if curated_indices and non_curated_indices:
        assert max(curated_indices) < min(non_curated_indices)


def test_harness_search_endpoint_no_match(catalog_client):
    resp = catalog_client.get("/catalog/benchmarks/harness-search?q=__no_such_task__&limit=10")
    assert resp.status_code == 200
    assert resp.json() == []


def test_harness_search_endpoint_limit_validation(catalog_client):
    # limit=0 should fail validation
    resp = catalog_client.get("/catalog/benchmarks/harness-search?q=mmlu&limit=0")
    assert resp.status_code == 422

    # limit=501 should fail validation
    resp = catalog_client.get("/catalog/benchmarks/harness-search?q=mmlu&limit=501")
    assert resp.status_code == 422


def test_harness_search_endpoint_result_shape(catalog_client):
    resp = catalog_client.get("/catalog/benchmarks/harness-search?q=arc_challenge&limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    item = data[0]
    required_fields = {"key", "name", "domain", "description", "metric", "few_shot", "is_frontier", "is_curated"}
    assert required_fields.issubset(item.keys()), f"Missing fields: {required_fields - item.keys()}"
