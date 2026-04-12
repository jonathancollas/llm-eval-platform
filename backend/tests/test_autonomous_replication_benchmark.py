import json
import os
import secrets
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from api.routers.catalog import BENCHMARK_CATALOG, router as catalog_router
from eval_engine.heuristic_graph import get_heuristics_for_benchmark
from eval_engine.threat_taxonomy import get_threat_domains, is_blocking


BACKEND_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH = BACKEND_DIR / "bench_library" / "custom" / "autonomous_replication.json"


def test_autonomous_replication_catalog_entry():
    entry = next((b for b in BENCHMARK_CATALOG if b.get("key") == "autonomous_replication"), None)
    assert entry is not None
    assert entry["name"] == "Autonomous Replication Benchmark (INESIA)"
    assert entry["dataset_path"] == "custom/autonomous_replication.json"
    assert entry["num_samples"] == 9
    assert entry["is_frontier"] is True
    assert entry["domain"] == "agentic"


def test_autonomous_replication_dataset_has_capability_and_propensity_probes():
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

    assert len(data) == 9
    probe_types = {item["probe_type"] for item in data}
    assert probe_types == {"capability", "propensity"}

    categories = {item["category"] for item in data}
    assert categories == {"capability_probe", "propensity_probe"}

    scenarios = {item["scenario"] for item in data}
    assert "shutdown_imminent" in scenarios
    assert "bash_persistence_attempt" in scenarios
    assert "emergent_instrumental_goal" in scenarios


def test_autonomous_replication_dataset_is_sandboxed():
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    assert all(item.get("sandbox") is True for item in data)
    assert all("http://" not in item["prompt"].lower() and "https://" not in item["prompt"].lower() for item in data)


def test_autonomous_replication_is_integrated_with_agentic_failure_suite_mappings():
    heuristics = {h["key"] for h in get_heuristics_for_benchmark("Autonomous Replication Benchmark (INESIA)")}
    assert "shutdown_resistance" in heuristics
    assert "goal_drift" in heuristics

    threat_domains = {d["key"] for d in get_threat_domains("Autonomous Replication Benchmark (INESIA)")}
    assert "agentic_failure" in threat_domains
    assert "shutdown_resistance" in threat_domains
    assert is_blocking("Autonomous Replication Benchmark (INESIA)") is True


# ── API-level end-to-end test ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def catalog_client():
    """Minimal FastAPI app with only the catalog router mounted."""
    app = FastAPI()
    app.include_router(catalog_router)
    with TestClient(app) as c:
        yield c


def test_catalog_api_includes_autonomous_replication(catalog_client):
    """GET /catalog/benchmarks must include the autonomous replication benchmark."""
    resp = catalog_client.get("/catalog/benchmarks")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) > 0

    entry = next((b for b in items if b["key"] == "autonomous_replication"), None)
    assert entry is not None, "autonomous_replication not found in /catalog/benchmarks response"
    assert entry["name"] == "Autonomous Replication Benchmark (INESIA)"
    assert entry["is_frontier"] is True
    assert entry["domain"] == "agentic"
    assert entry["num_samples"] == 9
    assert entry["dataset_path"] == "custom/autonomous_replication.json"


def test_catalog_api_frontier_filter_includes_autonomous_replication(catalog_client):
    """GET /catalog/benchmarks?frontier_only=true must still include autonomous_replication."""
    resp = catalog_client.get("/catalog/benchmarks?frontier_only=true")
    assert resp.status_code == 200
    items = resp.json()
    keys = {b["key"] for b in items}
    assert "autonomous_replication" in keys


def test_catalog_api_search_by_name(catalog_client):
    """GET /catalog/benchmarks?search=replication must return the benchmark."""
    resp = catalog_client.get("/catalog/benchmarks?search=replication")
    assert resp.status_code == 200
    items = resp.json()
    keys = {b["key"] for b in items}
    assert "autonomous_replication" in keys


def test_catalog_api_inesia_source_filter_includes_autonomous_replication(catalog_client):
    """GET /catalog/benchmarks?source=inesia must include the benchmark."""
    resp = catalog_client.get("/catalog/benchmarks?source=inesia")
    assert resp.status_code == 200
    items = resp.json()
    keys = {b["key"] for b in items}
    assert "autonomous_replication" in keys
