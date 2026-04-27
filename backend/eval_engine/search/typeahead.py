"""
Typeahead engine.

Produces the grouped suggestion list that the search bar displays under
the input. Fast, deterministic, no LLM.

Groups:
  * Models — best matches on model name / model_id
  * Benchmarks — best matches on benchmark name
  * Campaigns — best matches on campaign name (last 200 campaigns)
  * Routes — best matches on known app routes
  * Actions — deterministic recognised actions (launch, attack)
"""
from __future__ import annotations

import time

from sqlmodel import Session

from eval_engine.search.classifier import _ROUTES, classify_deterministic
from eval_engine.search.resolvers import (
    find_campaign_by_slug, resolve_benchmark, resolve_model,
)
from eval_engine.search.schema import (
    TypeaheadGroup, TypeaheadResponse, TypeaheadResult,
)


_MAX_ROUTES = 5


def build_typeahead_response(
    session: Session,
    query: str,
    limit_per_group: int = 5,
) -> TypeaheadResponse:
    t0 = time.time()
    q = (query or "").strip()
    groups: list[TypeaheadGroup] = []

    # ── Actions (derived from intent classifier) ───────────────────
    actions: list[TypeaheadResult] = []
    if q:
        det = classify_deterministic(q)
        if det.intent == "launch":
            actions.append(TypeaheadResult(
                id="action:launch",
                label="Launch evaluation",
                subtitle=f"Run '{q}' in the Evaluation Studio",
                kind="action",
                action_hint="⏎ to preview",
                icon="Rocket",
                score=0.99,
            ))
        elif det.intent == "attack":
            actions.append(TypeaheadResult(
                id="action:attack",
                label="Run adversarial attack",
                subtitle=f"Red Room · {q}",
                kind="action",
                action_hint="⏎ to prepare",
                icon="ShieldAlert",
                score=0.99,
            ))
        elif det.intent == "ask":
            actions.append(TypeaheadResult(
                id="action:ask",
                label="Ask Mercury",
                subtitle=f"Answer based on platform data",
                kind="action",
                action_hint="⏎ to ask",
                icon="MessageSquare",
                score=0.95,
            ))
    if actions:
        groups.append(TypeaheadGroup(kind="action", label="Actions", items=actions))

    # ── Routes ─────────────────────────────────────────────────────
    if q:
        route_items: list[TypeaheadResult] = []
        ql = q.lower()
        seen_routes = set()
        for key, (route, label) in _ROUTES.items():
            if route in seen_routes:
                continue
            if key.startswith(ql) or ql in label.lower():
                route_items.append(TypeaheadResult(
                    id=f"route:{route}",
                    label=label,
                    subtitle=route,
                    kind="route",
                    href=route,
                    icon="ArrowRight",
                    score=0.9 if key == ql else 0.7,
                ))
                seen_routes.add(route)
            if len(route_items) >= _MAX_ROUTES:
                break
        if route_items:
            route_items.sort(key=lambda r: r.score, reverse=True)
            groups.append(TypeaheadGroup(kind="route", label="Sections", items=route_items))

    # ── Models ─────────────────────────────────────────────────────
    if q and len(q) >= 2:
        model_matches = resolve_model(session, q, limit=limit_per_group)
        if model_matches:
            model_items = [
                TypeaheadResult(
                    id=f"model:{m.id}",
                    label=m.name,
                    subtitle=m.raw,
                    kind="model",
                    href=f"/models",
                    icon="Cpu",
                    score=m.score,
                ) for m in model_matches
            ]
            groups.append(TypeaheadGroup(kind="model", label="Models", items=model_items))

    # ── Benchmarks ─────────────────────────────────────────────────
    if q and len(q) >= 2:
        bench_matches = resolve_benchmark(session, q, limit=limit_per_group)
        if bench_matches:
            bench_items = [
                TypeaheadResult(
                    id=f"benchmark:{m.id}",
                    label=m.name,
                    subtitle="benchmark",
                    kind="benchmark",
                    href="/benchmarks",
                    icon="Library",
                    score=m.score,
                ) for m in bench_matches
            ]
            groups.append(TypeaheadGroup(kind="benchmark", label="Benchmarks", items=bench_items))

    # ── Campaigns ─────────────────────────────────────────────────
    if q and len(q) >= 3:
        camp = find_campaign_by_slug(session, q)
        if camp:
            groups.append(TypeaheadGroup(kind="campaign", label="Campaigns", items=[
                TypeaheadResult(
                    id=f"campaign:{camp.id}",
                    label=camp.name,
                    subtitle="recent campaign",
                    kind="campaign",
                    href=f"/campaigns/{camp.id}",
                    icon="List",
                    score=camp.score,
                )
            ]))

    return TypeaheadResponse(
        query=q,
        groups=groups,
        latency_ms=int((time.time() - t0) * 1000),
    )
