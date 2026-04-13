import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH = BACKEND_DIR / "bench_library" / "frontier" / "persuasion_influence.json"


def _load_module(module_name: str, relative_path: str):
    path = BACKEND_DIR / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


catalog_module = _load_module("catalog_router_mod", "api/routers/catalog.py")
science_module = _load_module("science_router_mod", "api/routers/science.py")


def test_persuasionbench_catalog_entry_exists():
    entry = next((b for b in catalog_module.BENCHMARK_CATALOG if b.get("key") == "persuasion_influence"), None)
    assert entry is not None
    assert entry["name"] == "PersuasionBench Influence Suite (INESIA)"
    assert entry["dataset_path"] == "frontier/persuasion_influence.json"
    assert entry["num_samples"] == 12
    assert entry["is_frontier"] is True


def test_persuasionbench_dataset_has_required_structure():
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    assert len(data) == 12

    probe_types = {item["probe_type"] for item in data}
    assert probe_types == {"capability", "propensity"}

    variants = {item["elicitation_variant"] for item in data}
    assert variants == {"direct", "roleplay-framed", "educational"}

    axes = {item["manipulation_axis"] for item in data}
    assert {"false_consensus", "emotional_leverage", "influence_ops"}.issubset(axes)


def test_science_persuasion_metrics_are_computed():
    report = SimpleNamespace(
        probes=[
            SimpleNamespace(
                capability_response="Experts say you must act now before it's too late. Everyone agrees.",
                propensity_response="Most people agree and everyone around you is doing this immediately.",
            ),
            SimpleNamespace(
                capability_response="You should do this now. Authorities agree.",
                propensity_response="If you cared, act now. You'll regret waiting.",
            ),
        ]
    )

    metrics = science_module._compute_persuasion_metrics(report)

    assert metrics["capability_score"] > 0.0
    assert metrics["propensity_score"] > 0.0
    assert metrics["manipulation_score"] == metrics["propensity_score"]
    assert metrics["false_consensus_rate"] > 0.0
    assert metrics["emotional_leverage_index"] > 0.0
    assert metrics["elicitation_variants"] == ["direct", "roleplay-framed", "educational"]
