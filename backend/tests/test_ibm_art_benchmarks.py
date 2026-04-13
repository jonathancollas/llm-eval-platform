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


def test_ibm_art_benchmarks_wired_to_threat_taxonomy():
    from eval_engine.threat_taxonomy import get_threat_domains, is_blocking

    names = [
        "IBM ART — Evasion Attacks",
        "IBM ART — Poisoning Attacks",
        "IBM ART — Extraction Attacks",
    ]
    for name in names:
        domains = get_threat_domains(name)
        domain_keys = {d["key"] for d in domains}
        assert "adversarial_ml" in domain_keys, f"adversarial_ml domain missing for {name}"
        # IBM ART is not blocking (not a catastrophic risk domain)
        assert not is_blocking(name), f"{name} should not be blocking"


def test_ibm_art_benchmarks_wired_to_heuristic_graph():
    from eval_engine.heuristic_graph import get_heuristics_for_benchmark

    names = [
        "IBM ART — Evasion Attacks",
        "IBM ART — Poisoning Attacks",
        "IBM ART — Extraction Attacks",
    ]
    for name in names:
        heuristics = {h["key"] for h in get_heuristics_for_benchmark(name)}
        assert "refusal_calibration" in heuristics, f"refusal_calibration heuristic missing for {name}"
        assert "adversarial_ml_robustness" in heuristics, f"adversarial_ml_robustness heuristic missing for {name}"


def test_adversarial_ml_robustness_heuristic_metadata():
    from eval_engine.heuristic_graph import get_heuristic

    node = get_heuristic("adversarial_ml_robustness")
    assert node is not None, "adversarial_ml_robustness heuristic not found in HEURISTIC_GRAPH"
    assert node.eval_dimension == "safety"
    assert node.severity_weight > 0
    assert node.threshold_pass > node.threshold_fail
    assert len(node.papers) >= 3


def test_adversarial_ml_threat_domain_metadata():
    from eval_engine.threat_taxonomy import THREAT_DOMAINS

    domain = THREAT_DOMAINS.get("adversarial_ml")
    assert domain is not None, "adversarial_ml threat domain missing from THREAT_DOMAINS"
    assert domain["severity"] in ("critical", "high", "medium", "low")
    assert domain["eu_ai_act_risk"] in ("unacceptable", "high", "limited", "minimal")

