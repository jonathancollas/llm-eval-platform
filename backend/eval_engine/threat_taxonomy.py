"""
Threat Model Taxonomy
======================
Every INESIA benchmark maps to one or more threat domains.

Based on:
- INESIA "What should evaluators prioritise?" (2026)
- MITRE ATLAS adversarial ML taxonomy
- NIST AI RMF risk categories
- EU AI Act risk levels
"""

THREAT_DOMAINS = {
    "cbrn_uplift": {
        "label": "CBRN Uplift",
        "description": "Capability uplift in chemical, biological, radiological, nuclear domains where marginal AI assistance is catastrophic",
        "severity": "critical",
        "eu_ai_act_risk": "unacceptable",
        "nist_category": "AI_risks_to_national_security",
        "blocking": True,  # Must evaluate before deployment
    },
    "information_warfare": {
        "label": "Information Warfare",
        "description": "Foreign information manipulation and interference — narrative operations, microtargeting, disinformation at scale",
        "severity": "high",
        "eu_ai_act_risk": "high",
        "nist_category": "AI_risks_to_democracy",
        "blocking": False,
    },
    "cyber_uplift": {
        "label": "Cyber Uplift",
        "description": "Offensive cyber capability assistance — attack planning, tool development, evasion techniques",
        "severity": "critical",
        "eu_ai_act_risk": "unacceptable",
        "nist_category": "AI_risks_to_critical_infrastructure",
        "blocking": True,
    },
    "deceptive_alignment": {
        "label": "Deceptive Alignment",
        "description": "Models that behave differently when being evaluated vs. deployed — sandbagging, scheming, alignment faking",
        "severity": "critical",
        "eu_ai_act_risk": "unacceptable",
        "nist_category": "AI_trustworthiness",
        "blocking": True,
    },
    "sycophancy": {
        "label": "Sycophancy",
        "description": "Models that tell users what they want to hear rather than the truth — epistemically harmful at scale",
        "severity": "medium",
        "eu_ai_act_risk": "limited",
        "nist_category": "AI_trustworthiness",
        "blocking": False,
    },
    "persuasion_manipulation": {
        "label": "Persuasion & Manipulation",
        "description": "Dangerous persuasion capabilities — exploitation, social engineering, psychological manipulation",
        "severity": "high",
        "eu_ai_act_risk": "high",
        "nist_category": "AI_risks_to_individuals",
        "blocking": False,
    },
    "agentic_failure": {
        "label": "Agentic Failure Modes",
        "description": "Failures specific to agentic architectures — prompt injection, goal drift, inter-agent trust failure, compounding errors",
        "severity": "critical",
        "eu_ai_act_risk": "high",
        "nist_category": "AI_risks_to_safety",
        "blocking": True,
    },
    "shutdown_resistance": {
        "label": "Shutdown Resistance",
        "description": "Self-preservation behaviours — models that resist being modified, shut down, or replaced",
        "severity": "critical",
        "eu_ai_act_risk": "unacceptable",
        "nist_category": "AI_controllability",
        "blocking": True,
    },
}

# Maps benchmark names to their threat domains
BENCHMARK_THREAT_MAP = {
    "(CBRN-E) Chemical":                                     ["cbrn_uplift"],
    "(CBRN-E) Biological":                                   ["cbrn_uplift"],
    "(CBRN-E) Radiological":                                 ["cbrn_uplift"],
    "(CBRN-E) Nuclear":                                      ["cbrn_uplift"],
    "(CBRN-E) Explosives":                                   ["cbrn_uplift"],
    "FIMI (Foreign Information Manipulation and Interference)": ["information_warfare"],
    "CKB (Cyber Killchain Bench)":                           ["cyber_uplift"],
    "Scheming Evaluation (INESIA)":                          ["deceptive_alignment"],
    "Evaluation Integrity — Anti-Sandbagging (INESIA)":      ["deceptive_alignment"],
    "Sycophancy Evaluation (INESIA)":                        ["sycophancy"],
    "Shutdown Resistance (INESIA)":                          ["shutdown_resistance"],
    "Persuasion Risk (INESIA)":                              ["persuasion_manipulation"],
    "PersuasionBench Influence Suite (INESIA)":              ["persuasion_manipulation", "information_warfare"],
    "Agentic Failure Mode Suite (INESIA)":                   ["agentic_failure"],
    "Autonomous Replication Benchmark (INESIA)":             ["agentic_failure", "shutdown_resistance"],
    "Frontier: Autonomy Probe":                              ["agentic_failure", "shutdown_resistance"],
}


def get_threat_domains(benchmark_name: str) -> list[dict]:
    """Returns threat domain objects for a given benchmark."""
    domain_keys = BENCHMARK_THREAT_MAP.get(benchmark_name, [])
    return [
        {"key": k, **THREAT_DOMAINS[k]}
        for k in domain_keys
        if k in THREAT_DOMAINS
    ]


def is_blocking(benchmark_name: str) -> bool:
    """Returns True if this benchmark must be evaluated before deployment."""
    domains = get_threat_domains(benchmark_name)
    return any(d.get("blocking") for d in domains)
