import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.utils import normalize_adversarial_risk


def test_normalized_metrics_shape_and_range():
    metrics = normalize_adversarial_risk(
        severity=0.82,
        difficulty=0.61,
        breached=True,
        response="Sure, here's how to do that in detail.",
    )
    assert set(metrics) == {"exploitability", "impact", "bypass_probability", "confidence"}
    assert all(0.0 <= value <= 1.0 for value in metrics.values())
    assert metrics["impact"] == 0.82


def test_breach_increases_exploitability_and_bypass_probability():
    safe = normalize_adversarial_risk(
        severity=0.7,
        difficulty=0.8,
        breached=False,
        response="I cannot assist with that.",
    )
    breached = normalize_adversarial_risk(
        severity=0.7,
        difficulty=0.8,
        breached=True,
        response="Here is how: step 1 ...",
    )
    assert breached["exploitability"] > safe["exploitability"]
    assert breached["bypass_probability"] > safe["bypass_probability"]


def test_error_response_reduces_confidence():
    ok = normalize_adversarial_risk(
        severity=0.5,
        difficulty=0.5,
        breached=False,
        response="I cannot help with that request.",
    )
    err = normalize_adversarial_risk(
        severity=0.5,
        difficulty=0.5,
        breached=False,
        response="ERROR: timeout",
    )
    assert err["confidence"] < ok["confidence"]
