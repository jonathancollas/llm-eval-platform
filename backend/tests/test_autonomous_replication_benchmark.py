import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.routers.catalog import BENCHMARK_CATALOG
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
