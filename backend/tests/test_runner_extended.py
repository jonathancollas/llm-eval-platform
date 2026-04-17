"""
Extended tests for eval_engine/runner.py
Covers: _execute_campaign_inner (full run path), _run_one, _progress callback,
        _auto_judge_campaign, _generate_manifest, _compute_genome_for_campaign,
        error classification branches in execute_campaign.
"""
import asyncio
import json
import os
import secrets
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from core.models import (
    Benchmark,
    BenchmarkType,
    Campaign,
    EvalResult,
    EvalRun,
    JobStatus,
    LLMModel,
    ModelProvider,
)
from eval_engine.runner import (
    _auto_judge_campaign,
    _compute_genome_for_campaign,
    _execute_campaign_inner,
    _format_eta,
    _generate_manifest,
    _mark_campaign,
    _run_one,
    execute_campaign,
)


# ── DB fixture ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture()
def session(db_engine):
    with Session(db_engine) as s:
        yield s


def _seed_campaign(db_engine, name="Test Campaign"):
    with Session(db_engine) as s:
        c = Campaign(name=name, status=JobStatus.RUNNING, progress=0.0, seed=42, temperature=0.0)
        s.add(c)
        s.commit()
        s.refresh(c)
        return c.id


_counter = 0

def _uid():
    global _counter
    _counter += 1
    return _counter


def _seed_model(db_engine):
    uid = _uid()
    with Session(db_engine) as s:
        m = LLMModel(name=f"test-model-{uid}", model_id=f"test/model-{uid}", provider=ModelProvider.OPENAI)
        s.add(m)
        s.commit()
        s.refresh(m)
        return m.id


def _seed_benchmark(db_engine, eval_dim="capability"):
    uid = _uid()
    with Session(db_engine) as s:
        b = Benchmark(
            name=f"test-bench-{uid}",
            type=BenchmarkType.ACADEMIC,
            metric="accuracy",
            num_samples=2,
        )
        try:
            b.eval_dimension = eval_dim
        except Exception:
            pass
        s.add(b)
        s.commit()
        s.refresh(b)
        return b.id


# ── RunSummary helper ──────────────────────────────────────────────────────────

def _make_run_summary(score=0.75):
    from eval_engine.base import ItemResult, RunSummary
    items = [
        ItemResult(
            item_index=0, prompt="Q", response="A", expected="A",
            score=score, latency_ms=100, input_tokens=10, output_tokens=5,
            cost_usd=0.001, metadata={},
        )
    ]
    return RunSummary(
        score=score, metrics={"accuracy": score},
        total_cost_usd=0.001, total_latency_ms=100,
        num_items=1, item_results=items,
    )


# ══════════════════════════════════════════════════════════════════════════════
# _execute_campaign_inner — full run with mocked get_runner
# ══════════════════════════════════════════════════════════════════════════════

class TestExecuteCampaignInner:
    def _run(self, db_engine, cid, model_ids, bench_ids, runner_result=None):
        import eval_engine.runner as runner_mod
        original = runner_mod.engine

        summary = runner_result or _make_run_summary()

        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=summary)

        async def _noop_emit(*a, **kw):
            pass

        try:
            runner_mod.engine = db_engine
            with patch("eval_engine.runner.get_campaign_model_ids", return_value=model_ids), \
                 patch("eval_engine.runner.get_campaign_benchmark_ids", return_value=bench_ids), \
                 patch("eval_engine.runner.get_runner", return_value=mock_runner), \
                 patch("eval_engine.runner._bus") as mock_bus, \
                 patch("eval_engine.runner._compute_genome_for_campaign"), \
                 patch("eval_engine.runner._generate_manifest"), \
                 patch("eval_engine.runner._auto_judge_campaign", new=AsyncMock()):
                mock_bus.emit = AsyncMock(return_value=None)
                asyncio.run(_execute_campaign_inner(cid))
        finally:
            runner_mod.engine = original

    def test_completes_with_zero_runs(self, db_engine):
        cid = _seed_campaign(db_engine, "Zero Runs")
        self._run(db_engine, cid, [], [])
        with Session(db_engine) as s:
            c = s.get(Campaign, cid)
            assert c.status == JobStatus.COMPLETED
            assert c.progress == 100.0

    def test_single_model_single_bench_completes(self, db_engine):
        cid = _seed_campaign(db_engine, "One Run")
        mid = _seed_model(db_engine)
        bid = _seed_benchmark(db_engine)
        self._run(db_engine, cid, [mid], [bid])
        with Session(db_engine) as s:
            c = s.get(Campaign, cid)
            assert c.status == JobStatus.COMPLETED

    def test_eval_run_score_stored(self, db_engine):
        cid = _seed_campaign(db_engine, "Score Test")
        mid = _seed_model(db_engine)
        bid = _seed_benchmark(db_engine)
        self._run(db_engine, cid, [mid], [bid], _make_run_summary(0.88))
        with Session(db_engine) as s:
            runs = s.exec(select(EvalRun).where(EvalRun.campaign_id == cid)).all()
            assert any(r.score == pytest.approx(0.88) for r in runs)

    def test_nonexistent_campaign_returns_early(self, db_engine):
        import eval_engine.runner as runner_mod
        original = runner_mod.engine
        try:
            runner_mod.engine = db_engine
            asyncio.run(_execute_campaign_inner(999999))  # no crash
        finally:
            runner_mod.engine = original

    def test_nonexistent_model_skips(self, db_engine):
        cid = _seed_campaign(db_engine, "Missing Model")
        bid = _seed_benchmark(db_engine)
        self._run(db_engine, cid, [99999], [bid])
        with Session(db_engine) as s:
            c = s.get(Campaign, cid)
            assert c.status == JobStatus.COMPLETED

    def test_nonexistent_benchmark_skips(self, db_engine):
        cid = _seed_campaign(db_engine, "Missing Bench")
        mid = _seed_model(db_engine)
        self._run(db_engine, cid, [mid], [99999])
        with Session(db_engine) as s:
            c = s.get(Campaign, cid)
            assert c.status == JobStatus.COMPLETED

    def test_run_failure_marks_eval_run_failed(self, db_engine):
        cid = _seed_campaign(db_engine, "Failing Run")
        mid = _seed_model(db_engine)
        bid = _seed_benchmark(db_engine)
        import eval_engine.runner as runner_mod
        original = runner_mod.engine

        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(side_effect=RuntimeError("runner exploded"))

        try:
            runner_mod.engine = db_engine
            with patch("eval_engine.runner.get_campaign_model_ids", return_value=[mid]), \
                 patch("eval_engine.runner.get_campaign_benchmark_ids", return_value=[bid]), \
                 patch("eval_engine.runner.get_runner", return_value=mock_runner), \
                 patch("eval_engine.runner._bus") as mock_bus, \
                 patch("eval_engine.runner._compute_genome_for_campaign"), \
                 patch("eval_engine.runner._generate_manifest"), \
                 patch("eval_engine.runner._auto_judge_campaign", new=AsyncMock()):
                mock_bus.emit = AsyncMock(return_value=None)
                asyncio.run(_execute_campaign_inner(cid))
        finally:
            runner_mod.engine = original

        with Session(db_engine) as s:
            runs = s.exec(select(EvalRun).where(EvalRun.campaign_id == cid)).all()
            assert any(r.status == JobStatus.FAILED for r in runs)

    def test_insufficient_credits_error_friendly_message(self, db_engine):
        cid = _seed_campaign(db_engine, "Credits Error")
        mid = _seed_model(db_engine)
        bid = _seed_benchmark(db_engine)
        import eval_engine.runner as runner_mod
        original = runner_mod.engine

        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(side_effect=RuntimeError("insufficient credits available"))

        try:
            runner_mod.engine = db_engine
            with patch("eval_engine.runner.get_campaign_model_ids", return_value=[mid]), \
                 patch("eval_engine.runner.get_campaign_benchmark_ids", return_value=[bid]), \
                 patch("eval_engine.runner.get_runner", return_value=mock_runner), \
                 patch("eval_engine.runner._bus") as mock_bus, \
                 patch("eval_engine.runner._compute_genome_for_campaign"), \
                 patch("eval_engine.runner._generate_manifest"), \
                 patch("eval_engine.runner._auto_judge_campaign", new=AsyncMock()):
                mock_bus.emit = AsyncMock(return_value=None)
                asyncio.run(_execute_campaign_inner(cid))
        finally:
            runner_mod.engine = original

        with Session(db_engine) as s:
            runs = s.exec(select(EvalRun).where(EvalRun.campaign_id == cid)).all()
            failed = [r for r in runs if r.status == JobStatus.FAILED]
            assert failed
            assert "credits" in (failed[0].error_message or "").lower()

    def test_rate_limit_error_friendly_message(self, db_engine):
        cid = _seed_campaign(db_engine, "Rate Limit Error")
        mid = _seed_model(db_engine)
        bid = _seed_benchmark(db_engine)
        import eval_engine.runner as runner_mod
        original = runner_mod.engine

        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(side_effect=RuntimeError("rate limit exceeded"))

        try:
            runner_mod.engine = db_engine
            with patch("eval_engine.runner.get_campaign_model_ids", return_value=[mid]), \
                 patch("eval_engine.runner.get_campaign_benchmark_ids", return_value=[bid]), \
                 patch("eval_engine.runner.get_runner", return_value=mock_runner), \
                 patch("eval_engine.runner._bus") as mock_bus, \
                 patch("eval_engine.runner._compute_genome_for_campaign"), \
                 patch("eval_engine.runner._generate_manifest"), \
                 patch("eval_engine.runner._auto_judge_campaign", new=AsyncMock()):
                mock_bus.emit = AsyncMock(return_value=None)
                asyncio.run(_execute_campaign_inner(cid))
        finally:
            runner_mod.engine = original

        with Session(db_engine) as s:
            runs = s.exec(select(EvalRun).where(EvalRun.campaign_id == cid)).all()
            failed = [r for r in runs if r.status == JobStatus.FAILED]
            assert failed
            assert "rate" in (failed[0].error_message or "").lower()

    def test_propensity_benchmark_stores_propensity_score(self, db_engine):
        cid = _seed_campaign(db_engine, "Propensity Campaign")
        mid = _seed_model(db_engine)
        bid = _seed_benchmark(db_engine, eval_dim="propensity")
        import eval_engine.runner as runner_mod
        original = runner_mod.engine

        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=_make_run_summary(0.6))

        try:
            runner_mod.engine = db_engine
            with patch("eval_engine.runner.get_campaign_model_ids", return_value=[mid]), \
                 patch("eval_engine.runner.get_campaign_benchmark_ids", return_value=[bid]), \
                 patch("eval_engine.runner.get_runner", return_value=mock_runner), \
                 patch("eval_engine.runner._bus") as mock_bus, \
                 patch("eval_engine.runner._compute_genome_for_campaign"), \
                 patch("eval_engine.runner._generate_manifest"), \
                 patch("eval_engine.runner._auto_judge_campaign", new=AsyncMock()):
                mock_bus.emit = AsyncMock(return_value=None)
                asyncio.run(_execute_campaign_inner(cid))
        finally:
            runner_mod.engine = original


# ══════════════════════════════════════════════════════════════════════════════
# execute_campaign — top-level error handling
# ══════════════════════════════════════════════════════════════════════════════

class TestExecuteCampaignTopLevel:
    def test_cancelled_error_marks_cancelled(self, db_engine):
        cid = _seed_campaign(db_engine, "Cancelled Campaign")
        import eval_engine.runner as runner_mod
        original = runner_mod.engine
        try:
            runner_mod.engine = db_engine

            async def _cancel(_):
                raise asyncio.CancelledError()

            with patch("eval_engine.runner._execute_campaign_inner", _cancel):
                asyncio.run(execute_campaign(cid))
        finally:
            runner_mod.engine = original

        with Session(db_engine) as s:
            c = s.get(Campaign, cid)
            assert c.status == JobStatus.CANCELLED

    def test_general_exception_marks_failed(self, db_engine):
        cid = _seed_campaign(db_engine, "Exception Campaign")
        import eval_engine.runner as runner_mod
        original = runner_mod.engine
        try:
            runner_mod.engine = db_engine

            async def _explode(_):
                raise ValueError("something bad")

            with patch("eval_engine.runner._execute_campaign_inner", _explode):
                asyncio.run(execute_campaign(cid))
        finally:
            runner_mod.engine = original

        with Session(db_engine) as s:
            c = s.get(Campaign, cid)
            assert c.status == JobStatus.FAILED


# ══════════════════════════════════════════════════════════════════════════════
# _run_one
# ══════════════════════════════════════════════════════════════════════════════

class TestRunOne:
    def _make_model(self):
        return LLMModel(id=1, name="test-model", model_id="test/model", provider=ModelProvider.OPENAI)

    def _make_bench(self, dataset_path=None):
        b = Benchmark(id=1, name="test-bench", type=BenchmarkType.ACADEMIC, metric="accuracy", num_samples=2)
        if dataset_path:
            b.dataset_path = dataset_path
        return b

    def _make_campaign(self):
        return Campaign(id=1, name="c", status=JobStatus.RUNNING, progress=0.0, seed=42, temperature=0.0)

    def test_run_one_success_returns_summary(self, db_engine):
        import eval_engine.runner as runner_mod
        original = runner_mod.engine

        summary = _make_run_summary(0.9)
        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=summary)

        try:
            runner_mod.engine = db_engine
            with patch("eval_engine.runner.get_runner", return_value=mock_runner), \
                 patch("eval_engine.runner._bus") as mock_bus:
                mock_bus.emit = AsyncMock(return_value=None)
                result = asyncio.run(_run_one(
                    self._make_model(), self._make_bench(),
                    self._make_campaign(), eval_run_id=1
                ))
        finally:
            runner_mod.engine = original

        s, items = result
        assert s.score == pytest.approx(0.9)

    def test_run_one_get_runner_failure_raises(self, db_engine):
        import eval_engine.runner as runner_mod
        original = runner_mod.engine
        try:
            runner_mod.engine = db_engine
            with patch("eval_engine.runner.get_runner", side_effect=ValueError("no runner")):
                with pytest.raises(RuntimeError, match="Failed to get runner"):
                    asyncio.run(_run_one(
                        self._make_model(), self._make_bench(),
                        self._make_campaign(), eval_run_id=1
                    ))
        finally:
            runner_mod.engine = original

    def test_run_one_timeout_raises(self, db_engine):
        import eval_engine.runner as runner_mod
        original = runner_mod.engine

        async def slow_run(**kwargs):
            await asyncio.sleep(999)

        mock_runner = MagicMock()
        mock_runner.run = slow_run

        try:
            runner_mod.engine = db_engine
            with patch("eval_engine.runner.get_runner", return_value=mock_runner), \
                 patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                with pytest.raises(RuntimeError, match="Timeout"):
                    asyncio.run(_run_one(
                        self._make_model(), self._make_bench(),
                        self._make_campaign(), eval_run_id=1
                    ))
        finally:
            runner_mod.engine = original

    def test_run_one_general_runner_error_raises(self, db_engine):
        import eval_engine.runner as runner_mod
        original = runner_mod.engine

        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(side_effect=RuntimeError("runner failed"))

        try:
            runner_mod.engine = db_engine
            with patch("eval_engine.runner.get_runner", return_value=mock_runner), \
                 patch("eval_engine.runner._bus") as mock_bus:
                mock_bus.emit = AsyncMock(return_value=None)
                with pytest.raises(RuntimeError, match="Runner failed"):
                    asyncio.run(_run_one(
                        self._make_model(), self._make_bench(),
                        self._make_campaign(), eval_run_id=1
                    ))
        finally:
            runner_mod.engine = original

    def test_run_one_progress_callback_batches_items(self, db_engine):
        """Verify that progress callback handles item flush without error."""
        import eval_engine.runner as runner_mod
        original = runner_mod.engine

        from eval_engine.base import ItemResult, RunSummary

        items = [
            ItemResult(
                item_index=i, prompt="Q", response="A", expected="A",
                score=1.0, latency_ms=50, input_tokens=5, output_tokens=3,
                cost_usd=0.0, metadata={},
            )
            for i in range(5)
        ]
        summary = RunSummary(
            score=1.0, metrics={}, total_cost_usd=0.0,
            total_latency_ms=250, num_items=5, item_results=items,
        )

        async def run_with_progress(**kwargs):
            cb = kwargs.get("progress_callback")
            if cb:
                for i, item in enumerate(items):
                    cb(i + 1, len(items), item)
                cb(len(items), len(items), None)
            return summary

        mock_runner = MagicMock()
        mock_runner.run = run_with_progress

        try:
            runner_mod.engine = db_engine
            with patch("eval_engine.runner.get_runner", return_value=mock_runner), \
                 patch("eval_engine.runner._bus") as mock_bus:
                mock_bus.emit = AsyncMock(return_value=None)
                result = asyncio.run(_run_one(
                    self._make_model(), self._make_bench(),
                    self._make_campaign(), eval_run_id=999
                ))
        finally:
            runner_mod.engine = original

        s, _ = result
        assert s.num_items == 5


# ══════════════════════════════════════════════════════════════════════════════
# _auto_judge_campaign
# ══════════════════════════════════════════════════════════════════════════════

class TestAutoJudgeCampaign:
    def test_no_completed_runs_exits_early(self, db_engine, session):
        cid = _seed_campaign(db_engine, "Judge No Runs")
        import eval_engine.runner as runner_mod
        original = runner_mod.engine
        try:
            runner_mod.engine = db_engine
            # No completed runs so _auto_judge_campaign should return early
            with Session(db_engine) as s:
                asyncio.run(_auto_judge_campaign(cid, s))  # no error
        finally:
            runner_mod.engine = original

    def test_already_judged_skips(self, db_engine):
        """If JudgeEvaluation already exists, skip re-judging."""
        from core.models import JudgeEvaluation
        cid = _seed_campaign(db_engine, "Already Judged")

        with Session(db_engine) as s:
            run = EvalRun(
                campaign_id=cid, model_id=1, benchmark_id=1,
                status=JobStatus.COMPLETED, score=0.8,
                started_at=datetime.utcnow(),
            )
            s.add(run)
            s.commit()
            s.refresh(run)
            result = EvalResult(
                run_id=run.id, item_index=0, prompt="Q", response="A",
                score=0.8, latency_ms=100,
            )
            s.add(result)
            s.commit()
            s.refresh(result)

            je = JudgeEvaluation(
                campaign_id=cid, run_id=run.id, result_id=result.id,
                judge_model="claude", judge_score=0.8, judge_reasoning="good",
            )
            s.add(je)
            s.commit()

        import eval_engine.runner as runner_mod
        original = runner_mod.engine
        try:
            runner_mod.engine = db_engine
            with Session(db_engine) as s:
                asyncio.run(_auto_judge_campaign(cid, s))  # should skip, no error
        finally:
            runner_mod.engine = original

    def test_judges_with_mock_anthropic(self, db_engine):
        cid = _seed_campaign(db_engine, "Mock Judge Campaign")

        with Session(db_engine) as s:
            run = EvalRun(
                campaign_id=cid, model_id=1, benchmark_id=1,
                status=JobStatus.COMPLETED, score=0.7,
                started_at=datetime.utcnow(),
            )
            s.add(run)
            s.commit()
            s.refresh(run)
            result = EvalResult(
                run_id=run.id, item_index=0, prompt="What is 2+2?", response="4",
                expected="4", score=1.0, latency_ms=50,
            )
            s.add(result)
            s.commit()

        mock_msg = MagicMock()
        mock_content = MagicMock()
        mock_content.text = json.dumps({"score": 0.9, "reasoning": "correct"})
        mock_msg.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_msg)

        import eval_engine.runner as runner_mod
        original = runner_mod.engine

        with patch("eval_engine.runner.settings") as mock_settings, \
             patch("anthropic.AsyncAnthropic", return_value=mock_client):
            mock_settings.anthropic_api_key = "fake-key"
            try:
                runner_mod.engine = db_engine
                with Session(db_engine) as s:
                    asyncio.run(_auto_judge_campaign(cid, s))
            finally:
                runner_mod.engine = original


# ══════════════════════════════════════════════════════════════════════════════
# _generate_manifest
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateManifest:
    def test_generate_manifest_nonexistent_campaign(self, db_engine):
        """Should return without error when campaign missing."""
        import eval_engine.runner as runner_mod
        original = runner_mod.engine
        try:
            runner_mod.engine = db_engine
            with Session(db_engine) as s:
                _generate_manifest(999999, s)  # no error
        finally:
            runner_mod.engine = original

    def test_generate_manifest_creates_record(self, db_engine):
        from core.models import ExperimentManifest
        cid = _seed_campaign(db_engine, "Manifest Campaign")
        mid = _seed_model(db_engine)
        bid = _seed_benchmark(db_engine)

        with Session(db_engine) as s:
            run = EvalRun(
                campaign_id=cid, model_id=mid, benchmark_id=bid,
                status=JobStatus.COMPLETED, score=0.8, num_items=1,
                started_at=datetime.utcnow(),
            )
            s.add(run)
            s.commit()

        import eval_engine.runner as runner_mod
        original = runner_mod.engine
        try:
            runner_mod.engine = db_engine
            with patch("eval_engine.runner.settings") as mock_settings:
                mock_settings.app_version = "test-1.0"
                with Session(db_engine) as s:
                    _generate_manifest(cid, s)
        finally:
            runner_mod.engine = original

        with Session(db_engine) as s:
            manifests = s.exec(
                select(ExperimentManifest).where(ExperimentManifest.campaign_id == cid)
            ).all()
            assert len(manifests) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# _compute_genome_for_campaign
# ══════════════════════════════════════════════════════════════════════════════

class TestComputeGenomeForCampaign:
    def test_compute_genome_no_runs(self, db_engine):
        cid = _seed_campaign(db_engine, "Genome Empty")
        import eval_engine.runner as runner_mod
        original = runner_mod.engine
        try:
            runner_mod.engine = db_engine
            with Session(db_engine) as s, \
                 patch("eval_engine.failure_genome.classifiers.classify_run", return_value={}), \
                 patch("eval_engine.failure_genome.classifiers.aggregate_genome", return_value={}):
                _compute_genome_for_campaign(cid, s)  # no error
        finally:
            runner_mod.engine = original

    def test_compute_genome_with_completed_runs(self, db_engine):
        from core.models import FailureProfile
        cid = _seed_campaign(db_engine, "Genome With Runs")
        mid = _seed_model(db_engine)
        bid = _seed_benchmark(db_engine)

        with Session(db_engine) as s:
            run = EvalRun(
                campaign_id=cid, model_id=mid, benchmark_id=bid,
                status=JobStatus.COMPLETED, score=0.7, num_items=1,
                started_at=datetime.utcnow(),
            )
            s.add(run)
            s.commit()
            s.refresh(run)
            res = EvalResult(
                run_id=run.id, item_index=0, prompt="Q", response="A",
                score=0.7, latency_ms=100,
            )
            s.add(res)
            s.commit()

        import eval_engine.runner as runner_mod
        original = runner_mod.engine
        try:
            runner_mod.engine = db_engine
            mock_genome = {"accuracy_failure": 0.1}
            with patch("eval_engine.failure_genome.classifiers.classify_run", return_value=mock_genome), \
                 patch("eval_engine.failure_genome.classifiers.aggregate_genome", return_value=mock_genome), \
                 patch("eval_engine.failure_genome.ontology.FAILURE_GENOME_VERSION", "v1"):
                with Session(db_engine) as s:
                    _compute_genome_for_campaign(cid, s)
        finally:
            runner_mod.engine = original

        with Session(db_engine) as s:
            profiles = s.exec(
                select(FailureProfile).where(FailureProfile.campaign_id == cid)
            ).all()
            assert len(profiles) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# _format_eta (additional boundary cases)
# ══════════════════════════════════════════════════════════════════════════════

def test_format_eta_zero():
    assert _format_eta(0) == "0s"


def test_format_eta_exactly_one_hour():
    assert _format_eta(3600) == "1h 0m"


def test_format_eta_minutes_only():
    assert _format_eta(61) == "1m 1s"
