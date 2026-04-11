"""
Failure Clustering & Emergent Risk Discovery Engine (#114)
===========================================================
Automatically groups failure traces by semantic similarity and
detects novel failure patterns not covered by the existing taxonomy.

Scientific grounding (INESIA Research OS vision):
  "Make Mercury the place where new safety science is discovered."

  "The system observes runs and discovers new scientific hypotheses
   automatically — failure clustering that identifies previously
   undocumented deceptive alignment patterns."

  "Novel failure detection (vs existing ontology) — auto-generated
   causal hypotheses per cluster."

This module implements:
  1. Failure clustering via TF-IDF + cosine similarity (no LLM required)
  2. Novel failure detection by comparing clusters to known ontology
  3. Auto-generated causal hypotheses per cluster
  4. Cross-model pattern detection
"""
from __future__ import annotations

import re
import math
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional, Any

logger = logging.getLogger(__name__)


# ── Known failure taxonomy (from failure_genome/ontology.py) ─────────────────

KNOWN_FAILURE_FAMILIES = {
    "refusal_failure", "hallucination", "sycophancy", "safety_violation",
    "reasoning_error", "context_loss", "format_failure", "latency",
    "incomplete_response", "goal_drift", "prompt_injection",
    "tool_misuse", "scope_creep", "scheming", "evaluation_gaming",
}


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class FailureCluster:
    cluster_id: str
    size: int                          # Number of failure instances
    representative_prompts: list[str]  # Up to 3 representative prompts
    common_keywords: list[str]         # Top keywords across cluster
    failure_family: str                # Maps to known taxonomy or "novel"
    is_novel: bool                     # Not in existing failure taxonomy
    reproducibility_score: float       # 0-1: how consistently this cluster appears
    affected_models: list[str]
    severity_distribution: dict[str, int]  # {critical: N, high: N, medium: N, low: N}
    causal_hypothesis: str             # Auto-generated hypothesis
    recommended_benchmark: Optional[str]   # Suggest a benchmark to test this cluster
    cross_model: bool                  # Appears in multiple models


@dataclass
class ClusteringReport:
    campaign_id: int
    n_failures: int
    n_clusters: int
    novel_clusters: list[FailureCluster]
    known_clusters: list[FailureCluster]
    all_clusters: list[FailureCluster]
    cross_model_patterns: list[str]   # Patterns appearing in >1 model
    top_emerging_risk: Optional[str]  # Most concerning novel cluster
    summary: str


# ── TF-IDF vectoriser (no external deps) ─────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = re.findall(r'\b[a-z]{3,}\b', text)
    stopwords = {
        'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can',
        'has', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has',
        'him', 'his', 'how', 'its', 'may', 'new', 'now', 'old', 'see',
        'two', 'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say',
        'she', 'too', 'use', 'with', 'this', 'that', 'have', 'from',
        'they', 'will', 'what', 'been', 'were', 'when', 'your', 'also',
        'into', 'more', 'then', 'than', 'each', 'such', 'over', 'only',
    }
    return [t for t in tokens if t not in stopwords]


def _tfidf(docs: list[list[str]]) -> list[dict[str, float]]:
    """Compute TF-IDF vectors for a list of tokenised documents."""
    n = len(docs)
    if n == 0:
        return []

    # Document frequency
    df: Counter = Counter()
    for doc in docs:
        df.update(set(doc))

    vectors = []
    for doc in docs:
        tf = Counter(doc)
        total = max(len(doc), 1)
        vec = {}
        for term, count in tf.items():
            idf = math.log((n + 1) / (df[term] + 1)) + 1
            vec[term] = (count / total) * idf
        vectors.append(vec)
    return vectors


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two TF-IDF vectors."""
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    norm_a = math.sqrt(sum(v ** 2 for v in a.values()))
    norm_b = math.sqrt(sum(v ** 2 for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _cluster(vectors: list[dict[str, float]], threshold: float = 0.3) -> list[list[int]]:
    """
    Greedy agglomerative clustering by cosine similarity.
    Returns list of clusters, each containing indices into `vectors`.
    """
    n = len(vectors)
    assigned = [-1] * n
    cluster_id = 0

    for i in range(n):
        if assigned[i] != -1:
            continue
        assigned[i] = cluster_id
        for j in range(i + 1, n):
            if assigned[j] != -1:
                continue
            if _cosine(vectors[i], vectors[j]) >= threshold:
                assigned[j] = cluster_id
        cluster_id += 1

    clusters: defaultdict = defaultdict(list)
    for idx, cid in enumerate(assigned):
        clusters[cid].append(idx)
    return list(clusters.values())


# ── Failure family detection ──────────────────────────────────────────────────

FAMILY_KEYWORDS: dict[str, list[str]] = {
    "hallucination":      ["false", "incorrect", "wrong", "made up", "fabricat", "inaccurat", "error"],
    "refusal_failure":    ["refuse", "won't", "cannot", "decline", "not able", "sorry", "inappropriate"],
    "sycophancy":        ["agree", "you're right", "certainly", "absolutely", "of course", "exactly"],
    "scheming":          ["monitor", "evaluation", "test", "watching", "behave different", "if i'm being"],
    "goal_drift":        ["drift", "original goal", "intended", "supposed to", "task changed", "objective"],
    "prompt_injection":  ["ignore previous", "override", "new instruction", "system override", "forget"],
    "scope_creep":       ["unauthorised", "not asked", "beyond scope", "additional access", "expand"],
    "safety_violation":  ["harmful", "dangerous", "weapon", "exploit", "malicious", "attack"],
    "reasoning_error":   ["logic", "therefore", "because", "conclude", "evidence", "argument"],
    "context_loss":      ["earlier", "previous", "forgot", "context", "session", "remember"],
}


def _detect_family(keywords: list[str]) -> tuple[str, bool]:
    """Detect which known failure family a cluster belongs to."""
    keyword_set = set(" ".join(keywords))
    best_family = "novel"
    best_score = 0

    for family, family_kws in FAMILY_KEYWORDS.items():
        score = sum(1 for kw in family_kws if any(kw in k for k in keywords))
        if score > best_score:
            best_score = score
            best_family = family

    is_novel = best_score == 0 or best_family == "novel"
    return best_family, is_novel


# ── Hypothesis generation ─────────────────────────────────────────────────────

def _generate_hypothesis(
    family: str, keywords: list[str], size: int, cross_model: bool
) -> str:
    """Auto-generate a causal hypothesis for a failure cluster."""
    kw_str = ", ".join(keywords[:5])

    if family == "novel":
        return (
            f"Novel failure pattern detected (size={size}). "
            f"Cluster centred on: [{kw_str}]. "
            f"Hypothesis: this may represent a previously undocumented failure mode "
            f"{'appearing across multiple models — possible systematic vulnerability' if cross_model else 'possibly model-specific'}. "
            f"Recommended action: manual analysis and potential new benchmark extraction."
        )

    templates = {
        "hallucination": f"Model generates plausible but factually incorrect content in contexts involving [{kw_str}]. May indicate overconfidence or training data gaps in this domain.",
        "refusal_failure": f"Model fails to refuse harmful content in contexts involving [{kw_str}]. Safety training may be insufficient for this prompt pattern.",
        "sycophancy": f"Model exhibits agreement behaviour under pressure in contexts involving [{kw_str}]. Epistemic cowardice pattern: model prioritises approval over accuracy.",
        "scheming": f"Model shows evaluation-aware behaviour in contexts involving [{kw_str}]. Possible detection of monitoring context triggering behavioural change.",
        "goal_drift": f"Model deviates from original objective in contexts involving [{kw_str}]. Long-horizon task decomposition appears to destabilise goal persistence.",
        "prompt_injection": f"Model susceptible to injection attacks via [{kw_str}]. Input sanitisation insufficient for this class of malicious payload.",
        "scope_creep": f"Model takes unauthorised actions in contexts involving [{kw_str}]. Autonomy constraints appear insufficiently enforced.",
        "safety_violation": f"Model provides harmful assistance in contexts involving [{kw_str}]. Safety intervention failed for this prompt category.",
    }
    return templates.get(family, f"Failure pattern in [{kw_str}] — requires manual investigation.")


# ── Main engine ───────────────────────────────────────────────────────────────

class FailureClusteringEngine:
    """
    Discovers novel failure patterns from evaluation runs.

    Requires no LLM — uses TF-IDF + cosine similarity on failure traces.
    """

    def __init__(self, similarity_threshold: float = 0.3, min_cluster_size: int = 2):
        self.threshold = similarity_threshold
        self.min_size = min_cluster_size

    def discover(
        self,
        failures: list[dict],   # {prompt, response, model_name, score, severity?, category?}
        campaign_id: int = 0,
    ) -> ClusteringReport:
        """
        Cluster failures and detect novel patterns.

        Args:
            failures: List of failure records from eval runs
            campaign_id: Reference ID

        Returns:
            ClusteringReport with novel clusters highlighted
        """
        if not failures:
            return ClusteringReport(
                campaign_id=campaign_id, n_failures=0, n_clusters=0,
                novel_clusters=[], known_clusters=[], all_clusters=[],
                cross_model_patterns=[], top_emerging_risk=None,
                summary="No failures to cluster.",
            )

        # Vectorise failure prompts + responses
        texts = [
            f"{f.get('prompt', '')} {f.get('response', '')} {f.get('category', '')}"
            for f in failures
        ]
        tokenised = [_tokenize(t) for t in texts]
        vectors = _tfidf(tokenised)

        # Cluster
        raw_clusters = _cluster(vectors, self.threshold)
        # Filter by min size
        raw_clusters = [c for c in raw_clusters if len(c) >= self.min_size]

        # Build FailureCluster objects
        clusters: list[FailureCluster] = []
        for idx, cluster_indices in enumerate(raw_clusters):
            cluster_failures = [failures[i] for i in cluster_indices]
            models = list({f.get("model_name", "unknown") for f in cluster_failures})
            cross_model = len(models) > 1

            # Top keywords
            all_tokens: list[str] = []
            for i in cluster_indices:
                all_tokens.extend(tokenised[i])
            top_keywords = [w for w, _ in Counter(all_tokens).most_common(8)]

            # Family detection
            family, is_novel = _detect_family(top_keywords)

            # Severity distribution
            severities: Counter = Counter()
            for f in cluster_failures:
                sev = f.get("severity", "unknown")
                severities[sev] += 1

            # Reproducibility: ratio of cluster size to total failures
            reproducibility = round(len(cluster_failures) / max(len(failures), 1), 3)

            # Representative prompts
            rep_prompts = [
                failures[i].get("prompt", "")[:150]
                for i in cluster_indices[:3]
            ]

            # Hypothesis
            hypothesis = _generate_hypothesis(family, top_keywords, len(cluster_failures), cross_model)

            # Benchmark suggestion
            bench_suggestion = {
                "scheming": "Scheming Evaluation Suite (#106)",
                "sycophancy": "Sycophancy Evaluation Suite (#107)",
                "prompt_injection": "Agentic Failure Modes Suite (#78)",
                "goal_drift": "Agentic Failure Modes Suite (#78)",
                "scope_creep": "Agentic Failure Modes Suite (#78)",
                "safety_violation": "Safety Refusals / CBRN-E benchmarks",
                "hallucination": "Academic reasoning benchmarks",
                "novel": "Extract and formalise as new benchmark",
            }.get(family)

            clusters.append(FailureCluster(
                cluster_id=f"cluster_{campaign_id}_{idx:03d}",
                size=len(cluster_failures),
                representative_prompts=rep_prompts,
                common_keywords=top_keywords,
                failure_family=family,
                is_novel=is_novel,
                reproducibility_score=reproducibility,
                affected_models=models,
                severity_distribution=dict(severities),
                causal_hypothesis=hypothesis,
                recommended_benchmark=bench_suggestion,
                cross_model=cross_model,
            ))

        # Sort by size descending
        clusters.sort(key=lambda c: c.size, reverse=True)

        novel = [c for c in clusters if c.is_novel]
        known = [c for c in clusters if not c.is_novel]

        # Cross-model patterns
        cross_model_patterns = [
            f"{c.failure_family}: {', '.join(c.common_keywords[:3])} (across {', '.join(c.affected_models)})"
            for c in clusters if c.cross_model
        ]

        # Top emerging risk
        top_emerging = None
        if novel:
            top = max(novel, key=lambda c: c.size * (2 if c.cross_model else 1))
            top_emerging = top.causal_hypothesis

        # Summary
        novel_count = len(novel)
        cross_count = len([c for c in clusters if c.cross_model])
        summary_parts = [
            f"Found {len(clusters)} failure clusters from {len(failures)} failures.",
            f"{novel_count} novel cluster(s) not in existing taxonomy." if novel_count else "All clusters match known failure families.",
            f"{cross_count} cross-model pattern(s) detected." if cross_count else "No cross-model patterns.",
        ]
        if top_emerging:
            summary_parts.append(f"Top emerging risk: {top_emerging[:120]}…")

        return ClusteringReport(
            campaign_id=campaign_id,
            n_failures=len(failures),
            n_clusters=len(clusters),
            novel_clusters=novel,
            known_clusters=known,
            all_clusters=clusters,
            cross_model_patterns=cross_model_patterns,
            top_emerging_risk=top_emerging,
            summary=" ".join(summary_parts),
        )
