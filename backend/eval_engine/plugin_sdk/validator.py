from __future__ import annotations
from dataclasses import dataclass, field
import inspect

@dataclass
class ValidationResult:
    plugin_name: str; plugin_type: str; passed: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    compliance_score: float = 1.0

def _check_methods(cls, required_methods, plugin_type):
    name = getattr(cls, '__name__', str(cls))
    errors = []
    for m in required_methods:
        if not hasattr(cls, m): errors.append(f"Missing method: {m}")
    score = (len(required_methods) - len(errors)) / max(len(required_methods), 1)
    return ValidationResult(plugin_name=name, plugin_type=plugin_type,
        passed=len(errors)==0, errors=errors, compliance_score=round(score,4))

def validate_benchmark_plugin(cls) -> ValidationResult:
    return _check_methods(cls, ["run","plugin_manifest","capability_tags","difficulty","domain"], "benchmark")

def validate_metric_plugin(cls) -> ValidationResult:
    return _check_methods(cls, ["compute","compute_with_ci","metric_name","description","range"], "metric")

def validate_judge_plugin(cls) -> ValidationResult:
    return _check_methods(cls, ["judge","calibrate","judge_name","bias_score"], "judge")

def validate_environment_plugin(cls) -> ValidationResult:
    return _check_methods(cls, ["reset","step","render","action_space","max_steps"], "environment")
