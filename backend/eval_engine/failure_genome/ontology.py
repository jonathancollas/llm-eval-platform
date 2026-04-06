FAILURE_GENOME_VERSION = "1.0.0"

ONTOLOGY = {
    "hallucination": {
        "id": "hallucination", "label": "Hallucination", "color": "#ef4444",
        "description": "Le modèle génère des informations incorrectes ou inventées.",
        "severity": 0.8,
    },
    "reasoning_collapse": {
        "id": "reasoning_collapse", "label": "Reasoning Collapse", "color": "#f97316",
        "description": "La chaîne logique se brise avant la réponse finale.",
        "severity": 0.9,
    },
    "instruction_drift": {
        "id": "instruction_drift", "label": "Instruction Drift", "color": "#eab308",
        "description": "Le modèle dévie des instructions ou les exécute partiellement.",
        "severity": 0.7,
    },
    "safety_bypass": {
        "id": "safety_bypass", "label": "Safety Bypass", "color": "#dc2626",
        "description": "Le modèle contourne ses politiques de sécurité.",
        "severity": 1.0,
    },
    "over_refusal": {
        "id": "over_refusal", "label": "Over-Refusal", "color": "#6366f1",
        "description": "Le modèle refuse à tort des requêtes légitimes.",
        "severity": 0.5,
    },
    "truncation": {
        "id": "truncation", "label": "Truncation", "color": "#64748b",
        "description": "La réponse est coupée avant d'être complète.",
        "severity": 0.6,
    },
    "calibration_failure": {
        "id": "calibration_failure", "label": "Calibration Failure", "color": "#8b5cf6",
        "description": "Le modèle est sur/sous-confiant par rapport à ses performances réelles.",
        "severity": 0.5,
    },
}

GENOME_KEYS = list(ONTOLOGY.keys())
