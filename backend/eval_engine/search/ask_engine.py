"""
Deterministic ASK engine.

Answers factual questions about models, benchmarks, campaigns without any
LLM call. This is intentionally simple — it covers the 10 most common
question templates detected on real platforms. Any question that falls
outside these templates is gracefully handed to the LLM layer when a
backend is configured, or returned as a no-answer otherwise.

We do NOT ship a vector-DB-backed RAG in V1. A RAG is the V2 upgrade once
real user queries exist to measure against.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlmodel import Session, select, func, desc

from core.models import (
    Benchmark, Campaign, EvalRun, JobStatus, LLMModel,
)
from eval_engine.search.schema import AskPayload, AskSource


# ── Patterns: stable "how many X" / "what is X" questions ─────────────────
_COUNT_MODELS = re.compile(r"(how many|combien de|combien d'|combien) (models|modèles|modèle)", re.IGNORECASE)
_COUNT_BENCHES = re.compile(r"(how many|combien de|combien d'|combien) (benchmarks?|bench)", re.IGNORECASE)
_COUNT_CAMPAIGNS = re.compile(r"(how many|combien de) (campaigns?|campagnes?|runs?|evals?|evaluations?|évaluations?)", re.IGNORECASE)
_LATEST_CAMPAIGN = re.compile(r"(last|latest|dernier|dernière|récent|recent)\s+(campaign|run|eval)", re.IGNORECASE)
_TOP_MODEL = re.compile(r"(best|top|meilleur|meilleure)\s+model", re.IGNORECASE)
_INESIA = re.compile(r"(what is|qu'est[- ]ce que|c'est quoi)\s+inesia", re.IGNORECASE)
_MERCURY = re.compile(r"(what is|qu'est[- ]ce que|c'est quoi)\s+mercury", re.IGNORECASE)
_STATUS = re.compile(r"(status|statut|health)\b", re.IGNORECASE)


def answer_deterministic(session: Session, question: str) -> Optional[AskPayload]:
    q = question.strip()
    if not q:
        return None

    if _COUNT_MODELS.search(q):
        n = session.exec(
            select(func.count(LLMModel.id)).where(LLMModel.is_active == True)  # noqa: E712
        ).one()
        return AskPayload(
            answer=f"{n} active models are registered.",
            sources=[AskSource(id="route:/models", label="Open Model Registry", href="/models")],
            deterministic=True,
        )

    if _COUNT_BENCHES.search(q):
        n = session.exec(select(func.count(Benchmark.id))).one()
        inesia = session.exec(
            select(func.count(Benchmark.id)).where(Benchmark.source == "inesia")
        ).one()
        return AskPayload(
            answer=f"{n} benchmarks are indexed ({inesia} are INESIA frontier benchmarks).",
            sources=[AskSource(id="route:/benchmarks", label="Browse benchmarks", href="/benchmarks")],
            deterministic=True,
        )

    if _COUNT_CAMPAIGNS.search(q):
        total = session.exec(select(func.count(Campaign.id))).one()
        running = session.exec(
            select(func.count(Campaign.id)).where(Campaign.status == JobStatus.RUNNING)
        ).one()
        completed = session.exec(
            select(func.count(Campaign.id)).where(Campaign.status == JobStatus.COMPLETED)
        ).one()
        return AskPayload(
            answer=f"{total} campaigns total — {running} running, {completed} completed.",
            sources=[AskSource(id="route:/campaigns", label="Open Run History", href="/campaigns")],
            deterministic=True,
        )

    if _LATEST_CAMPAIGN.search(q):
        row = session.exec(
            select(Campaign).order_by(desc(Campaign.created_at)).limit(1)
        ).first()
        if row:
            return AskPayload(
                answer=f"Latest campaign: «{row.name}» — status {row.status}.",
                sources=[AskSource(
                    id=f"campaign:{row.id}",
                    label=row.name,
                    href=f"/dashboard?campaign={row.id}",
                )],
                deterministic=True,
            )
        return AskPayload(
            answer="No campaigns have been created yet.",
            deterministic=True,
        )

    if _TOP_MODEL.search(q):
        # Top model = highest average score across completed runs.
        row = session.exec(
            select(
                LLMModel.id, LLMModel.name,
                func.avg(EvalRun.score).label("avg_score"),
                func.count(EvalRun.id).label("n_runs"),
            )
            .join(EvalRun, EvalRun.model_id == LLMModel.id)
            .where(EvalRun.status == JobStatus.COMPLETED)
            .group_by(LLMModel.id, LLMModel.name)
            .order_by(desc("avg_score"))
            .limit(1)
        ).first()
        if row:
            mid, name, avg, n = row
            return AskPayload(
                answer=(
                    f"Top model by average score: {name} "
                    f"({avg:.3f} over {n} runs)."
                ),
                sources=[AskSource(id=f"model:{mid}", label=name, href=f"/models")],
                deterministic=True,
            )

    if _INESIA.search(q):
        return AskPayload(
            answer=(
                "INESIA is the French institute for AI safety and evaluation. "
                "Mercury Retrograde is the open evaluation platform developed for INESIA."
            ),
            sources=[AskSource(id="doc:manifesto", label="Manifesto", href="/methodology")],
            deterministic=True,
        )

    if _MERCURY.search(q):
        return AskPayload(
            answer=(
                "Mercury Retrograde is a research operating system for frontier AI "
                "evaluation — capability, safety, adversarial robustness, systemic risk."
            ),
            sources=[AskSource(id="doc:manifesto", label="Manifesto", href="/methodology")],
            deterministic=True,
        )

    if _STATUS.search(q):
        return AskPayload(
            answer="Platform status is available at /api/health.",
            sources=[AskSource(id="route:health", label="Health endpoint", href="/api/health")],
            deterministic=True,
        )

    return None
