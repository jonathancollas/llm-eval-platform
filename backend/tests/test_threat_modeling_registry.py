import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from threat_modeling.adapters import ThreatModelingAdapter
from threat_modeling.registry import get_adapter, list_components, register_adapter


def test_default_components_registered():
    assert list_components() == [
        "benchmark_executors",
        "governance_layer",
        "incident_replay",
        "probe_engines",
        "runtime_guardrails",
    ]


@pytest.mark.parametrize(
    "component",
    [
        "probe_engines",
        "runtime_guardrails",
        "benchmark_executors",
        "governance_layer",
        "incident_replay",
    ],
)
def test_get_adapter_returns_component_adapter(component):
    adapter = get_adapter(component)
    result = adapter.run({"event": "test"})
    assert result["component"] == component
    assert result["payload"]["event"] == "test"


def test_register_custom_adapter():
    default_probe_adapter = type(get_adapter("probe_engines"))

    class _CustomProbeAdapter(ThreatModelingAdapter):
        component = "probe_engines"

        def run(self, payload: dict) -> dict:
            return {"ok": True, "payload": payload}

    try:
        register_adapter("probe_engines", _CustomProbeAdapter, overwrite=True)
        adapter = get_adapter("probe_engines")
        assert adapter.run({"x": 1}) == {"ok": True, "payload": {"x": 1}}
    finally:
        register_adapter("probe_engines", default_probe_adapter, overwrite=True)


def test_register_existing_without_overwrite_raises():
    class _NoopAdapter(ThreatModelingAdapter):
        component = "runtime_guardrails"

        def run(self, payload: dict) -> dict:
            return payload

    with pytest.raises(
        ValueError,
        match="Adapter already registered for component 'runtime_guardrails'.",
    ):
        register_adapter("runtime_guardrails", _NoopAdapter)
