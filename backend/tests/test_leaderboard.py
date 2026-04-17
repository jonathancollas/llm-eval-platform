"""Tests for api/routers/leaderboard.py"""
import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

_spec = importlib.util.spec_from_file_location(
    "leaderboard_router_module",
    Path(__file__).parent.parent / "api" / "routers" / "leaderboard.py",
)
mod = importlib.util.module_from_spec(_spec)
sys.modules["leaderboard_router_module"] = mod
_spec.loader.exec_module(mod)


@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("leaderboard_test") / "test.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine):
    def _get_session():
        with Session(db_engine) as s:
            yield s

    test_app = FastAPI()
    test_app.include_router(mod.router)
    test_app.dependency_overrides[mod.get_session] = _get_session
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def seeded_leaderboard(db_engine):
    """Seed LLMModel, Benchmark, Campaign, EvalRun for leaderboard tests."""
    from core.models import (
        Campaign, EvalRun, LLMModel, Benchmark,
        ModelProvider, BenchmarkType, JobStatus,
    )

    with Session(db_engine) as session:
        model_a = LLMModel(
            name="Model Alpha",
            provider=ModelProvider.OPENAI,
            model_id="openai/model-alpha-lb",
        )
        model_b = LLMModel(
            name="Model Beta",
            provider=ModelProvider.ANTHROPIC,
            model_id="anthropic/model-beta-lb",
        )
        bench = Benchmark(
            name="mmlu",
            type=BenchmarkType.ACADEMIC,
            config_json="{}",
            is_builtin=True,
        )
        session.add(model_a)
        session.add(model_b)
        session.add(bench)
        session.commit()
        session.refresh(model_a)
        session.refresh(model_b)
        session.refresh(bench)

        campaign = Campaign(
            name="LB Campaign",
            description="",
            model_ids=json.dumps([model_a.id, model_b.id]),
            benchmark_ids=json.dumps([bench.id]),
        )
        session.add(campaign)
        session.commit()
        session.refresh(campaign)

        run_a = EvalRun(
            campaign_id=campaign.id,
            model_id=model_a.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
            score=0.75,
            total_cost_usd=0.01,
            total_latency_ms=1000,
        )
        run_b = EvalRun(
            campaign_id=campaign.id,
            model_id=model_b.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
            score=0.85,
            total_cost_usd=0.02,
            total_latency_ms=1200,
        )
        # Pending run (should be excluded)
        from core.models import JobStatus as JS
        run_pending = EvalRun(
            campaign_id=campaign.id,
            model_id=model_a.id,
            benchmark_id=bench.id,
            status=JS.PENDING,
            score=None,
            total_cost_usd=0.0,
            total_latency_ms=0,
        )
        session.add(run_a)
        session.add(run_b)
        session.add(run_pending)
        session.commit()
        return {
            "campaign_id": campaign.id,
            "model_a_id": model_a.id,
            "model_b_id": model_b.id,
            "bench_id": bench.id,
        }


# ── GET /leaderboard/domains ──────────────────────────────────────────────────

def test_list_domains(client):
    resp = client.get("/leaderboard/domains")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    keys = {d["key"] for d in data}
    assert "global" in keys
    assert "academic" in keys
    for d in data:
        assert "key" in d
        assert "label" in d
        assert "description" in d
        assert "icon" in d


# ── GET /leaderboard/{domain} ─────────────────────────────────────────────────

def test_get_leaderboard_invalid_domain(client):
    resp = client.get("/leaderboard/nonexistent_domain")
    assert resp.status_code == 404


def test_get_leaderboard_global_empty(client):
    """Global domain with no runs returns empty rows."""
    resp = client.get("/leaderboard/global")
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "global"
    assert isinstance(data["rows"], list)
    assert isinstance(data["benchmarks"], list)


def test_get_leaderboard_global_with_data(client, seeded_leaderboard):
    resp = client.get("/leaderboard/global")
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "global"
    assert data["total_runs"] >= 2
    rows = data["rows"]
    assert len(rows) >= 2
    # Ranks should be set
    assert rows[0]["rank"] == 1
    assert rows[1]["rank"] == 2
    # Top rank should have higher avg_score
    assert rows[0]["avg_score"] >= rows[1]["avg_score"]
    for row in rows:
        assert "model_name" in row
        assert "model_provider" in row
        assert "scores" in row
        assert "avg_score" in row


def test_get_leaderboard_academic_domain(client, seeded_leaderboard):
    resp = client.get("/leaderboard/academic")
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "academic"


def test_get_leaderboard_frontier_domain(client):
    resp = client.get("/leaderboard/frontier")
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "frontier"


def test_get_leaderboard_all_domains(client):
    for domain_key in ["cyber", "disinfo", "propensity", "french", "code"]:
        resp = client.get(f"/leaderboard/{domain_key}")
        assert resp.status_code == 200, f"Failed for domain {domain_key}"


# ── POST /leaderboard/{domain}/report ────────────────────────────────────────

def test_generate_report_invalid_domain(client):
    resp = client.post("/leaderboard/nonexistent_domain/report")
    assert resp.status_code == 404


def test_generate_report_no_api_key_no_ollama(client, seeded_leaderboard):
    """Should return 500 when no LLM backend is configured."""
    mock_settings = MagicMock()
    mock_settings.anthropic_api_key = None
    mock_settings.ollama_base_url = None
    mock_settings.report_model = "claude-sonnet"

    with patch.object(mod, "settings", mock_settings):
        resp = client.post("/leaderboard/global/report?force_refresh=true")
    assert resp.status_code == 500


def test_generate_report_no_runs(client):
    """Domain with no completed runs returns 400."""
    mock_settings = MagicMock()
    mock_settings.anthropic_api_key = "sk-test"
    mock_settings.ollama_base_url = None
    mock_settings.report_model = "claude-sonnet"

    with patch.object(mod, "settings", mock_settings):
        resp = client.post("/leaderboard/frontier/report?force_refresh=true")
    assert resp.status_code == 400


def test_generate_report_success(client, seeded_leaderboard):
    """Success path with mocked generate_text."""
    mock_settings = MagicMock()
    mock_settings.anthropic_api_key = "sk-test"
    mock_settings.ollama_base_url = None
    mock_settings.report_model = "claude-sonnet"

    # Clear cache
    mod._report_cache.pop("global", None)

    with patch.object(mod, "settings", mock_settings):
        with patch("core.utils.generate_text", new=AsyncMock(return_value="# Analysis\nGreat models.")):
            resp = client.post("/leaderboard/global/report?force_refresh=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "global"
    assert "content_markdown" in data
    assert "generated_at" in data


def test_generate_report_returns_cached(client, seeded_leaderboard):
    """Without force_refresh, returns cached report."""
    from leaderboard_router_module import DomainReport
    from datetime import datetime

    cached = DomainReport(
        domain="global",
        label="Global",
        content_markdown="Cached content",
        generated_at=datetime.utcnow().isoformat(),
        model_used="claude",
    )
    mod._report_cache["global"] = cached

    resp = client.post("/leaderboard/global/report")
    assert resp.status_code == 200
    data = resp.json()
    assert data["content_markdown"] == "Cached content"


# ── GET /leaderboard/{domain}/report ─────────────────────────────────────────

def test_get_cached_report_not_found(client):
    mod._report_cache.pop("frontier", None)
    resp = client.get("/leaderboard/frontier/report")
    assert resp.status_code == 200
    assert resp.json() is None


def test_get_cached_report_exists(client):
    from leaderboard_router_module import DomainReport
    from datetime import datetime

    mod._report_cache["cyber"] = DomainReport(
        domain="cyber",
        label="Cybersecurity",
        content_markdown="Cyber analysis",
        generated_at=datetime.utcnow().isoformat(),
        model_used="claude",
    )
    resp = client.get("/leaderboard/cyber/report")
    assert resp.status_code == 200
    data = resp.json()
    assert data["content_markdown"] == "Cyber analysis"


# ── Internal helpers ──────────────────────────────────────────────────────────

def test_build_leaderboard_empty():
    rows, bench_names = mod._build_leaderboard([], [], [])
    assert rows == []
    assert bench_names == []


def test_build_leaderboard_with_none_score():
    """Model with no valid scores should have avg_score=None."""
    from core.models import EvalRun, LLMModel, Benchmark, ModelProvider, BenchmarkType, JobStatus

    model = LLMModel(id=1, name="M1", provider=ModelProvider.OPENAI, model_id="m1")
    bench = Benchmark(id=1, name="b1", type=BenchmarkType.ACADEMIC, config_json="{}")
    run = EvalRun(
        id=1, campaign_id=1, model_id=1, benchmark_id=1,
        status=JobStatus.COMPLETED, score=None,
        total_cost_usd=0.0, total_latency_ms=0,
    )
    rows, bench_names = mod._build_leaderboard([run], [model], [bench])
    assert len(rows) == 1
    assert rows[0].avg_score is None
