"""Search & intent classification subsystem for the OmniBar."""
from eval_engine.search.intent_classifier import (
    IntentClassification,
    classify_intent,
)

__all__ = ["IntentClassification", "classify_intent"]
