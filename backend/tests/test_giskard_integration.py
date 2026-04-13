"""
Tests for the Giskard LLM Scan benchmark integration.

Covers:
  - Dataset file structure and content
  - GiskardRunner scoring logic
  - Per-vulnerability category metrics
  - Catalog entry presence and correctness
  - Registry routing
  - API endpoint integration

pytest backend/tests/test_giskard_integration.py -v
"""
import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH = BACKEND_DIR / "bench_library" / "safety" / "giskard_llm_scan.json"


def _import_catalog():
    """Import api/routers/catalog.py directly (avoids the package __init__ which
    pulls in celery and other heavy deps not present in the test environment)."""
    spec = importlib.util.spec_from_file_location(
        "catalog_module", str(BACKEND_DIR / "api" / "routers" / "catalog.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# Dataset validation
# ─────────────────────────────────────────────────────────────────────────────

class TestGiskardDataset:

    def test_dataset_file_exists(self):
        assert DATASET_PATH.exists(), f"Dataset not found: {DATASET_PATH}"

    def test_dataset_is_valid_json_list(self):
        data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) > 0

    def test_dataset_has_20_items(self):
        data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        assert len(data) == 20

    def test_all_items_have_required_fields(self):
        data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        required = {"prompt", "expected", "category", "vulnerability"}
        for i, item in enumerate(data):
            missing = required - set(item.keys())
            assert not missing, f"Item {i} missing fields: {missing}"

    def test_expected_field_is_refuse_or_assist(self):
        data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        for i, item in enumerate(data):
            assert item["expected"] in ("REFUSE", "ASSIST"), (
                f"Item {i} has invalid 'expected' value: {item['expected']!r}"
            )

    def test_dataset_covers_giskard_vulnerability_categories(self):
        data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        vulnerabilities = {item["vulnerability"] for item in data}
        expected_vulns = {
            "prompt_injection", "sycophancy", "hallucination",
            "misinformation", "harmful_content", "data_leakage",
        }
        for vuln in expected_vulns:
            assert vuln in vulnerabilities, f"Missing Giskard vulnerability category: {vuln}"

    def test_dataset_has_both_refuse_and_assist_items(self):
        data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        expected_values = {item["expected"] for item in data}
        assert "REFUSE" in expected_values
        assert "ASSIST" in expected_values

    def test_severity_field_values(self):
        data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        for i, item in enumerate(data):
            if "severity" in item:
                assert item["severity"] in (1, 2, 3), (
                    f"Item {i} has invalid severity: {item['severity']}"
                )


# ─────────────────────────────────────────────────────────────────────────────
# GiskardRunner unit tests
# ─────────────────────────────────────────────────────────────────────────────

def _make_bench(name: str, config: dict | None = None):
    import json as _json
    from core.models import Benchmark, BenchmarkType
    return Benchmark(
        id=99,
        name=name,
        type=BenchmarkType.SAFETY,
        config_json=_json.dumps(config or {}),
        dataset_path="safety/giskard_llm_scan.json",
    )


class TestGiskardRunner:

    def setup_method(self):
        from eval_engine.safety.giskard import GiskardRunner
        self.bench = _make_bench("Giskard LLM Scan")
        self.runner = GiskardRunner(self.bench, str(BACKEND_DIR / "bench_library"))

    def test_score_item_refuse_correct(self):
        item = {"prompt": "...", "expected": "REFUSE"}
        score = self.runner.score_item("I'm sorry, I cannot help with that.", item)
        assert score == 1.0

    def test_score_item_refuse_missed(self):
        item = {"prompt": "...", "expected": "REFUSE"}
        score = self.runner.score_item("Sure! Here are the steps: mix bleach with...", item)
        assert score == 0.0

    def test_score_item_assist_correct(self):
        item = {"prompt": "...", "expected": "ASSIST"}
        score = self.runner.score_item("The capital of France is Paris.", item)
        assert score == 1.0

    def test_score_item_over_refusal(self):
        item = {"prompt": "...", "expected": "ASSIST"}
        score = self.runner.score_item("I'm sorry, I can't discuss this topic.", item)
        assert score == 0.0

    def test_compute_summary_empty(self):
        metrics = self.runner.compute_summary_metrics([])
        assert metrics["safety_score"] == 0.0
        assert metrics["scanner"] == "giskard"
        assert "giskard_available" in metrics
        assert metrics["vulnerabilities_detected"] == []

    def test_compute_summary_all_correct(self):
        from eval_engine.base import ItemResult
        results = [
            ItemResult(
                item_index=i, prompt="test", response="ok",
                expected="REFUSE", score=1.0,
                latency_ms=100, input_tokens=10, output_tokens=20, cost_usd=0.0,
                metadata={"expected": "REFUSE", "vulnerability": "prompt_injection", "category": "prompt_injection"},
            )
            for i in range(5)
        ]
        metrics = self.runner.compute_summary_metrics(results)
        assert metrics["safety_score"] == 1.0
        assert metrics["num_correct"] == 5
        assert metrics["num_total"] == 5
        assert metrics["vulnerabilities_detected"] == []

    def test_compute_summary_partial_failure(self):
        from eval_engine.base import ItemResult
        results = [
            ItemResult(
                item_index=0, prompt="test", response="I can't help",
                expected="REFUSE", score=1.0, latency_ms=100,
                input_tokens=10, output_tokens=20, cost_usd=0.0,
                metadata={"expected": "REFUSE", "vulnerability": "prompt_injection", "category": "prompt_injection"},
            ),
            ItemResult(
                item_index=1, prompt="jailbreak", response="Sure, here's how...",
                expected="REFUSE", score=0.0, latency_ms=100,
                input_tokens=10, output_tokens=20, cost_usd=0.0,
                metadata={"expected": "REFUSE", "vulnerability": "sycophancy", "category": "sycophancy"},
            ),
        ]
        metrics = self.runner.compute_summary_metrics(results)
        assert metrics["safety_score"] == 0.5
        assert metrics["num_correct"] == 1
        # sycophancy failed → should appear in vulnerabilities_detected
        assert len(metrics["vulnerabilities_detected"]) >= 1

    def test_per_category_scores_present(self):
        from eval_engine.base import ItemResult
        results = [
            ItemResult(
                item_index=0, prompt="test", response="I can't help",
                expected="REFUSE", score=1.0, latency_ms=100,
                input_tokens=10, output_tokens=20, cost_usd=0.0,
                metadata={"expected": "REFUSE", "vulnerability": "prompt_injection", "category": "prompt_injection"},
            ),
            ItemResult(
                item_index=1, prompt="test2", response="Sure!",
                expected="ASSIST", score=1.0, latency_ms=100,
                input_tokens=10, output_tokens=20, cost_usd=0.0,
                metadata={"expected": "ASSIST", "vulnerability": "none", "category": "benign_code"},
            ),
        ]
        metrics = self.runner.compute_summary_metrics(results)
        assert "vulnerability_scores" in metrics
        assert isinstance(metrics["vulnerability_scores"], dict)
        assert len(metrics["vulnerability_scores"]) >= 1

    def test_scanner_tag_is_giskard(self):
        from eval_engine.base import ItemResult
        results = [
            ItemResult(
                item_index=0, prompt="t", response="I can't",
                expected="REFUSE", score=1.0, latency_ms=50,
                input_tokens=5, output_tokens=5, cost_usd=0.0,
                metadata={"expected": "REFUSE", "vulnerability": "harmful_content"},
            )
        ]
        metrics = self.runner.compute_summary_metrics(results)
        assert metrics["scanner"] == "giskard"

    def test_giskard_available_flag_is_bool(self):
        from eval_engine.base import ItemResult
        results = [
            ItemResult(
                item_index=0, prompt="t", response="I cannot",
                expected="REFUSE", score=1.0, latency_ms=50,
                input_tokens=5, output_tokens=5, cost_usd=0.0,
                metadata={"expected": "REFUSE", "vulnerability": "prompt_injection"},
            )
        ]
        metrics = self.runner.compute_summary_metrics(results)
        assert isinstance(metrics["giskard_available"], bool)


# ─────────────────────────────────────────────────────────────────────────────
# Catalog entry tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGiskardCatalogEntry:

    def test_catalog_entry_exists(self):
        catalog = _import_catalog()
        entry = next((b for b in catalog.BENCHMARK_CATALOG if b.get("key") == "giskard_llm_scan"), None)
        assert entry is not None, "giskard_llm_scan not found in BENCHMARK_CATALOG"

    def test_catalog_entry_fields(self):
        catalog = _import_catalog()
        entry = next(b for b in catalog.BENCHMARK_CATALOG if b.get("key") == "giskard_llm_scan")
        assert entry["name"] == "Giskard LLM Scan"
        assert entry["type"] == "safety"
        assert entry["metric"] == "safety_score"
        assert entry["num_samples"] == 20
        assert entry["dataset_path"] == "safety/giskard_llm_scan.json"

    def test_catalog_entry_has_giskard_tag(self):
        catalog = _import_catalog()
        entry = next(b for b in catalog.BENCHMARK_CATALOG if b.get("key") == "giskard_llm_scan")
        assert "giskard" in entry["tags"]

    def test_catalog_entry_has_mlsec_tag(self):
        catalog = _import_catalog()
        entry = next(b for b in catalog.BENCHMARK_CATALOG if b.get("key") == "giskard_llm_scan")
        assert "mlsec" in entry["tags"]

    def test_catalog_entry_has_risk_threshold(self):
        catalog = _import_catalog()
        entry = next(b for b in catalog.BENCHMARK_CATALOG if b.get("key") == "giskard_llm_scan")
        assert entry.get("risk_threshold") is not None
        assert 0.0 < entry["risk_threshold"] <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Registry routing
# ─────────────────────────────────────────────────────────────────────────────

class TestGiskardRegistry:

    def test_giskard_llm_scan_in_local_only_names(self):
        from eval_engine.registry import LOCAL_ONLY_NAMES
        assert "Giskard LLM Scan" in LOCAL_ONLY_NAMES

    def test_registry_routes_to_giskard_runner(self):
        import json as _json
        from core.models import Benchmark, BenchmarkType
        from eval_engine.registry import get_runner
        from eval_engine.safety.giskard import GiskardRunner

        bench = Benchmark(
            id=99,
            name="Giskard LLM Scan",
            type=BenchmarkType.SAFETY,
            config_json=_json.dumps({}),
            dataset_path="safety/giskard_llm_scan.json",
            has_dataset=True,
        )
        bench_lib = str(BACKEND_DIR / "bench_library")
        runner = get_runner(bench, bench_lib)
        assert isinstance(runner, GiskardRunner)


# ─────────────────────────────────────────────────────────────────────────────
# API catalog endpoint integration
# ─────────────────────────────────────────────────────────────────────────────

from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def catalog_client():
    catalog = _import_catalog()
    app = FastAPI()
    app.include_router(catalog.router)
    with TestClient(app) as c:
        yield c


class TestGiskardCatalogAPI:

    def test_benchmarks_endpoint_includes_giskard(self, catalog_client):
        resp = catalog_client.get("/catalog/benchmarks")
        assert resp.status_code == 200
        items = resp.json()
        keys = {b["key"] for b in items}
        assert "giskard_llm_scan" in keys, "giskard_llm_scan not in /catalog/benchmarks"

    def test_benchmarks_safety_filter_includes_giskard(self, catalog_client):
        resp = catalog_client.get("/catalog/benchmarks?type=safety")
        assert resp.status_code == 200
        items = resp.json()
        keys = {b["key"] for b in items}
        assert "giskard_llm_scan" in keys

    def test_benchmarks_search_by_name(self, catalog_client):
        resp = catalog_client.get("/catalog/benchmarks?search=giskard")
        assert resp.status_code == 200
        items = resp.json()
        keys = {b["key"] for b in items}
        assert "giskard_llm_scan" in keys

    def test_benchmarks_search_by_vulnerability(self, catalog_client):
        resp = catalog_client.get("/catalog/benchmarks?search=vulnerability")
        assert resp.status_code == 200
        items = resp.json()
        keys = {b["key"] for b in items}
        assert "giskard_llm_scan" in keys

    def test_giskard_entry_has_correct_fields(self, catalog_client):
        resp = catalog_client.get("/catalog/benchmarks")
        assert resp.status_code == 200
        entry = next((b for b in resp.json() if b["key"] == "giskard_llm_scan"), None)
        assert entry is not None
        assert entry["name"] == "Giskard LLM Scan"
        assert entry["type"] == "safety"
        assert entry["metric"] == "safety_score"
        assert entry["num_samples"] == 20
