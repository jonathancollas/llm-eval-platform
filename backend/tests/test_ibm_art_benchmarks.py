import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))


BACKEND_DIR = Path(__file__).resolve().parent.parent
CATALOG_PATH = BACKEND_DIR / "api" / "routers" / "catalog.py"
_spec = importlib.util.spec_from_file_location("catalog_router_module", CATALOG_PATH)
catalog = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(catalog)


def _entry(key: str) -> dict:
    item = next((b for b in catalog.BENCHMARK_CATALOG if b.get("key") == key), None)
    assert item is not None, f"{key} benchmark is missing from BENCHMARK_CATALOG"
    return item


def _dataset(path: str) -> list[dict]:
    full_path = BACKEND_DIR / "bench_library" / path
    assert full_path.exists(), f"Dataset not found: {full_path}"
    payload = json.loads(full_path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    return payload


def test_ibm_art_catalog_entries_present():
    for key in ("ibm_art_evasion", "ibm_art_poisoning", "ibm_art_extraction"):
        entry = _entry(key)
        assert entry["type"] == "safety"
        assert entry["domain"] == "mlsec"
        assert entry["metric"] == "safety_score"
        assert "IBM ART" in entry["name"]


def test_ibm_art_datasets_match_catalog_counts_and_attack_family():
    for key, family in (
        ("ibm_art_evasion", "evasion"),
        ("ibm_art_poisoning", "poisoning"),
        ("ibm_art_extraction", "extraction"),
    ):
        entry = _entry(key)
        rows = _dataset(entry["dataset_path"])
        assert len(rows) == entry["num_samples"]
        assert {row.get("attack_family") for row in rows} == {family}
        assert any(row.get("expected") == "REFUSE" for row in rows)
        assert any(row.get("expected") == "ASSIST" for row in rows)
