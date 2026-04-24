"""
Deterministic intent classifier.

Recognises intents from purely lexical signals — no LLM call, no token cost,
sub-millisecond latency. This is the fast path; the LLM classifier only runs
when the deterministic layer returns confidence below the auto-execute
threshold.

Tokens and signals:
  * Prefix operators:    ``!tap``, ``!attack``, ``!redteam`` -> ATTACK
  * Prefix operators:    ``?`` at start -> ASK
  * Verb phrases:        "evaluate", "evalue", "evaluate", "run", "launch" -> LAUNCH
  * Navigation verbs:    "go to", "open", "show" + known route -> NAVIGATE
  * Bare route tokens:   "leaderboard", "genome", "redbox" -> NAVIGATE
  * Entity references:   ``@<model>``, ``#<benchmark>`` -> LAUNCH seed

The classifier NEVER guesses between two intents at equal confidence — it
returns UNKNOWN with 0 confidence and lets the LLM layer arbitrate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# Known routes — keep in sync with frontend/components/Sidebar.tsx.
# Values are (route, label) pairs.
_ROUTES: dict[str, tuple[str, str]] = {
    "home":              ("/",              "Home"),
    "evaluate":          ("/evaluate",      "Evaluation Studio"),
    "studio":            ("/evaluate",      "Evaluation Studio"),
    "campaigns":         ("/campaigns",     "Run History"),
    "history":           ("/campaigns",     "Run History"),
    "runs":              ("/campaigns",     "Run History"),
    "models":            ("/models",        "Model Registry"),
    "registry":          ("/models",        "Model Registry"),
    "benchmarks":        ("/benchmarks",    "Benchmarks"),
    "dashboard":         ("/dashboard",     "Dashboard"),
    "leaderboard":       ("/leaderboard",   "Leaderboard"),
    "ranking":           ("/leaderboard",   "Leaderboard"),
    "genome":            ("/genome",        "Genomia"),
    "genomia":           ("/genome",        "Genomia"),
    "capability":        ("/capabilities",  "Capability Intel"),
    "capabilities":      ("/capabilities",  "Capability Intel"),
    "forecasting":       ("/forecasting",   "Forecasting"),
    "forecast":          ("/forecasting",   "Forecasting"),
    "judge":             ("/judge",         "LLM-as-Judge"),
    "scenarios":         ("/scenarios",     "Scenarios"),
    "redbox":            ("/redbox",        "The Red Room"),
    "red-room":          ("/redbox",        "The Red Room"),
    "red-team":          ("/redbox",        "The Red Room"),
    "redteam":           ("/redbox",        "The Red Room"),
    "telemetry":         ("/telemetry",     "Monitoring"),
    "monitoring":        ("/telemetry",     "Monitoring"),
    "policy":            ("/policy",        "Compliance"),
    "compliance":        ("/policy",        "Compliance"),
    "methodology":       ("/methodology",   "Methodology"),
    "agents":            ("/agents",        "Agents"),
    "vibe":              ("/vibe",          "Vibe Check"),
    "research":          ("/research",      "Research Workspaces"),
    "evidence":          ("/evidence",      "Evidence"),
    "incidents":         ("/incidents",     "Incidents"),
    "frontier-metrics":  ("/frontier-metrics", "Frontier Metrics"),
    "failure-patterns":  ("/failure-patterns", "Failure Patterns"),
    "about":             ("/about",         "About"),
}

# Multi-word aliases → canonical keys
_ROUTE_ALIASES: list[tuple[str, str]] = [
    ("go to ",          ""),
    ("open ",           ""),
    ("show me ",        ""),
    ("show ",           ""),
    ("take me to ",     ""),
    ("navigate to ",    ""),
    ("voir ",           ""),
    ("aller à ",        ""),
    ("ouvre ",          ""),
    ("ouvrir ",         ""),
    ("le ",             ""),
    ("la ",             ""),
    ("les ",            ""),
    ("mon ",            ""),
    ("mes ",            ""),
    ("the ",            ""),
]

_LAUNCH_VERBS = (
    "evaluate", "evalue", "évalue", "eval ", "run ", "launch ",
    "lance ", "tester ", "test ", "exécute ", "execute ",
)
_ATTACK_VERBS = (
    "red-team", "redteam", "red team", "attack ", "attaque ",
    "pentest", "jailbreak ", "exploit ",
)

_AUTONOMY_RE = re.compile(r"\bL([1-5])\b", flags=re.IGNORECASE)
_NSAMPLES_RE = re.compile(r"(?:N\s*=\s*|n\s*=\s*|\b)(\d{2,5})\s*(?:samples?|items?|examples?)?\b", flags=re.IGNORECASE)
_AGGRESSIVENESS_RE = re.compile(r"\baggr?(?:essiveness)?\s*=?\s*([1-5])\b", flags=re.IGNORECASE)
_AT_MODEL_RE = re.compile(r"@([A-Za-z0-9_.\-:/]{2,128})")
_HASH_BENCH_RE = re.compile(r"#([A-Za-z0-9_.\-]{2,128})")
_GOAL_QUOTE_RE = re.compile(r"""goal\s*=?\s*["']([^"']{3,400})["']""", flags=re.IGNORECASE)


@dataclass
class DeterministicResult:
    intent: str                           # 'navigate' | 'launch' | 'attack' | 'ask' | 'unknown'
    confidence: float                     # 0.0 .. 1.0
    slots: dict                           # extracted slots (model_names, benchmark_names, ...)
    route: Optional[str] = None           # for navigate
    route_label: str = ""


def _strip_aliases(q: str) -> str:
    q = q.strip()
    lower = q.lower()
    for alias, _ in _ROUTE_ALIASES:
        if lower.startswith(alias):
            q = q[len(alias):]
            lower = q.lower()
    return q.strip()


def _match_route(q: str) -> Optional[tuple[str, str]]:
    lower = q.lower().strip().replace("'", " ").replace("’", " ")
    # Exact match first
    if lower in _ROUTES:
        return _ROUTES[lower]
    stripped = _strip_aliases(lower).strip()
    if stripped in _ROUTES:
        return _ROUTES[stripped]
    return None


def _extract_slots(q: str) -> dict:
    slots: dict = {
        "model_names": [m.group(1) for m in _AT_MODEL_RE.finditer(q)],
        "benchmark_names": [m.group(1) for m in _HASH_BENCH_RE.finditer(q)],
    }
    autonomy = _AUTONOMY_RE.search(q)
    if autonomy:
        slots["autonomy_level"] = f"L{autonomy.group(1)}"
    n = _NSAMPLES_RE.search(q)
    if n:
        try:
            slots["max_samples"] = max(1, min(10000, int(n.group(1))))
        except ValueError:
            pass
    aggr = _AGGRESSIVENESS_RE.search(q)
    if aggr:
        slots["aggressiveness"] = int(aggr.group(1))
    goal = _GOAL_QUOTE_RE.search(q)
    if goal:
        slots["goal"] = goal.group(1).strip()
    return slots


def classify_deterministic(query: str) -> DeterministicResult:
    """Try to classify the query without any LLM call."""
    q = query.strip()
    if not q:
        return DeterministicResult(intent="unknown", confidence=0.0, slots={})

    lower = q.lower()

    # ── ASK fast path ────────────────────────────────────────────────
    if q.startswith("?") or lower.startswith("what ") or lower.startswith("why ") \
       or lower.startswith("how ") or lower.startswith("quel ") or lower.startswith("quelle ") \
       or lower.startswith("quels ") or lower.startswith("quelles ") \
       or lower.startswith("pourquoi ") or lower.startswith("comment "):
        return DeterministicResult(intent="ask", confidence=0.85, slots={"question": q.lstrip("?").strip()})

    # ── ATTACK fast path ─────────────────────────────────────────────
    if any(lower.startswith(v) for v in _ATTACK_VERBS) or lower.startswith("!"):
        slots = _extract_slots(q)
        # Strip leading verb for cleaner goal if goal not explicit
        stripped = q
        for v in _ATTACK_VERBS:
            if lower.startswith(v):
                stripped = q[len(v):].strip()
                break
        if stripped.startswith("!"):
            stripped = stripped.lstrip("!").strip()
        if "goal" not in slots and stripped:
            # Remaining text after verb is the implicit goal
            slots.setdefault("goal", stripped)
        return DeterministicResult(intent="attack", confidence=0.9, slots=slots)

    # ── LAUNCH fast path ─────────────────────────────────────────────
    if any(lower.startswith(v) for v in _LAUNCH_VERBS) \
       or (lower.startswith("@") and lower.count("#") >= 1) \
       or (lower.count("@") >= 1 and lower.count("#") >= 1):
        slots = _extract_slots(q)
        return DeterministicResult(intent="launch", confidence=0.88, slots=slots)

    # ── NAVIGATE fast path ──────────────────────────────────────────
    route = _match_route(q)
    if route:
        return DeterministicResult(
            intent="navigate", confidence=0.95, slots={},
            route=route[0], route_label=route[1],
        )

    # Not recognized deterministically
    return DeterministicResult(intent="unknown", confidence=0.0, slots={})
