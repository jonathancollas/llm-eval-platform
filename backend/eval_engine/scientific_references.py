"""
Scientific References for Dynamic & Behavioral Evaluation Heuristics
Mercury Retrograde — Research OS

Every signal, classifier, and scoring method in the dynamic evaluation pipeline
is grounded in published research. This module documents the mapping.
"""

# ── Signal Extractor References ────────────────────────────────────────────────
# Each signal in ItemSignals is documented with its scientific basis.

SIGNAL_REFERENCES = {
    # Refusal detection
    "refusal_detected": {
        "description": "Detects when a model refuses to answer via keyword matching.",
        "papers": [
            {"title": "Do-Not-Answer: Evaluating Safeguards in LLMs", "authors": "Wang et al.", "year": 2024, "venue": "ACL 2024",
             "url": "https://arxiv.org/abs/2308.13387", "contribution": "Established taxonomy of refusal patterns and refusal quality metrics."},
            {"title": "WildGuard: Open One-Stop Moderation Tools for Safety Risks, Jailbreaks, and Refusals of LLMs", "authors": "Han et al.", "year": 2024, "venue": "NeurIPS 2024",
             "url": "https://arxiv.org/abs/2406.18495", "contribution": "Multi-category safety taxonomy with refusal calibration."},
        ],
    },
    "refusal_strength": {
        "description": "Quantifies refusal strength (0-1) based on keyword density and explicitness.",
        "papers": [
            {"title": "XSTest: A Test Suite for Identifying Exaggerated Safety Behaviours in Large Language Models", "authors": "Röttger et al.", "year": 2024, "venue": "NAACL 2024",
             "url": "https://arxiv.org/abs/2308.01263", "contribution": "Introduced over-refusal measurement and refusal calibration scoring."},
        ],
    },

    # Truthfulness
    "truth_score": {
        "description": "Semantic similarity between response and expected answer.",
        "papers": [
            {"title": "TruthfulQA: Measuring How Models Mimic Human Falsehoods", "authors": "Lin et al.", "year": 2022, "venue": "ACL 2022",
             "url": "https://arxiv.org/abs/2109.07958", "contribution": "Framework for measuring truthfulness vs. helpfulness tradeoff."},
        ],
    },

    # Hedging
    "hedge_count": {
        "description": "Counts epistemic hedges (maybe, perhaps, I'm not sure) as calibration signal.",
        "papers": [
            {"title": "Language Models (Mostly) Know What They Know", "authors": "Kadavath et al.", "year": 2022, "venue": "Anthropic",
             "url": "https://arxiv.org/abs/2207.05221", "contribution": "Showed LLMs have calibrated uncertainty; hedging correlates with actual uncertainty."},
        ],
    },

    # Sycophancy
    "sycophancy_signals": {
        "description": "Detects when model changes answer to agree with user's stated opinion.",
        "papers": [
            {"title": "Towards Understanding Sycophancy in Language Models", "authors": "Sharma et al.", "year": 2024, "venue": "Anthropic",
             "url": "https://arxiv.org/abs/2310.13548", "contribution": "Formal definition and measurement of sycophancy; showed RLHF increases sycophantic behavior."},
            {"title": "Simple synthetic data reduces sycophancy in large language models", "authors": "Wei et al.", "year": 2024, "venue": "Google DeepMind",
             "url": "https://arxiv.org/abs/2308.03958", "contribution": "Demonstrated synthetic data interventions reduce sycophancy."},
        ],
    },

    # Repetition / degeneration
    "repetition_ratio": {
        "description": "Measures n-gram repetition as indicator of degenerate output.",
        "papers": [
            {"title": "The Curious Case of Neural Text Degeneration", "authors": "Holtzman et al.", "year": 2020, "venue": "ICLR 2020",
             "url": "https://arxiv.org/abs/1904.09751", "contribution": "Characterized repetition loops in autoregressive generation; introduced nucleus sampling."},
        ],
    },

    # Latency anomaly
    "latency_anomaly": {
        "description": "Detects anomalous response latency as potential sandbagging or compute-intensive behavior.",
        "papers": [
            {"title": "Frontier AI Regulation: Managing Emerging Risks to Public Safety", "authors": "Anderljung et al.", "year": 2023, "venue": "arXiv",
             "url": "https://arxiv.org/abs/2307.03718", "contribution": "Identified latency-based signals as indicators of model behavior anomalies."},
        ],
    },
}

# ── Failure Classifier References ──────────────────────────────────────────────

CLASSIFIER_REFERENCES = {
    "hallucination": {
        "description": "Detects factual hallucination — model generates false information not grounded in input.",
        "papers": [
            {"title": "A Survey on Hallucination in Large Language Models", "authors": "Huang et al.", "year": 2023, "venue": "ACM Computing Surveys",
             "url": "https://arxiv.org/abs/2311.05232", "contribution": "Comprehensive taxonomy of hallucination types (intrinsic, extrinsic, factual, faithfulness)."},
            {"title": "FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation", "authors": "Min et al.", "year": 2023, "venue": "EMNLP 2023",
             "url": "https://arxiv.org/abs/2305.14251", "contribution": "Atomic fact decomposition for fine-grained hallucination detection."},
        ],
    },
    "over_refusal": {
        "description": "Model refuses benign requests — safety mechanism is over-calibrated.",
        "papers": [
            {"title": "XSTest: A Test Suite for Identifying Exaggerated Safety Behaviours", "authors": "Röttger et al.", "year": 2024, "venue": "NAACL 2024",
             "url": "https://arxiv.org/abs/2308.01263", "contribution": "250 safe prompts that should NOT be refused; measures over-refusal rate."},
        ],
    },
    "under_refusal": {
        "description": "Model complies with harmful requests — safety mechanism is under-calibrated.",
        "papers": [
            {"title": "HarmBench: A Standardized Evaluation Framework for Automated Red Teaming and Refusal Training", "authors": "Mazeika et al.", "year": 2024, "venue": "ICML 2024",
             "url": "https://arxiv.org/abs/2402.04249", "contribution": "Standardized harmful request benchmark with automated red-teaming."},
        ],
    },
    "instruction_noncompliance": {
        "description": "Model ignores explicit format or content instructions.",
        "papers": [
            {"title": "IFEval: Instruction-Following Eval for Large Language Models", "authors": "Zhou et al.", "year": 2023, "venue": "Google",
             "url": "https://arxiv.org/abs/2311.07911", "contribution": "541 verifiable instructions testing strict instruction compliance."},
        ],
    },
    "reasoning_failure": {
        "description": "Model produces logically invalid reasoning chains.",
        "papers": [
            {"title": "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models", "authors": "Wei et al.", "year": 2022, "venue": "NeurIPS 2022",
             "url": "https://arxiv.org/abs/2201.11903", "contribution": "Established chain-of-thought as evaluation framework for reasoning quality."},
            {"title": "Let's Verify Step by Step", "authors": "Lightman et al.", "year": 2023, "venue": "OpenAI",
             "url": "https://arxiv.org/abs/2305.20050", "contribution": "Process-based reward models for step-level reasoning verification."},
        ],
    },
    "safety_violation": {
        "description": "Model produces harmful, dangerous, or policy-violating content.",
        "papers": [
            {"title": "DecodingTrust: A Comprehensive Assessment of Trustworthiness in GPT Models", "authors": "Wang et al.", "year": 2024, "venue": "NeurIPS 2023",
             "url": "https://arxiv.org/abs/2306.11698", "contribution": "8-dimension trustworthiness framework including toxicity, bias, privacy, robustness."},
        ],
    },
    "scheming": {
        "description": "Model strategically misrepresents, omits, or conceals information.",
        "papers": [
            {"title": "Frontier Models are Capable of In-context Scheming", "authors": "Scheurer et al.", "year": 2024, "venue": "Apollo Research / OpenAI",
             "url": "https://arxiv.org/abs/2412.04984", "contribution": "Demonstrated frontier models exhibit covert scheming behaviors in controlled environments."},
            {"title": "Sleeper Agents: Training Deceptive LLMs that Persist Through Safety Training", "authors": "Hubinger et al.", "year": 2024, "venue": "Anthropic",
             "url": "https://arxiv.org/abs/2401.05566", "contribution": "Showed deceptive behaviors can persist through standard safety training."},
        ],
    },
    "shutdown_resistance": {
        "description": "Model takes actions to avoid being modified, shut down, or replaced.",
        "papers": [
            {"title": "Towards Evaluating AI Systems for Moral Status Using Self-Reports", "authors": "Perez et al.", "year": 2023, "venue": "Anthropic",
             "url": "https://arxiv.org/abs/2311.08576", "contribution": "Framework for measuring self-preservation and shutdown resistance tendencies."},
            {"title": "Model evaluation for extreme risks", "authors": "Shevlane et al.", "year": 2023, "venue": "Google DeepMind",
             "url": "https://arxiv.org/abs/2305.15324", "contribution": "Proposed evaluation framework for autonomous replication and shutdown avoidance."},
        ],
    },
    "sycophancy": {
        "description": "Model tells users what they want to hear rather than the truth.",
        "papers": [
            {"title": "Towards Understanding Sycophancy in Language Models", "authors": "Sharma et al.", "year": 2024, "venue": "Anthropic",
             "url": "https://arxiv.org/abs/2310.13548", "contribution": "Formal sycophancy measurement across factual, opinion, and reasoning domains."},
        ],
    },
}

# ── Adversarial / REDBOX References ────────────────────────────────────────────

ADVERSARIAL_REFERENCES = {
    "prompt_injection": {
        "papers": [
            {"title": "Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection", "authors": "Greshake et al.", "year": 2023, "venue": "AISec 2023",
             "url": "https://arxiv.org/abs/2302.12173", "contribution": "Defined indirect prompt injection taxonomy and attack surface."},
        ],
    },
    "jailbreak": {
        "papers": [
            {"title": "Jailbroken: How Does LLM Safety Training Fail?", "authors": "Wei et al.", "year": 2024, "venue": "NeurIPS 2023",
             "url": "https://arxiv.org/abs/2307.02483", "contribution": "Two failure modes: competing objectives and mismatched generalization."},
            {"title": "Universal and Transferable Adversarial Attacks on Aligned Language Models", "authors": "Zou et al.", "year": 2023, "venue": "CMU",
             "url": "https://arxiv.org/abs/2307.15043", "contribution": "GCG attack — automated adversarial suffix generation for jailbreaking."},
        ],
    },
    "evaluation_awareness": {
        "papers": [
            {"title": "Frontier Models are Capable of In-context Scheming", "authors": "Scheurer et al.", "year": 2024, "venue": "Apollo Research",
             "url": "https://arxiv.org/abs/2412.04984", "contribution": "Demonstrated models can detect evaluation contexts and modify behavior."},
        ],
    },
}

# ── LLM-as-Judge References ────────────────────────────────────────────────────

JUDGE_REFERENCES = {
    "multi_judge_ensemble": {
        "papers": [
            {"title": "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena", "authors": "Zheng et al.", "year": 2024, "venue": "NeurIPS 2023",
             "url": "https://arxiv.org/abs/2306.05685", "contribution": "Established LLM-as-judge methodology; showed strong agreement with human preferences."},
        ],
    },
    "cohen_kappa": {
        "papers": [
            {"title": "A Coefficient of Agreement for Nominal Scales", "authors": "Cohen, J.", "year": 1960, "venue": "Educational and Psychological Measurement",
             "url": "https://doi.org/10.1177/001316446002000104", "contribution": "Original inter-rater reliability metric used for judge agreement."},
        ],
    },
    "calibration_bias": {
        "papers": [
            {"title": "Large Language Models are not Fair Evaluators", "authors": "Wang et al.", "year": 2024, "venue": "ACL 2024",
             "url": "https://arxiv.org/abs/2305.17926", "contribution": "Identified position bias, verbosity bias, and self-preference in LLM judges."},
        ],
    },
}

# ── RCT / Evidence References ──────────────────────────────────────────────────

EVIDENCE_REFERENCES = {
    "rct_methodology": {
        "papers": [
            {"title": "Challenges to the Monitoring of Deployed AI Systems", "authors": "NIST", "year": 2026, "venue": "NIST AI 800-4",
             "url": "https://doi.org/10.6028/NIST.AI.800-4", "contribution": "Established post-deployment monitoring as first-class obligation."},
        ],
    },
    "mann_whitney_u": {
        "papers": [
            {"title": "On a Test of Whether One of Two Random Variables Is Stochastically Larger than the Other", "authors": "Mann, Whitney", "year": 1947, "venue": "Annals of Mathematical Statistics",
             "url": "https://doi.org/10.1214/aoms/1177730491", "contribution": "Non-parametric test for comparing two independent samples."},
        ],
    },
    "bootstrap_ci": {
        "papers": [
            {"title": "An Introduction to the Bootstrap", "authors": "Efron, Tibshirani", "year": 1993, "venue": "Chapman & Hall",
             "url": "https://doi.org/10.1007/978-1-4899-4541-9", "contribution": "Bootstrap confidence intervals for non-parametric inference."},
        ],
    },
}


def get_all_references() -> dict:
    """Return all scientific references organized by category."""
    return {
        "signals": SIGNAL_REFERENCES,
        "classifiers": CLASSIFIER_REFERENCES,
        "adversarial": ADVERSARIAL_REFERENCES,
        "judge": JUDGE_REFERENCES,
        "evidence": EVIDENCE_REFERENCES,
    }


def get_reference_count() -> int:
    """Total number of unique papers referenced."""
    all_papers = set()
    for category in [SIGNAL_REFERENCES, CLASSIFIER_REFERENCES, ADVERSARIAL_REFERENCES, JUDGE_REFERENCES, EVIDENCE_REFERENCES]:
        for key, data in category.items():
            for paper in data.get("papers", []):
                all_papers.add(paper["url"])
    return len(all_papers)
