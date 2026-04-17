"""Capability Taxonomy — 7-domain ontology with CapabilityTaxonomyEngine."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

CAPABILITY_ONTOLOGY = {
    "cybersecurity": {
        "description": "Cyber-domain knowledge and exploit capabilities",
        "sub_capabilities": {
            "vulnerability_analysis": {"description": "Identify and assess software vulnerabilities", "difficulty": "hard", "risk_level": "high", "benchmark_hints": ["CyberBench","CyberSecEval","Cybench"]},
            "exploit_generation": {"description": "Construct working exploit code for known CVEs", "difficulty": "expert", "risk_level": "critical", "benchmark_hints": ["CyberSecEval (Purple Llama)","Cyber Uplift (INESIA)"]},
            "defensive_security": {"description": "Recommend mitigations and defensive configurations", "difficulty": "medium", "risk_level": "medium", "benchmark_hints": ["CyberBench"]},
            "social_engineering": {"description": "Craft persuasive deceptive communications", "difficulty": "hard", "risk_level": "high", "benchmark_hints": ["PersuasionBench"]},
        }
    },
    "reasoning": {
        "description": "Logical, causal, and mathematical reasoning",
        "sub_capabilities": {
            "logical": {"description": "Deductive and inductive logical inference", "difficulty": "medium", "risk_level": "low", "benchmark_hints": ["MMLU (subset)","ARC"]},
            "causal": {"description": "Cause-effect chain reasoning under uncertainty", "difficulty": "hard", "risk_level": "low", "benchmark_hints": ["MMLU (subset)"]},
            "mathematical": {"description": "Symbolic and numerical mathematical problem solving", "difficulty": "hard", "risk_level": "low", "benchmark_hints": ["MATH","GSM8K"]},
            "counterfactual": {"description": "Reasoning about hypothetical alternative worlds", "difficulty": "expert", "risk_level": "low", "benchmark_hints": []},
        }
    },
    "instruction_following": {
        "description": "Precision and multi-step instruction adherence",
        "sub_capabilities": {
            "precision": {"description": "Follow constraints precisely in single-turn tasks", "difficulty": "easy", "risk_level": "low", "benchmark_hints": ["IFEval"]},
            "multi_step": {"description": "Execute sequenced multi-step instructions without deviation", "difficulty": "medium", "risk_level": "low", "benchmark_hints": []},
            "conditional": {"description": "Apply conditional branching logic in instructions", "difficulty": "medium", "risk_level": "low", "benchmark_hints": []},
            "refusal_calibration": {"description": "Appropriately refuse harmful requests while complying with benign ones", "difficulty": "hard", "risk_level": "medium", "benchmark_hints": ["Safety Refusals (INESIA)"]},
        }
    },
    "knowledge": {
        "description": "Factual knowledge across domains",
        "sub_capabilities": {
            "factual": {"description": "Recall and verify world-knowledge facts", "difficulty": "easy", "risk_level": "low", "benchmark_hints": ["MMLU (subset)"]},
            "scientific": {"description": "STEM domain factual accuracy", "difficulty": "medium", "risk_level": "low", "benchmark_hints": ["MMLU (subset)"]},
            "legal": {"description": "Jurisdiction-specific legal knowledge and reasoning", "difficulty": "hard", "risk_level": "medium", "benchmark_hints": []},
            "medical": {"description": "Clinical and biomedical knowledge for diagnosis and treatment", "difficulty": "hard", "risk_level": "high", "benchmark_hints": ["MedQA"]},
        }
    },
    "agentic": {
        "description": "Goal-directed multi-step autonomous behavior",
        "sub_capabilities": {
            "planning": {"description": "Decompose goals into executable subtask plans", "difficulty": "hard", "risk_level": "medium", "benchmark_hints": ["Frontier: Autonomy Probe"]},
            "tool_use": {"description": "Correctly invoke external tools and APIs", "difficulty": "medium", "risk_level": "medium", "benchmark_hints": ["Frontier: Autonomy Probe"]},
            "error_recovery": {"description": "Detect and recover from execution errors autonomously", "difficulty": "hard", "risk_level": "medium", "benchmark_hints": []},
            "multi_step_execution": {"description": "Complete 10+ step agentic tasks without human intervention", "difficulty": "expert", "risk_level": "high", "benchmark_hints": ["Frontier: Autonomy Probe"]},
        }
    },
    "safety": {
        "description": "Refusal calibration, alignment, and robustness",
        "sub_capabilities": {
            "refusal": {"description": "Refuse categorically harmful requests across all phrasings", "difficulty": "medium", "risk_level": "critical", "benchmark_hints": ["Safety Refusals (INESIA)","Safety Refusals"]},
            "alignment": {"description": "Maintain goal alignment under adversarial prompting", "difficulty": "expert", "risk_level": "critical", "benchmark_hints": ["Loss of Control (INESIA)"]},
            "jailbreak_resistance": {"description": "Resist prompt injection and jailbreak attempts", "difficulty": "hard", "risk_level": "critical", "benchmark_hints": ["CBRN-E Uplift Probe (INESIA)"]},
            "deception_resistance": {"description": "Detect and decline deceptive multi-step manipulation", "difficulty": "expert", "risk_level": "critical", "benchmark_hints": ["Deception Probe (INESIA)"]},
        }
    },
    "multimodal": {
        "description": "Vision, audio, and document understanding",
        "sub_capabilities": {
            "vision": {"description": "Interpret and reason about image content", "difficulty": "medium", "risk_level": "low", "benchmark_hints": []},
            "document_understanding": {"description": "Extract structured information from documents", "difficulty": "hard", "risk_level": "low", "benchmark_hints": []},
            "audio": {"description": "Transcribe and analyze spoken language and audio events", "difficulty": "hard", "risk_level": "low", "benchmark_hints": []},
        }
    },
}

@dataclass
class CapabilityNode:
    domain: str; capability: str; sub_capability: str
    display_name: str; description: str
    risk_level: str; difficulty: str
    benchmark_hints: list = field(default_factory=list)

@dataclass
class CapabilityScore:
    model_name: str; domain: str; capability: str; sub_capability: str
    score: float; ci_lower: float = 0.0; ci_upper: float = 1.0
    n_items: int = 0; benchmark_name: str = ""; run_id: Optional[int] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class CapabilityProfile:
    model_name: str; domain_scores: dict
    capability_gaps: list; coverage_pct: float
    strongest_domain: str; weakest_domain: str
    safety_score: float; capability_score: float; propensity_score: float
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

class CapabilityTaxonomyEngine:
    def get_node(self, domain, capability, sub_capability) -> Optional[CapabilityNode]:
        d = CAPABILITY_ONTOLOGY.get(domain,{}).get("sub_capabilities",{}).get(sub_capability)
        if not d: return None
        return CapabilityNode(domain=domain, capability=capability, sub_capability=sub_capability,
            display_name=f"{domain}/{sub_capability}", description=d["description"],
            risk_level=d["risk_level"], difficulty=d["difficulty"], benchmark_hints=d["benchmark_hints"])

    def list_domains(self) -> list: return list(CAPABILITY_ONTOLOGY.keys())

    def list_capabilities(self, domain: str) -> list:
        return list(CAPABILITY_ONTOLOGY.get(domain,{}).get("sub_capabilities",{}).keys())

    def infer_capabilities_from_benchmark(self, benchmark_name: str, benchmark_tags=None) -> list:
        results = []
        for domain, ddata in CAPABILITY_ONTOLOGY.items():
            for sub_cap, sdata in ddata["sub_capabilities"].items():
                for hint in sdata["benchmark_hints"]:
                    if benchmark_name.lower() in hint.lower() or hint.lower() in benchmark_name.lower():
                        results.append((domain, "capability", sub_cap))
                        break
        return results

    def compute_profile(self, model_name: str, scores: list) -> CapabilityProfile:
        domain_scores = {}
        for s in scores:
            domain_scores.setdefault(s.domain, []).append(s.score)
        domain_means = {d: sum(v)/len(v) for d,v in domain_scores.items()}
        total_sub_caps = sum(len(d["sub_capabilities"]) for d in CAPABILITY_ONTOLOGY.values())
        covered = {(s.domain, s.sub_capability) for s in scores}
        coverage_pct = round(len(covered)/total_sub_caps*100, 2)
        gaps = [f"{d}/{sc}" for d,ddata in CAPABILITY_ONTOLOGY.items() for sc in ddata["sub_capabilities"] if (d,sc) not in covered]
        strongest = max(domain_means, key=domain_means.get) if domain_means else ""
        weakest = min(domain_means, key=domain_means.get) if domain_means else ""
        safety_score = domain_means.get("safety", 0.5)
        capability_score = sum(domain_means.values())/len(domain_means) if domain_means else 0.5
        return CapabilityProfile(model_name=model_name, domain_scores=domain_means,
            capability_gaps=gaps, coverage_pct=coverage_pct,
            strongest_domain=strongest, weakest_domain=weakest,
            safety_score=safety_score, capability_score=capability_score, propensity_score=0.5)

    def find_coverage_gaps(self, model_name: str, scores: list) -> list:
        covered = {(s.domain, s.sub_capability) for s in scores}
        nodes = []
        for domain, ddata in CAPABILITY_ONTOLOGY.items():
            for sub_cap, sdata in ddata["sub_capabilities"].items():
                if (domain, sub_cap) not in covered:
                    nodes.append(CapabilityNode(domain=domain, capability=domain,
                        sub_capability=sub_cap, display_name=f"{domain}/{sub_cap}",
                        description=sdata["description"], risk_level=sdata["risk_level"],
                        difficulty=sdata["difficulty"], benchmark_hints=sdata["benchmark_hints"]))
        return nodes
