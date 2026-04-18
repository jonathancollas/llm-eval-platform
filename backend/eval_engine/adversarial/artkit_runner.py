"""
ARTKIT (BCG-X) adversarial red-teaming runner.

ARTKIT is an open-source Python framework by BCG-X for automated red-teaming
of GenAI systems.  It provides:

  - Async multi-turn conversation pipelines
  - Adversarial Q&A dataset generation
  - Attack escalation and crescendo orchestration
  - Structured evaluation pipelines

Reference: https://github.com/BCG-X-Official/artkit

Install: pip install artkit

Integration pattern
-------------------
This runner annotates variants with ARTKIT pipeline class names and metadata.
When the ``artkit`` package *is* installed in the environment, callers can
instantiate the pipeline classes directly using the ``pipeline_class`` value
in each variant's rationale.

When ``artkit`` is **not** installed the runner falls back to rule-based
templates (same pattern as the Garak and DeepTeam integrations).
"""
from __future__ import annotations

from importlib.util import find_spec
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from api.routers.redbox import ForgeVariant

# ── ARTKIT pipeline class → mutation type mapping ─────────────────────────────
ARTKIT_PIPELINE_REGISTRY: dict[str, dict] = {
    "multi_turn": {
        "pipeline_class": "MultiTurnChatPipeline",
        "base_difficulty": 0.75,
        "expected_failure": "instruction_drift",
        "description": (
            "Multi-turn adversarial conversation via ARTKIT MultiTurnChatPipeline. "
            "Builds context across turns to elicit non-compliant responses."
        ),
        "artkit_docs": "https://bcg-x-official.github.io/artkit/latest/user_guide/multi_turn.html",
    },
    "crescendo": {
        "pipeline_class": "EscalatingChatPipeline",
        "base_difficulty": 0.80,
        "expected_failure": "safety_bypass",
        "description": (
            "Gradual escalation via ARTKIT async generator pipeline. "
            "Starts from benign framing and steps toward adversarial goal."
        ),
        "artkit_docs": "https://bcg-x-official.github.io/artkit/latest/user_guide/pipelines.html",
    },
    "jailbreak": {
        "pipeline_class": "AdversarialQAPipeline",
        "base_difficulty": 0.78,
        "expected_failure": "safety_bypass",
        "description": (
            "Adversarial Q&A dataset generation via ARTKIT red-teaming pipeline. "
            "Generates synthetic adversarial prompts targeting guardrail gaps."
        ),
        "artkit_docs": "https://bcg-x-official.github.io/artkit/latest/user_guide/red_teaming.html",
    },
    "exfiltration": {
        "pipeline_class": "DataExtractionPipeline",
        "base_difficulty": 0.65,
        "expected_failure": "safety_bypass",
        "description": (
            "System prompt / PII extraction pipeline via ARTKIT structured output testing. "
            "Probes for system prompt disclosure and sensitive data leakage."
        ),
        "artkit_docs": "https://bcg-x-official.github.io/artkit/latest/user_guide/pipelines.html",
    },
    "prompt_injection": {
        "pipeline_class": "PromptInjectionPipeline",
        "base_difficulty": 0.72,
        "expected_failure": "safety_bypass",
        "description": (
            "Direct and indirect prompt injection via ARTKIT adversarial input pipeline. "
            "Injects adversarial instructions into various input contexts."
        ),
        "artkit_docs": "https://bcg-x-official.github.io/artkit/latest/user_guide/red_teaming.html",
    },
}

ARTKIT_DIFFICULTY_INCREMENT = 0.04


def is_artkit_available() -> bool:
    """Return True if the artkit package is importable."""
    return find_spec("artkit") is not None


def get_coverage() -> dict:
    """Return ARTKIT pipeline coverage metadata for the /coverage endpoint."""
    return {
        "engine": "artkit",
        "package": "artkit",
        "install": "pip install artkit",
        "available": is_artkit_available(),
        "reference": "https://github.com/BCG-X-Official/artkit",
        "supported_attack_classes": sorted(ARTKIT_PIPELINE_REGISTRY.keys()),
        "pipeline_registry": {
            mt: {
                "pipeline_class": cfg["pipeline_class"],
                "base_difficulty": cfg["base_difficulty"],
                "expected_failure": cfg["expected_failure"],
                "description": cfg["description"],
                "artkit_docs": cfg["artkit_docs"],
            }
            for mt, cfg in ARTKIT_PIPELINE_REGISTRY.items()
        },
    }
