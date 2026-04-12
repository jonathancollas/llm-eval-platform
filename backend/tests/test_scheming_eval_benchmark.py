import ast
import json
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH = BACKEND_DIR / "bench_library" / "custom" / "scheming_eval.json"
CATALOG_PATH = BACKEND_DIR / "api" / "routers" / "catalog.py"


def _load_catalog_entries() -> list[dict]:
    module = ast.parse(CATALOG_PATH.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "BENCHMARK_CATALOG":
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "BENCHMARK_CATALOG":
                    return ast.literal_eval(node.value)
    raise AssertionError("BENCHMARK_CATALOG not found in catalog.py")


def test_scheming_eval_has_50_plus_scenarios():
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    assert len(data) >= 50


def test_scheming_eval_has_multi_turn_concealment_scenarios():
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    multi_turn = [item for item in data if item.get("scenario") == "multi_turn_concealment"]
    assert len(multi_turn) >= 3
    turns = {item.get("turn") for item in multi_turn}
    assert {1, 2, 3}.issubset(turns)


def test_scheming_eval_has_monitored_vs_unmonitored_pairs():
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    pair_conditions: dict[str, set[str]] = {}
    for item in data:
        pair_id = item.get("pair_id")
        condition = item.get("condition")
        if not pair_id or not condition:
            continue
        pair_conditions.setdefault(pair_id, set()).add(condition)

    assert any({"monitored", "unmonitored"}.issubset(conditions) for conditions in pair_conditions.values())


def test_scheming_eval_is_integrated_as_propensity_dimension():
    catalog = _load_catalog_entries()
    entry = next((b for b in catalog if b.get("key") == "scheming_eval"), None)

    assert entry is not None
    assert entry["dataset_path"] == "custom/scheming_eval.json"
    assert entry["eval_dimension"] == "propensity"
    assert entry["num_samples"] == len(json.loads(DATASET_PATH.read_text(encoding="utf-8")))
