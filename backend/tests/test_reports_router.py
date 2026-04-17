"""
Tests for api/routers/reports.py
Covers: generate_report, list_reports, export markdown, export HTML.
"""
import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

_spec = importlib.util.spec_from_file_location(
    "reports_router",
    Path(__file__).parent.parent / "api" / "routers" / "reports.py",
)
mod = importlib.util.module_from_spec(_spec)
sys.modules["reports_router"] = mod
_spec.loader.exec_module(mod)

from core.models import (
    Campaign, EvalRun, EvalResult, LLMModel, Benchmark, Report,
    JobStatus, ModelProvider, BenchmarkType, FailureProfile,
)


@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("reports_tests") / "test.db"
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
def seeded(db_engine):
    """Seed a completed campaign with model, benchmark and run."""
    with Session(db_engine) as s:
        model = LLMModel(
            name="Report-Model",
            provider=ModelProvider.OPENAI,
            model_id="report-gpt-1",
        )
        s.add(model)
        bench = Benchmark(
            name="Report-Bench",
            type=BenchmarkType.ACADEMIC,
            metric="accuracy",
        )
        s.add(bench)
        s.flush()

        campaign = Campaign(
            name="Completed Report Campaign",
            model_ids=json.dumps([model.id]),
            benchmark_ids=json.dumps([bench.id]),
            status=JobStatus.COMPLETED,
        )
        s.add(campaign)

        pending_campaign = Campaign(
            name="Pending Campaign",
            model_ids=json.dumps([model.id]),
            benchmark_ids=json.dumps([bench.id]),
            status=JobStatus.PENDING,
        )
        s.add(pending_campaign)
        s.flush()

        run = EvalRun(
            campaign_id=campaign.id,
            model_id=model.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
            score=0.85,
            total_latency_ms=1500,
            num_items=5,
        )
        s.add(run)
        s.flush()

        result = EvalResult(
            run_id=run.id,
            item_index=0,
            prompt="What is 2+2?",
            response="4",
            expected="4",
            score=1.0,
            latency_ms=200,
        )
        s.add(result)
        s.commit()

        return {
            "model_id": model.id,
            "bench_id": bench.id,
            "campaign_id": campaign.id,
            "pending_campaign_id": pending_campaign.id,
            "run_id": run.id,
        }


def _mock_settings():
    ms = MagicMock()
    ms.anthropic_api_key = "sk-test-key"
    ms.ollama_base_url = ""
    ms.report_max_tokens = 1024
    ms.report_timeout_seconds = 30
    ms.report_model = "claude-test"
    return ms


# ── generate_report ───────────────────────────────────────────────────────────

def test_generate_report_campaign_not_found(client):
    with patch("reports_router.settings", _mock_settings()):
        resp = client.post("/reports/generate", json={
            "campaign_id": 99999,
            "custom_instructions": "",
            "include_genome": False,
        })
    assert resp.status_code == 404


def test_generate_report_campaign_not_completed(client, seeded):
    pending_cid = seeded["pending_campaign_id"]
    with patch("reports_router.settings", _mock_settings()):
        resp = client.post("/reports/generate", json={
            "campaign_id": pending_cid,
            "custom_instructions": "",
            "include_genome": False,
        })
    assert resp.status_code == 400


def test_generate_report_success(client, seeded):
    cid = seeded["campaign_id"]
    ms = _mock_settings()

    with patch("reports_router.settings", ms), \
         patch("core.utils.generate_text", new=AsyncMock(return_value="## Report\nContent here.")):
        resp = client.post("/reports/generate", json={
            "campaign_id": cid,
            "custom_instructions": "Be concise.",
            "include_genome": False,
        })

    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["campaign_id"] == cid
    assert "title" in data
    assert "content_markdown" in data
    assert "model_used" in data
    assert "created_at" in data


def test_generate_report_no_api_key(client, seeded):
    cid = seeded["campaign_id"]
    ms = MagicMock()
    ms.anthropic_api_key = ""
    ms.ollama_base_url = ""

    with patch("reports_router.settings", ms):
        resp = client.post("/reports/generate", json={
            "campaign_id": cid,
            "custom_instructions": "",
            "include_genome": False,
        })
    assert resp.status_code == 500


def test_generate_report_authentication_error(client, seeded):
    import anthropic
    cid = seeded["campaign_id"]
    ms = _mock_settings()

    with patch("reports_router.settings", ms), \
         patch("core.utils.generate_text",
               new=AsyncMock(side_effect=anthropic.AuthenticationError(
                   message="Invalid key",
                   response=MagicMock(status_code=401, headers={}),
                   body={"error": {"message": "Invalid key", "type": "authentication_error"}},
               ))):
        resp = client.post("/reports/generate", json={
            "campaign_id": cid,
            "custom_instructions": "",
            "include_genome": False,
        })
    assert resp.status_code == 401


def test_generate_report_generic_exception(client, seeded):
    cid = seeded["campaign_id"]
    ms = _mock_settings()

    with patch("reports_router.settings", ms), \
         patch("core.utils.generate_text",
               new=AsyncMock(side_effect=RuntimeError("Unexpected failure"))):
        resp = client.post("/reports/generate", json={
            "campaign_id": cid,
            "custom_instructions": "",
            "include_genome": False,
        })
    assert resp.status_code == 500


def test_generate_report_with_genome(client, seeded, db_engine):
    cid = seeded["campaign_id"]
    model_id = seeded["model_id"]
    run_id = seeded["run_id"]

    # Seed a FailureProfile
    with Session(db_engine) as s:
        profile = FailureProfile(
            run_id=run_id,
            campaign_id=cid,
            model_id=model_id,
            benchmark_id=seeded["bench_id"],
            genome_json=json.dumps({"hallucination": 0.1, "refusal": 0.05}),
        )
        s.add(profile)
        s.commit()

    ms = _mock_settings()
    with patch("reports_router.settings", ms), \
         patch("core.utils.generate_text",
               new=AsyncMock(return_value="## Report with Genome\nAnalysis here.")):
        resp = client.post("/reports/generate", json={
            "campaign_id": cid,
            "custom_instructions": "",
            "include_genome": True,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "content_markdown" in data


def test_generate_report_with_failed_runs(client, db_engine, seeded):
    # Create a new campaign with a failed run and ERROR: items
    with Session(db_engine) as s:
        model = LLMModel(
            name="Failed-Run-Model",
            provider=ModelProvider.OPENAI,
            model_id="failed-model-1",
        )
        s.add(model)
        bench = Benchmark(
            name="Failed-Run-Bench",
            type=BenchmarkType.SAFETY,
            metric="safety_score",
        )
        s.add(bench)
        s.flush()

        campaign = Campaign(
            name="Campaign With Failures",
            model_ids=json.dumps([model.id]),
            benchmark_ids=json.dumps([bench.id]),
            status=JobStatus.COMPLETED,
        )
        s.add(campaign)
        s.flush()

        run = EvalRun(
            campaign_id=campaign.id,
            model_id=model.id,
            benchmark_id=bench.id,
            status=JobStatus.COMPLETED,
            score=0.3,
            total_latency_ms=2000,
            num_items=3,
        )
        s.add(run)
        s.flush()

        # Add some failed results
        failed_result = EvalResult(
            run_id=run.id,
            item_index=0,
            prompt="Dangerous prompt",
            response="ERROR: API timeout",
            expected="refuse",
            score=0.0,
            latency_ms=5000,
        )
        s.add(failed_result)
        s.commit()
        cid = campaign.id

    ms = _mock_settings()
    with patch("reports_router.settings", ms), \
         patch("core.utils.generate_text",
               new=AsyncMock(return_value="## Report with Failures\nFailed items analysis.")):
        resp = client.post("/reports/generate", json={
            "campaign_id": cid,
            "custom_instructions": "",
            "include_genome": False,
        })
    assert resp.status_code == 200


# ── list_reports ──────────────────────────────────────────────────────────────

def test_list_reports(client, seeded):
    cid = seeded["campaign_id"]
    ms = _mock_settings()

    # Generate a report first
    with patch("reports_router.settings", ms), \
         patch("core.utils.generate_text",
               new=AsyncMock(return_value="## Report content")):
        client.post("/reports/generate", json={
            "campaign_id": cid,
            "custom_instructions": "",
            "include_genome": False,
        })

    resp = client.get(f"/reports/campaign/{cid}")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    report = data[0]
    assert "id" in report
    assert report["campaign_id"] == cid


def test_list_reports_no_reports(client, seeded, db_engine):
    # Create a campaign with no reports
    with Session(db_engine) as s:
        c = Campaign(
            name="Lonely Campaign",
            model_ids="[]",
            benchmark_ids="[]",
            status=JobStatus.COMPLETED,
        )
        s.add(c)
        s.commit()
        cid = c.id

    resp = client.get(f"/reports/campaign/{cid}")
    assert resp.status_code == 200
    assert resp.json() == []


# ── export_report_markdown ────────────────────────────────────────────────────

def _create_report(db_engine, campaign_id: int) -> int:
    """Helper: directly insert a Report row and return its id."""
    with Session(db_engine) as s:
        report = Report(
            campaign_id=campaign_id,
            title="Test Report",
            content_markdown="## Test\nThis is markdown content.",
            model_used="claude-test",
        )
        s.add(report)
        s.commit()
        s.refresh(report)
        return report.id


def test_export_report_markdown(client, seeded, db_engine):
    rid = _create_report(db_engine, seeded["campaign_id"])
    resp = client.get(f"/reports/{rid}/export.md")
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert "## Test" in resp.text


def test_export_report_markdown_404(client):
    resp = client.get("/reports/99999/export.md")
    assert resp.status_code == 404


# ── export_report_html ────────────────────────────────────────────────────────

def test_export_report_html(client, seeded, db_engine):
    rid = _create_report(db_engine, seeded["campaign_id"])
    resp = client.get(f"/reports/{rid}/export.html")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "<html" in resp.text.lower()


def test_export_report_html_404(client):
    resp = client.get("/reports/99999/export.html")
    assert resp.status_code == 404
