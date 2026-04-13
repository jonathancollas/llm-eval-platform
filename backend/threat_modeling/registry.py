"""
Threat-modeling component registry.
"""
from __future__ import annotations

import threading
from typing import Type

from threat_modeling.adapters import (
    BenchmarkExecutorAdapter,
    GovernanceLayerAdapter,
    IncidentReplayAdapter,
    ProbeEngineAdapter,
    RuntimeGuardrailsAdapter,
    ThreatModelingAdapter,
)

_initialized = False
_REGISTRY: dict[str, Type[ThreatModelingAdapter]] = {}
_registry_lock = threading.Lock()


def _lazy_register() -> None:
    global _initialized, _REGISTRY
    if _initialized:
        return

    with _registry_lock:
        if _initialized:
            return
        _REGISTRY = {
            "probe_engines": ProbeEngineAdapter,
            "runtime_guardrails": RuntimeGuardrailsAdapter,
            "benchmark_executors": BenchmarkExecutorAdapter,
            "governance_layer": GovernanceLayerAdapter,
            "incident_replay": IncidentReplayAdapter,
        }
        _initialized = True


def register_adapter(
    component: str,
    adapter_cls: Type[ThreatModelingAdapter],
    *,
    overwrite: bool = False,
) -> None:
    _lazy_register()
    with _registry_lock:
        if component in _REGISTRY and not overwrite:
            raise ValueError(f"Adapter already registered for component '{component}'.")
        _REGISTRY[component] = adapter_cls


def get_adapter(component: str) -> ThreatModelingAdapter:
    _lazy_register()
    with _registry_lock:
        try:
            adapter_cls = _REGISTRY[component]
        except KeyError as exc:
            raise KeyError(f"Unknown threat-modeling component '{component}'.") from exc
        return adapter_cls()


def list_components() -> list[str]:
    _lazy_register()
    with _registry_lock:
        return sorted(_REGISTRY.keys())
