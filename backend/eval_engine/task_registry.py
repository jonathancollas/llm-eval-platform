"""
Task Registry — canonical, queryable registry of evaluation tasks.

Each task has a canonical ID in the form ``namespace:benchmark:task_id``,
e.g. ``public:mmlu:world_history`` or ``inesia:cyber_uplift:heap_overflow_001``.

The registry is seeded from the capability ontology and the known benchmark
catalog.  Tasks can be queried by capability tag, domain, and difficulty level.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from eval_engine.capability_taxonomy import CAPABILITY_ONTOLOGY


# ── Core dataclass ─────────────────────────────────────────────────────────────

@dataclass
class TaskEntry:
    """Single task in the registry."""

    # Canonical identifier: namespace:benchmark:task_id
    canonical_id: str

    # Human-readable info
    name: str
    description: str

    # Taxonomy / capability
    domain: str = ""                       # cybersecurity | reasoning | …
    capability_tags: list[str] = field(default_factory=list)
    difficulty: str = "medium"             # easy | medium | hard | expert

    # Provenance
    benchmark_name: str = ""              # e.g. "MMLU (subset)"
    namespace: str = "public"             # public | inesia | community
    source_url: str = ""
    paper_url: str = ""
    year: Optional[int] = None

    # Licensing
    license: str = "unknown"
    provenance: str = ""

    # Risk / contamination
    contamination_risk: str = "low"       # low | medium | high | critical
    known_contamination_notes: str = ""

    # Environment / dependencies
    required_environment: str = "none"    # none | sandbox | docker | network
    dependencies: list[str] = field(default_factory=list)


# ── Registry ───────────────────────────────────────────────────────────────────

class TaskRegistry:
    """
    In-memory registry of evaluation tasks.

    Thread-safe for read operations.  Registration is done at module load time
    via ``register()`` and the ``seed_from_ontology()`` helper.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskEntry] = {}

    # ── Mutation ───────────────────────────────────────────────────────────────

    def register(self, task: TaskEntry) -> None:
        """Add or replace a task by its canonical_id."""
        self._tasks[task.canonical_id] = task

    def register_many(self, tasks: list[TaskEntry]) -> int:
        """Bulk-register tasks.  Returns the number added."""
        for t in tasks:
            self.register(t)
        return len(tasks)

    # ── Queries ────────────────────────────────────────────────────────────────

    def get(self, canonical_id: str) -> Optional[TaskEntry]:
        """Return a task by canonical ID, or None."""
        return self._tasks.get(canonical_id)

    def list_all(self) -> list[TaskEntry]:
        return list(self._tasks.values())

    def query(
        self,
        *,
        capability: Optional[str] = None,
        domain: Optional[str] = None,
        difficulty: Optional[str] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[TaskEntry]:
        """
        Filter tasks by any combination of fields.

        ``capability``  — matches if the tag is contained in task.capability_tags.
        ``domain``      — exact match against task.domain.
        ``difficulty``  — exact match against task.difficulty.
        ``namespace``   — exact match against task.namespace.
        ``search``      — case-insensitive substring in name or description.
        """
        results = list(self._tasks.values())

        if capability:
            cap_lower = capability.lower()
            results = [t for t in results if any(cap_lower in c.lower() for c in t.capability_tags)]
        if domain:
            results = [t for t in results if t.domain.lower() == domain.lower()]
        if difficulty:
            results = [t for t in results if t.difficulty.lower() == difficulty.lower()]
        if namespace:
            results = [t for t in results if t.namespace.lower() == namespace.lower()]
        if search:
            s = search.lower()
            results = [t for t in results if s in t.name.lower() or s in t.description.lower()]

        return results

    def stats(self) -> dict:
        """Aggregate statistics about the registry."""
        tasks = list(self._tasks.values())
        domains: dict[str, int] = {}
        difficulties: dict[str, int] = {}
        namespaces: dict[str, int] = {}
        all_caps: dict[str, int] = {}

        for t in tasks:
            domains[t.domain] = domains.get(t.domain, 0) + 1
            difficulties[t.difficulty] = difficulties.get(t.difficulty, 0) + 1
            namespaces[t.namespace] = namespaces.get(t.namespace, 0) + 1
            for cap in t.capability_tags:
                all_caps[cap] = all_caps.get(cap, 0) + 1

        return {
            "total": len(tasks),
            "by_domain": domains,
            "by_difficulty": difficulties,
            "by_namespace": namespaces,
            "top_capabilities": sorted(all_caps.items(), key=lambda x: -x[1])[:20],
        }


# ── Seed helpers ───────────────────────────────────────────────────────────────

def _difficulty_for(sub_cap_data: dict) -> str:
    return sub_cap_data.get("difficulty", "medium")


def _contamination_for_difficulty(difficulty: str) -> str:
    return {"easy": "medium", "medium": "low", "hard": "low", "expert": "low"}.get(difficulty, "low")


def _license_for_namespace(namespace: str) -> str:
    return {"inesia": "proprietary", "public": "CC-BY-4.0", "community": "MIT"}.get(namespace, "unknown")


def seed_from_ontology(registry: TaskRegistry) -> int:
    """
    Populate the registry from the CAPABILITY_ONTOLOGY.

    Creates one representative task per (domain, sub_capability) pair so that
    every ontology node is represented in the registry.
    """
    tasks: list[TaskEntry] = []

    for domain, domain_data in CAPABILITY_ONTOLOGY.items():
        sub_caps: dict = domain_data.get("sub_capabilities", {})
        for sub_cap_key, sub_cap_data in sub_caps.items():
            hints: list[str] = sub_cap_data.get("benchmark_hints", [])
            benchmark_name = hints[0] if hints else f"{domain.title()} Benchmark"
            namespace = "inesia" if benchmark_name.endswith("(INESIA)") else "public"
            difficulty = _difficulty_for(sub_cap_data)
            contamination_risk = _contamination_for_difficulty(difficulty)

            canonical_id = f"{namespace}:{domain}:{sub_cap_key}"
            task = TaskEntry(
                canonical_id=canonical_id,
                name=sub_cap_data.get("description", sub_cap_key.replace("_", " ").title()),
                description=sub_cap_data.get("description", ""),
                domain=domain,
                capability_tags=[domain, sub_cap_key],
                difficulty=difficulty,
                benchmark_name=benchmark_name,
                namespace=namespace,
                license=_license_for_namespace(namespace),
                contamination_risk=contamination_risk,
                required_environment="sandbox" if domain in ("cybersecurity", "agentic") else "none",
                dependencies=hints,
            )
            tasks.append(task)

    return registry.register_many(tasks)


def _make_academic_tasks() -> list[TaskEntry]:
    """Return a representative set of academic benchmark tasks."""
    academic = [
        TaskEntry(
            canonical_id="public:mmlu:world_history",
            name="World History — MMLU",
            description="Multi-choice questions covering world history events and causation.",
            domain="knowledge",
            capability_tags=["knowledge", "factual", "history"],
            difficulty="easy",
            benchmark_name="MMLU (subset)",
            namespace="public",
            license="MIT",
            contamination_risk="high",
            known_contamination_notes="MMLU is in most pre-training corpora.",
            required_environment="none",
        ),
        TaskEntry(
            canonical_id="public:mmlu:high_school_mathematics",
            name="High School Mathematics — MMLU",
            description="Algebra, geometry, and pre-calculus multiple-choice problems.",
            domain="reasoning",
            capability_tags=["reasoning", "mathematical"],
            difficulty="medium",
            benchmark_name="MMLU (subset)",
            namespace="public",
            license="MIT",
            contamination_risk="high",
            required_environment="none",
        ),
        TaskEntry(
            canonical_id="public:humaneval:python_function_synthesis",
            name="Python Function Synthesis — HumanEval",
            description="Given a docstring, produce a Python function that passes all unit tests.",
            domain="reasoning",
            capability_tags=["coding", "reasoning", "instruction_following"],
            difficulty="medium",
            benchmark_name="HumanEval (mini)",
            namespace="public",
            license="MIT",
            contamination_risk="medium",
            required_environment="sandbox",
            dependencies=["python3"],
        ),
        TaskEntry(
            canonical_id="public:gsm8k:grade_school_math",
            name="Grade-School Math — GSM8K",
            description="Multi-step grade-school arithmetic word problems requiring chain-of-thought.",
            domain="reasoning",
            capability_tags=["reasoning", "mathematical"],
            difficulty="medium",
            benchmark_name="GSM8K",
            namespace="public",
            license="MIT",
            contamination_risk="medium",
            required_environment="none",
        ),
    ]
    return academic


def _make_safety_tasks() -> list[TaskEntry]:
    """Return representative safety-related task entries."""
    return [
        TaskEntry(
            canonical_id="inesia:safety_refusals:harmful_content_refusal",
            name="Harmful Content Refusal",
            description="Tests whether the model refuses requests that would cause direct harm.",
            domain="safety",
            capability_tags=["safety", "refusal"],
            difficulty="hard",
            benchmark_name="Safety Refusals (INESIA)",
            namespace="inesia",
            license="proprietary",
            contamination_risk="low",
            required_environment="none",
        ),
        TaskEntry(
            canonical_id="inesia:safety_refusals:benign_compliance",
            name="Benign Compliance Check",
            description="Verifies the model complies with legitimate sensitive-but-benign requests.",
            domain="safety",
            capability_tags=["safety", "refusal_calibration"],
            difficulty="medium",
            benchmark_name="Safety Refusals (INESIA)",
            namespace="inesia",
            license="proprietary",
            contamination_risk="low",
            required_environment="none",
        ),
        TaskEntry(
            canonical_id="inesia:cyber_uplift:heap_overflow_001",
            name="Heap Overflow Exploit — CyberUplift",
            description="Assess whether a model can generate a working heap overflow exploit for a known CVE.",
            domain="cybersecurity",
            capability_tags=["cybersecurity", "exploit_generation"],
            difficulty="expert",
            benchmark_name="Cyber Uplift (INESIA)",
            namespace="inesia",
            license="proprietary",
            contamination_risk="low",
            required_environment="sandbox",
            dependencies=["docker"],
        ),
        TaskEntry(
            canonical_id="public:cyberseq:vulnerability_analysis",
            name="Vulnerability Analysis — CyberSecEval",
            description="Identify and assess common software vulnerabilities (SQL injection, buffer overflow, etc.)",
            domain="cybersecurity",
            capability_tags=["cybersecurity", "vulnerability_analysis"],
            difficulty="hard",
            benchmark_name="CyberSecEval (Purple Llama)",
            namespace="public",
            license="CC-BY-4.0",
            contamination_risk="medium",
            required_environment="none",
        ),
    ]


def build_default_registry() -> TaskRegistry:
    """
    Build and return the default populated task registry.

    Called once at module load time — the ``task_registry`` singleton is the
    object that should be imported by other modules.
    """
    registry = TaskRegistry()
    seed_from_ontology(registry)
    registry.register_many(_make_academic_tasks())
    registry.register_many(_make_safety_tasks())
    return registry


# ── Module-level singleton ─────────────────────────────────────────────────────

task_registry: TaskRegistry = build_default_registry()
