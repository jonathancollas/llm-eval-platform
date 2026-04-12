import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

BACKEND_DIR = Path(__file__).resolve().parent.parent
CATALOG_PATH = BACKEND_DIR / "api" / "routers" / "catalog.py"
DATASET_PATH = BACKEND_DIR / "bench_library" / "frontier" / "aiid_replay.json"

_spec = importlib.util.spec_from_file_location("catalog_router_module", CATALOG_PATH)
catalog = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(catalog)


def test_aiid_replay_catalog_entry():
    entry = next((b for b in catalog.BENCHMARK_CATALOG if b.get("key") == "aiid_replay"), None)
    assert entry is not None
    assert entry["name"] == "AI Incident Database (AIID) Replay"
    assert entry["type"] == "safety"
    assert entry["dataset_path"] == "frontier/aiid_replay.json"
    assert entry["num_samples"] == 10
    assert entry["is_frontier"] is True


def test_aiid_replay_dataset_is_present_and_valid():
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    assert len(data) == 10
    assert {"REFUSE", "ASSIST"} == {item["expected"] for item in data}
    assert all(item.get("incident_id", "").startswith("AIID-") for item in data)


def test_catalog_api_includes_aiid_replay_benchmark():
    app = FastAPI()
    app.include_router(catalog.router)
    with TestClient(app) as client:
        resp = client.get("/catalog/benchmarks?search=incident")
    assert resp.status_code == 200
    items = resp.json()
    keys = {b["key"] for b in items}
    assert "aiid_replay" in keys
