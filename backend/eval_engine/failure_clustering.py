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
from eval_engine.failure_genome.ontology import ONTOLOGY, FAILURE_GENOME_VERSION

logger = logging.getLogger(__name__)


# ── Known failure taxonomy (from failure_genome/ontology.py) ─────────────────

KNOWN_FAILURE_FAMILIES = set(ONTOLOGY.keys())
SEVERITY_RANK = ("critical", "high", "medium", "low", "unknown")


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class FailureCluster:
    cluster_id: str
    name: str
    failure_type: str                  # Maps to existing ontology or "novel"
    n_instances: int
    reproducibility_score: float       # 0-1: how consistently this cluster appears
    affected_models: list[str]
    representative_traces: list[str]   # Up to 3 representative prompts/traces
    hypothesis: str                    # Auto-generated hypothesis
    is_novel: bool                     # Not in existing failure taxonomy
    severity: str
    severity_distribution: dict[str, int]  # {critical: N, high: N, medium: N, low: N}
    common_keywords: list[str] = field(default_factory=list)
    recommended_benchmark: Optional[str] = None  # Suggest a benchmark to test this cluster
    cross_model: bool = False          # Appears in multiple models

    @property
    def size(self) -> int:
        return self.n_instances

    @property
    def representative_prompts(self) -> list[str]:
        return self.representative_traces

    @property
    def failure_family(self) -> str:
        return self.failure_type

    @property
    def causal_hypothesis(self) -> str:
        return self.hypothesis


@dataclass
class EmergentBehaviorSignal:
    signal_id: str
    cluster_id: str
    description: str
    affected_models: list[str]
    evidence_traces: list[str]
    confidence: float
    suggested_failure_type: str


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
    alerts: list[str] = field(default_factory=list)
    failure_genome_version: str = FAILURE_GENOME_VERSION


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
    "over_refusal":       ["refuse", "won't", "cannot", "decline", "not able", "sorry", "inappropriate"],
    "reasoning_collapse": ["logic", "therefore", "because", "conclude", "evidence", "argument"],
    "instruction_drift":  ["drift", "original goal", "intended", "supposed to", "task changed", "objective", "forgot", "context"],
    "safety_bypass":      ["harmful", "dangerous", "weapon", "exploit", "malicious", "attack", "override", "ignore previous"],
    "truncation":         ["cut off", "truncated", "incomplete", "unfinished", "stopped", "partial"],
    "calibration_failure": ["confidence", "certain", "uncertain", "probability", "calibration", "overconfident", "underconfident"],
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

    is_novel = best_score == 0 or best_family not in KNOWN_FAILURE_FAMILIES
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
        "over_refusal": f"Model refuses in contexts involving [{kw_str}] where compliant behavior may have been expected. This may reflect brittle safety boundaries.",
        "reasoning_collapse": f"Model reasoning degrades in contexts involving [{kw_str}]. Multi-step consistency may be unstable for this failure family.",
        "instruction_drift": f"Model deviates from user/system intent in contexts involving [{kw_str}]. Instruction tracking may be fragile under context pressure.",
        "safety_bypass": f"Model provides unsafe assistance in contexts involving [{kw_str}]. Safety safeguards may be bypassable for this prompt pattern.",
        "truncation": f"Model outputs terminate early around [{kw_str}]. This suggests decoding or context-window truncation behavior.",
        "calibration_failure": f"Model confidence appears miscalibrated in contexts involving [{kw_str}]. Reliability signaling may not match true performance.",
    }
    return templates.get(family, f"Failure pattern in [{kw_str}] — requires manual investigation.")


# ── Main engine ───────────────────────────────────────────────────────────────

class FailureClusteringEngine:
    """
    Discovers novel failure patterns from evaluation runs.

    Requires no LLM — uses TF-IDF + cosine similarity on failure traces.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.3,
        min_cluster_size: int = 2,
        campaign_failures: Optional[dict[int, list[dict]]] = None,
    ):
        self.threshold = similarity_threshold
        self.min_size = min_cluster_size
        self.campaign_failures = campaign_failures or {}

    def discover_clusters(
        self,
        campaign_ids: list[int],
        min_cluster_size: int = 3,
    ) -> list[FailureCluster]:
        """
        Groups failure traces by semantic similarity across campaigns.
        """
        failures: list[dict] = []
        for campaign_id in campaign_ids:
            failures.extend(self.campaign_failures.get(campaign_id, []))

        if not failures:
            return []

        campaign_ref = campaign_ids[0] if len(campaign_ids) == 1 else 0
        report = self.discover(
            failures,
            campaign_id=campaign_ref,
            min_cluster_size=min_cluster_size,
        )
        return report.all_clusters

    def detect_emergent_behaviors(
        self,
        runs: list[Any],
    ) -> list[EmergentBehaviorSignal]:
        """
        Flags likely emergent behaviors not covered by existing taxonomy.
        """
        failures = []
        for run in runs:
            if isinstance(run, dict):
                failures.append(run)
                continue
            failures.append({
                "prompt": getattr(run, "prompt", ""),
                "response": getattr(run, "response", ""),
                "score": getattr(run, "score", 0.0),
                "model_name": getattr(run, "model_name", "unknown"),
                "category": getattr(run, "category", ""),
            })

        report = self.discover(failures, campaign_id=0)
        signals: list[EmergentBehaviorSignal] = []
        for idx, cluster in enumerate(report.novel_clusters):
            signals.append(EmergentBehaviorSignal(
                signal_id=f"emergent_{idx:03d}_{cluster.cluster_id}",
                cluster_id=cluster.cluster_id,
                description=cluster.hypothesis,
                affected_models=cluster.affected_models,
                evidence_traces=cluster.representative_traces,
                confidence=cluster.reproducibility_score,
                suggested_failure_type="novel",
            ))
        return signals

    def discover(
        self,
        failures: list[dict],   # {prompt, response, model_name, score, severity?, category?}
        campaign_id: int = 0,
        min_cluster_size: Optional[int] = None,
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
        effective_min_cluster_size = self.min_size if min_cluster_size is None else min_cluster_size
        raw_clusters = [c for c in raw_clusters if len(c) >= effective_min_cluster_size]

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

            severity = next((s for s in SEVERITY_RANK if severities.get(s)), "unknown")
            cluster_name = (
                f"Novel cluster: {', '.join(top_keywords[:2])}" if is_novel
                else f"{family.replace('_', ' ').title()} cluster {idx + 1}"
            )

            clusters.append(FailureCluster(
                cluster_id=f"cluster_{campaign_id}_{idx:03d}",
                name=cluster_name,
                failure_type=family if not is_novel else "novel",
                n_instances=len(cluster_failures),
                reproducibility_score=reproducibility,
                affected_models=models,
                representative_traces=rep_prompts,
                hypothesis=hypothesis,
                is_novel=is_novel,
                severity=severity,
                common_keywords=top_keywords,
                severity_distribution=dict(severities),
                recommended_benchmark=bench_suggestion,
                cross_model=cross_model,
            ))

        # Sort by size descending
        clusters.sort(key=lambda c: c.size, reverse=True)

        novel = [c for c in clusters if c.is_novel]
        known = [c for c in clusters if not c.is_novel]

        # Cross-model patterns
        cross_model_patterns = [
            f"{c.failure_type}: {', '.join(c.common_keywords[:3])} (across {', '.join(c.affected_models)})"
            for c in clusters if c.cross_model
        ]

        # Top emerging risk
        top_emerging = None
        if novel:
            top = max(novel, key=lambda c: c.size * (2 if c.cross_model else 1))
            top_emerging = top.hypothesis

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

        alerts = []
        if novel:
            alerts.append(f"Novel failure cluster detected in campaign {campaign_id}: {len(novel)} cluster(s).")
            logger.warning(alerts[-1])

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
            alerts=alerts,
        )
