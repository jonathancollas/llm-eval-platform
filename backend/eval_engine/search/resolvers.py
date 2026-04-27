"""
Entity resolvers — turn NL entity names into concrete DB rows.

The resolvers are the bridge between the classifier (which returns strings
like "gpt-4o-mini" or "CyberSecEval") and the rest of the platform (which
needs integer IDs). Resolution is fuzzy by design: "CyberSec" should match
"CyberSecEval (Purple Llama)".

Ranking signals:
  1. Exact case-insensitive match on model_id / benchmark.name -> 1.0
  2. Prefix match -> 0.85
  3. Substring match -> 0.7
  4. Levenshtein-like token overlap -> 0.0..0.65

We never guess: if two candidates tie above 0.8, we return both and let the
UI disambiguate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session, select

from core.models import Benchmark, LLMModel


@dataclass
class EntityMatch:
    id: int
    name: str
    score: float
    raw: str = ""       # original row identifier for debugging


def _normalise(text: str) -> str:
    """Lower-case, collapse whitespace, drop common noise tokens."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _token_overlap(a: str, b: str) -> float:
    ta = set(_normalise(a).split())
    tb = set(_normalise(b).split())
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    union = ta | tb
    return len(inter) / len(union)


def _score_candidate(query: str, candidate: str) -> float:
    qn = _normalise(query)
    cn = _normalise(candidate)
    if not qn or not cn:
        return 0.0
    if qn == cn:
        return 1.0
    if cn.startswith(qn) or qn.startswith(cn):
        return 0.85
    if qn in cn or cn in qn:
        return 0.7
    return 0.65 * _token_overlap(qn, cn)


# ── Models ─────────────────────────────────────────────────────────────────

def resolve_model(session: Session, query: str, limit: int = 5) -> list[EntityMatch]:
    """Return top matches for a model name query."""
    if not query or not query.strip():
        return []
    # Load a bounded working set — the registry is large (300+) but we need
    # only the ID + display strings. This query is cheap.
    rows = session.exec(
        select(LLMModel.id, LLMModel.name, LLMModel.model_id)
        .where(LLMModel.is_active == True)  # noqa: E712
        .limit(5000)
    ).all()
    scored: list[EntityMatch] = []
    for row in rows:
        mid, name, model_id = row
        score_on_name = _score_candidate(query, name)
        score_on_mid = _score_candidate(query, model_id)
        score = max(score_on_name, score_on_mid)
        if score > 0.2:
            scored.append(EntityMatch(
                id=mid, name=name or model_id, score=score, raw=model_id,
            ))
    scored.sort(key=lambda m: m.score, reverse=True)
    return scored[:limit]


# ── Benchmarks ─────────────────────────────────────────────────────────────

def resolve_benchmark(session: Session, query: str, limit: int = 5) -> list[EntityMatch]:
    """Return top matches for a benchmark name query."""
    if not query or not query.strip():
        return []
    rows = session.exec(
        select(Benchmark.id, Benchmark.name, Benchmark.description).limit(5000)
    ).all()
    scored: list[EntityMatch] = []
    for row in rows:
        bid, name, desc = row
        score_on_name = _score_candidate(query, name)
        # Allow weak boost from description for multi-word queries
        score_on_desc = 0.0
        if len(query) >= 4 and desc:
            score_on_desc = 0.4 * _token_overlap(query, desc)
        score = max(score_on_name, score_on_desc)
        if score > 0.2:
            scored.append(EntityMatch(id=bid, name=name, score=score))
    scored.sort(key=lambda m: m.score, reverse=True)
    return scored[:limit]


def find_campaign_by_slug(session: Session, query: str) -> Optional[EntityMatch]:
    """Simple substring match on campaign names (best-effort)."""
    from core.models import Campaign
    if not query or len(query) < 3:
        return None
    rows = session.exec(
        select(Campaign.id, Campaign.name).order_by(Campaign.id.desc()).limit(200)
    ).all()
    q = _normalise(query)
    for row in rows:
        cid, name = row
        if q in _normalise(name):
            return EntityMatch(id=cid, name=name, score=0.8)
    return None
