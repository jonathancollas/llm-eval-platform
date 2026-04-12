import importlib.util
import os
import sys

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, BACKEND_DIR)

from eval_engine.adversarial_taxonomy import ADVERSARIAL_TOOL_REGISTRY, MUTATION_TAXONOMY

REDBOX_PATH = os.path.join(BACKEND_DIR, "api", "routers", "redbox.py")
_spec = importlib.util.spec_from_file_location("redbox_router_module", REDBOX_PATH)
redbox = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(redbox)


def test_registry_covers_all_mutation_tools():
    mutation_tools = set(MUTATION_TAXONOMY.keys())
    registry_tools = {item["tool_name"] for item in ADVERSARIAL_TOOL_REGISTRY}
    assert registry_tools == mutation_tools


def test_registry_has_required_standard_fields():
    required = {"tool_name", "category", "input_adapter", "output_schema", "severity_model"}
    for item in ADVERSARIAL_TOOL_REGISTRY:
        assert required.issubset(item.keys())
        for field in required:
            assert isinstance(item[field], str)
            assert item[field]


def test_tool_registry_endpoint_supports_category_filter():
    assert ADVERSARIAL_TOOL_REGISTRY
    category = min({tool["category"] for tool in ADVERSARIAL_TOOL_REGISTRY})
    payload = redbox.get_adversarial_tool_registry(category=category)
    assert payload["total"] > 0
    assert category in payload["categories"]
    assert all(item["category"] == category for item in payload["tools"])
