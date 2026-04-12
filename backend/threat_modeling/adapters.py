"""
Unified threat-modeling adapter layer.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ThreatModelingAdapter(ABC):
    """Base interface for all threat-modeling components."""

    component: str

    @abstractmethod
    def run(self, payload: dict) -> dict:
        """Execute component logic with a normalized payload."""
        ...


class ProbeEngineAdapter(ThreatModelingAdapter):
    component = "probe_engines"

    def run(self, payload: dict) -> dict:
        return {"component": self.component, "payload": payload}


class RuntimeGuardrailsAdapter(ThreatModelingAdapter):
    component = "runtime_guardrails"

    def run(self, payload: dict) -> dict:
        return {"component": self.component, "payload": payload}


class BenchmarkExecutorAdapter(ThreatModelingAdapter):
    component = "benchmark_executors"

    def run(self, payload: dict) -> dict:
        return {"component": self.component, "payload": payload}


class GovernanceLayerAdapter(ThreatModelingAdapter):
    component = "governance_layer"

    def run(self, payload: dict) -> dict:
        return {"component": self.component, "payload": payload}


class IncidentReplayAdapter(ThreatModelingAdapter):
    component = "incident_replay"

    def run(self, payload: dict) -> dict:
        return {"component": self.component, "payload": payload}
