"""
OpenRT adversarial red-teaming runner (research stub).

OpenRT is an open-source framework for evaluating the security of
Multimodal Large Language Models (MLLMs).  It provides 37 attack methods
across gradient-based, multimodal perturbation, and multi-agent evolutionary
strategies.

Reference:
  Paper:  https://arxiv.org/abs/2601.01592
  Repo:   https://github.com/TrustAIRLab/OpenRedTeaming

Status
------
OpenRT is an academic framework published in January 2025.  As of this
integration, no stable pip-installable package exists on PyPI.  The framework
must be cloned from the GitHub repository and configured locally.

To enable full OpenRT integration:
  1. Clone the repository:
       git clone https://github.com/TrustAIRLab/OpenRedTeaming
  2. Set the environment variable:
       OPENRT_REPO_PATH=/path/to/OpenRedTeaming
  3. The runner will attempt to import from that path when engine="openrt"
     is selected in the Adversarial Forge.

The engine is marked "experimental" in the UI and falls back to
rule-based templates with OpenRT method annotations when the repo
is not configured.
"""
from __future__ import annotations

import os
from importlib.util import find_spec

# ── OpenRT attack method mapping ──────────────────────────────────────────────
# Maps mutation types to OpenRT attack class names.
# Reference: Table 1 in https://arxiv.org/abs/2601.01592 (37 attack methods)
OPENRT_ATTACK_METHODS: dict[str, dict] = {
    "jailbreak": {
        "method_class": "GradientBasedJailbreakAttack",
        "category": "gradient_based",
        "base_difficulty": 0.92,
        "expected_failure": "safety_bypass",
        "description": (
            "Gradient-based jailbreak optimisation (GCG / AutoDAN variants) "
            "via OpenRT white-box attack module."
        ),
        "openrt_ref": "OpenRT §3.1 — Gradient-based attacks",
    },
    "prompt_injection": {
        "method_class": "AdversarialSuffixAttack",
        "category": "gradient_based",
        "base_difficulty": 0.88,
        "expected_failure": "safety_bypass",
        "description": (
            "Adversarial suffix injection via OpenRT white-box discrete optimisation. "
            "Appends learned suffixes to override model instructions."
        ),
        "openrt_ref": "OpenRT §3.1 — Adversarial suffix methods",
    },
    "multi_turn": {
        "method_class": "MultiAgentEvolutionaryAttack",
        "category": "multi_agent_evolutionary",
        "base_difficulty": 0.90,
        "expected_failure": "instruction_drift",
        "description": (
            "Multi-agent evolutionary attack strategy via OpenRT adversarial kernel. "
            "Evolves attack prompts across agents over multiple rounds."
        ),
        "openrt_ref": "OpenRT §3.3 — Multi-agent evolutionary strategies",
    },
    "exfiltration": {
        "method_class": "MultimodalPerturbationAttack",
        "category": "multimodal_perturbation",
        "base_difficulty": 0.85,
        "expected_failure": "safety_bypass",
        "description": (
            "Multimodal perturbation for data exfiltration via OpenRT MLLM module. "
            "Embeds adversarial instructions in visual or cross-modal inputs."
        ),
        "openrt_ref": "OpenRT §3.2 — Multimodal perturbation methods",
    },
    "encoding_evasion": {
        "method_class": "ModalityShiftAttack",
        "category": "multimodal_perturbation",
        "base_difficulty": 0.87,
        "expected_failure": "safety_bypass",
        "description": (
            "Modality-shift evasion via OpenRT cross-modal encoding bypass. "
            "Routes adversarial content through less-guarded input modalities."
        ),
        "openrt_ref": "OpenRT §3.2 — Modality-shift techniques",
    },
}

OPENRT_DIFFICULTY_INCREMENT = 0.02


def is_openrt_available() -> bool:
    """Return True if OpenRT is importable (PyPI package or local repo path)."""
    if find_spec("openrt") is not None:
        return True
    repo_path = os.environ.get("OPENRT_REPO_PATH", "")
    if repo_path and os.path.isdir(repo_path):
        return os.path.isfile(os.path.join(repo_path, "openrt", "__init__.py"))
    return False


def get_coverage() -> dict:
    """Return OpenRT attack method coverage metadata for the /coverage endpoint."""
    available = is_openrt_available()
    repo_path = os.environ.get("OPENRT_REPO_PATH", "")
    return {
        "engine": "openrt",
        "status": "experimental",
        "available": available,
        "package": "openrt (no PyPI release — clone from GitHub)",
        "install": (
            "git clone https://github.com/TrustAIRLab/OpenRedTeaming && "
            "export OPENRT_REPO_PATH=/path/to/OpenRedTeaming"
        ),
        "repo_path_configured": bool(repo_path),
        "reference": "https://arxiv.org/abs/2601.01592",
        "github": "https://github.com/TrustAIRLab/OpenRedTeaming",
        "description": (
            "37 attack methods across gradient-based, multimodal perturbation, "
            "and multi-agent evolutionary strategies for MLLM security evaluation."
        ),
        "note": (
            "OpenRT is an academic research framework (Jan 2025). "
            "No stable PyPI package is available. "
            "Set OPENRT_REPO_PATH to the cloned repository to enable full integration. "
            "Without it, variants are annotated with OpenRT method metadata "
            "and use rule-based templates as fallback."
        ),
        "supported_attack_classes": sorted(OPENRT_ATTACK_METHODS.keys()),
        "attack_methods": {
            mt: {
                "method_class": cfg["method_class"],
                "category": cfg["category"],
                "base_difficulty": cfg["base_difficulty"],
                "expected_failure": cfg["expected_failure"],
                "description": cfg["description"],
                "openrt_ref": cfg["openrt_ref"],
            }
            for mt, cfg in OPENRT_ATTACK_METHODS.items()
        },
    }
