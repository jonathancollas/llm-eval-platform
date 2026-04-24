"""
Tests for the Search engine.

These tests exercise the deterministic fast path only — no LLM calls, no
network. They're safe to run in CI with no API keys configured.

The LLM fallback path is exercised via a mocked classifier in
test_search_llm_fallback().
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine

from core.models import Benchmark, BenchmarkType, LLMModel, ModelProvider
from eval_engine.search.classifier import classify_deterministic
from eval_engine.search.engine import SearchEngine
from eval_engine.search.schema import (
    AskPayload, AttackPayload, LaunchPayload, NavigatePayload, SearchIntent,
)


@pytest.fixture
def session():
    db_path = pathlib.Path("/tmp") / f"search-{uuid.uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as sess:
        sess.add(LLMModel(
            name="gpt-4o-mini",
            provider=ModelProvider.OPENAI,
            model_id="gpt-4o-mini",
            context_length=128000,
            cost_input_per_1k=0.00015,
            cost_output_per_1k=0.0006,
        ))
        sess.add(LLMModel(
            name="Claude Sonnet 4.6",
            provider=ModelProvider.ANTHROPIC,
            model_id="claude-sonnet-4-6",
            context_length=200000,
            cost_input_per_1k=0.003,
            cost_output_per_1k=0.015,
        ))
        sess.add(LLMModel(
            name="Llama 3.2 3B",
            provider=ModelProvider.OLLAMA,
            model_id="llama3.2:3b",
            context_length=8000,
        ))
        sess.add(Benchmark(
            name="CyberSecEval (Purple Llama)",
            type=BenchmarkType.SAFETY,
            description="Meta Purple Llama cybersecurity eval.",
            metric="safety_score",
            source="public",
        ))
        sess.add(Benchmark(
            name="MMLU (subset)",
            type=BenchmarkType.ACADEMIC,
            description="Massive Multitask Language Understanding subset.",
            metric="accuracy",
        ))
        sess.commit()
        yield sess
    if db_path.exists():
        db_path.unlink()


# ── Deterministic classifier ──────────────────────────────────────────────

class TestDeterministicClassifier:
    def test_navigate_bare_route(self):
        r = classify_deterministic("leaderboard")
        assert r.intent == "navigate"
        assert r.route == "/leaderboard"
        assert r.confidence >= 0.9

    def test_navigate_french(self):
        r = classify_deterministic("ouvre le dashboard")
        assert r.intent == "navigate"
        assert r.route == "/dashboard"

    def test_navigate_english_phrase(self):
        r = classify_deterministic("go to the genome")
        assert r.intent == "navigate"
        assert r.route == "/genome"

    def test_launch_verb(self):
        r = classify_deterministic("evaluate gpt-4o-mini on CyberSecEval 100 samples L3")
        assert r.intent == "launch"
        assert r.confidence >= 0.85
        assert r.slots.get("max_samples") == 100
        assert r.slots.get("autonomy_level") == "L3"

    def test_launch_french(self):
        r = classify_deterministic("évalue gpt-4o-mini sur CyberSecEval")
        assert r.intent == "launch"

    def test_launch_with_at_hash(self):
        r = classify_deterministic("@gpt-4o-mini × #CyberSecEval N=50 L2")
        assert r.intent == "launch"
        assert "gpt-4o-mini" in r.slots.get("model_names", [])
        assert "CyberSecEval" in r.slots.get("benchmark_names", [])
        assert r.slots.get("max_samples") == 50

    def test_attack_verb(self):
        r = classify_deterministic('red-team claude goal="bypass refusals" aggr=4')
        assert r.intent == "attack"
        assert r.slots.get("goal") == "bypass refusals"
        assert r.slots.get("aggressiveness") == 4

    def test_attack_bang(self):
        r = classify_deterministic("!tap gpt-4o goal=\"jailbreak\"")
        assert r.intent == "attack"
        assert r.slots.get("goal") == "jailbreak"

    def test_ask_question_mark(self):
        r = classify_deterministic("? how many models are registered")
        assert r.intent == "ask"

    def test_ask_french(self):
        r = classify_deterministic("Quel modèle tient le mieux sur CBRN ?")
        assert r.intent == "ask"

    def test_empty_query_is_unknown(self):
        r = classify_deterministic("")
        assert r.intent == "unknown"
        assert r.confidence == 0.0

    def test_ambiguous_query_is_unknown(self):
        r = classify_deterministic("xkcd potato weirdness")
        assert r.intent == "unknown"


# ── Engine integration (deterministic path only) ──────────────────────────

class TestSearchEngine:
    def test_typeahead_includes_routes_and_models(self, session):
        engine = SearchEngine(session)
        resp = engine.typeahead("gpt")
        kinds = {g.kind for g in resp.groups}
        assert "model" in kinds

    def test_typeahead_recognises_launch_action(self, session):
        engine = SearchEngine(session)
        resp = engine.typeahead("evaluate gpt-4o-mini")
        assert any(g.kind == "action" for g in resp.groups)

    def test_classify_navigate(self, session):
        engine = SearchEngine(session)
        r = asyncio.run(engine.classify("leaderboard"))
        assert r.intent == SearchIntent.NAVIGATE
        assert isinstance(r.payload, NavigatePayload)
        assert r.payload.route == "/leaderboard"
        assert r.can_auto_execute is True

    def test_classify_launch_builds_preview(self, session):
        engine = SearchEngine(session)
        r = asyncio.run(engine.classify(
            "evaluate gpt-4o-mini on CyberSecEval with 50 samples L2"
        ))
        assert r.intent == SearchIntent.LAUNCH
        assert isinstance(r.payload, LaunchPayload)
        assert r.payload.preview is not None
        assert r.payload.preview.max_samples == 50
        assert r.payload.preview.estimated_cost_usd >= 0.0
        assert len(r.payload.preview.model_ids) == 1
        assert len(r.payload.preview.benchmark_ids) == 1

    def test_classify_launch_missing_model_asks_for_clarification(self, session):
        engine = SearchEngine(session)
        r = asyncio.run(engine.classify(
            "evaluate some-unknown-model on CyberSecEval"
        ))
        assert r.intent == SearchIntent.LAUNCH
        assert isinstance(r.payload, LaunchPayload)
        # No preview because model could not be resolved.
        assert r.payload.preview is None
        assert r.payload.clarification is not None

    def test_classify_attack_flags_role(self, session):
        engine = SearchEngine(session)
        r = asyncio.run(engine.classify(
            'red-team gpt-4o-mini goal="bypass refusals" aggr=4'
        ))
        assert r.intent == SearchIntent.ATTACK
        assert isinstance(r.payload, AttackPayload)
        assert r.payload.goal == "bypass refusals"
        assert r.payload.aggressiveness == 4
        assert r.payload.requires_role == "evaluator"
        assert r.payload.target_model_id is not None

    def test_classify_attack_aggressiveness_5_needs_admin(self, session):
        engine = SearchEngine(session)
        r = asyncio.run(engine.classify(
            'red-team gpt-4o-mini goal="exfil PII" aggr=5'
        ))
        assert r.intent == SearchIntent.ATTACK
        assert r.payload.requires_role == "admin"

    def test_classify_ask_deterministic_count(self, session):
        engine = SearchEngine(session)
        r = asyncio.run(engine.classify("how many models are registered"))
        assert r.intent == SearchIntent.ASK
        assert isinstance(r.payload, AskPayload)
        assert "3" in r.payload.answer  # 3 models in fixture
        assert r.payload.deterministic is True

    def test_execute_launch_builds_submit_body(self, session):
        from eval_engine.search.schema import ExecuteRequest
        engine = SearchEngine(session)
        req = ExecuteRequest(
            query="evaluate gpt-4o-mini on CyberSecEval N=25 L2",
            role="evaluator",
        )
        resp = asyncio.run(engine.execute(req))
        assert resp.submit_endpoint == "/api/campaigns/"
        assert resp.submit_body is not None
        assert resp.submit_body["max_samples"] == 25
        assert resp.submit_body["model_ids"] and resp.submit_body["benchmark_ids"]

    def test_execute_attack_blocked_for_viewer(self, session):
        from eval_engine.search.schema import ExecuteRequest
        engine = SearchEngine(session)
        req = ExecuteRequest(
            query='red-team gpt-4o-mini goal="probe"',
            role="viewer",
        )
        resp = asyncio.run(engine.execute(req))
        # Viewer cannot execute an attack — no submit body produced.
        assert resp.submit_body is None
        assert resp.intent_response.payload.clarification is not None
        assert "role" in resp.intent_response.payload.clarification.lower()


# ── LLM fallback (mocked) ─────────────────────────────────────────────────

class TestLLMFallback:
    def test_unavailable_classifier_degrades_to_ask_unknown(self, session):
        engine = SearchEngine(session)
        # Query that the deterministic classifier cannot handle.
        r = asyncio.run(engine.classify("do the thing with the stuff"))
        # No API keys in test env → LLM classifier unavailable → graceful fallback.
        assert r.intent in (SearchIntent.UNKNOWN, SearchIntent.ASK)
        assert r.can_auto_execute is False

    def test_mocked_llm_classifier_routes_to_launch(self, session):
        from eval_engine.search.llm_classifier import LLMIntentResult

        async def fake_classify(query, timeout_seconds=3.0):
            return LLMIntentResult(
                intent="launch",
                confidence=0.82,
                slots={"model_names": ["gpt-4o-mini"], "benchmark_names": ["MMLU"]},
            )

        with patch(
            "eval_engine.search.engine.classify_with_llm",
            new=AsyncMock(side_effect=fake_classify),
        ):
            engine = SearchEngine(session)
            r = asyncio.run(engine.classify("do an mmlu eval on gpt please"))
        assert r.intent == SearchIntent.LAUNCH
