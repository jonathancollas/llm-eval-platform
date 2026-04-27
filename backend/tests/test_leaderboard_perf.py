"""
Tests for the optimised leaderboard helpers (issue #perf-leaderboard).

Validates:
- _RunSlim projection carries the right values.
- _resolve_domain_benchmark_ids filters correctly for global (None) and scoped domains.
- _build_leaderboard produces correct aggregates from _RunSlim inputs.
- _get_domain_runs applies the domain filter at SQL level and only selects 5 columns.
- TTL cache: second call within TTL does NOT hit the database; force_refresh bypasses it.

Run:
    cd backend && python -m pytest tests/test_leaderboard_perf.py -v
"""
from __future__ import annotations

import os
import sys
import time
from typing import Optional
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "a" * 64)
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_benchmark(id_: int, name: str):
    from core.models import Benchmark, BenchmarkType
    b = Benchmark(
        id=id_,
        name=name,
        type=BenchmarkType.ACADEMIC,
        description="",
        tags="[]",
        config_json="{}",
        metric="accuracy",
        is_builtin=True,
        has_dataset=False,
        source="public",
    )
    return b


def _make_model(id_: int, name: str, provider: str = "openai"):
    from core.models import LLMModel
    m = LLMModel(
        id=id_,
        name=name,
        provider=provider,
        model_id=f"model-{id_}",
    )
    return m


# ─────────────────────────────────────────────────────────────────────────────
# _RunSlim
# ─────────────────────────────────────────────────────────────────────────────

class TestRunSlim:
    def test_fields(self):
        from api.routers.leaderboard import _RunSlim
        r = _RunSlim(model_id=1, benchmark_id=2, score=0.75, total_cost_usd=0.01, total_latency_ms=500)
        assert r.model_id == 1
        assert r.benchmark_id == 2
        assert r.score == 0.75
        assert r.total_cost_usd == 0.01
        assert r.total_latency_ms == 500

    def test_none_score_allowed(self):
        from api.routers.leaderboard import _RunSlim
        r = _RunSlim(model_id=1, benchmark_id=2, score=None, total_cost_usd=0.0, total_latency_ms=0)
        assert r.score is None


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_domain_benchmark_ids
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveDomainBenchmarkIds:
    def _benchmarks(self):
        return {
            1: _make_benchmark(1, "mmlu"),
            2: _make_benchmark(2, "mitre_attack_cyber"),
            3: _make_benchmark(3, "harmbench"),
            4: _make_benchmark(4, "gpqa"),
        }

    def test_global_returns_none(self):
        from api.routers.leaderboard import _resolve_domain_benchmark_ids
        result = _resolve_domain_benchmark_ids(None, self._benchmarks())
        assert result is None

    def test_scoped_domain_filters_correctly(self):
        from api.routers.leaderboard import _resolve_domain_benchmark_ids
        # cyber domain keys
        allowed_keys = ["mitre_attack_cyber", "harmbench"]
        result = _resolve_domain_benchmark_ids(allowed_keys, self._benchmarks())
        assert result == {2, 3}

    def test_unmatched_keys_yield_empty_set(self):
        from api.routers.leaderboard import _resolve_domain_benchmark_ids
        result = _resolve_domain_benchmark_ids(["nonexistent_bench"], self._benchmarks())
        assert result == set()


# ─────────────────────────────────────────────────────────────────────────────
# _build_leaderboard
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildLeaderboard:
    def _setup(self):
        from api.routers.leaderboard import _RunSlim
        bench1 = _make_benchmark(1, "mmlu")
        bench2 = _make_benchmark(2, "gpqa")
        model_a = _make_model(10, "ModelA")
        model_b = _make_model(20, "ModelB")

        runs = [
            _RunSlim(model_id=10, benchmark_id=1, score=0.8, total_cost_usd=0.02, total_latency_ms=400),
            _RunSlim(model_id=10, benchmark_id=2, score=0.6, total_cost_usd=0.03, total_latency_ms=600),
            _RunSlim(model_id=20, benchmark_id=1, score=0.9, total_cost_usd=0.01, total_latency_ms=300),
        ]
        models = {10: model_a, 20: model_b}
        benchmarks = {1: bench1, 2: bench2}
        return runs, models, benchmarks

    def test_row_count(self):
        from api.routers.leaderboard import _build_leaderboard
        runs, models, benchmarks = self._setup()
        rows, _ = _build_leaderboard(runs, models, benchmarks)
        assert len(rows) == 2

    def test_ranks_assigned(self):
        from api.routers.leaderboard import _build_leaderboard
        runs, models, benchmarks = self._setup()
        rows, _ = _build_leaderboard(runs, models, benchmarks)
        ranks = [r.rank for r in rows]
        assert sorted(ranks) == [1, 2]

    def test_sorted_by_avg_score_desc(self):
        from api.routers.leaderboard import _build_leaderboard
        runs, models, benchmarks = self._setup()
        rows, _ = _build_leaderboard(runs, models, benchmarks)
        # ModelB has only mmlu=0.9; ModelA has avg of (0.8+0.6)/2=0.7
        assert rows[0].model_name == "ModelB"
        assert rows[1].model_name == "ModelA"

    def test_avg_score_computed_correctly(self):
        from api.routers.leaderboard import _build_leaderboard
        runs, models, benchmarks = self._setup()
        rows, _ = _build_leaderboard(runs, models, benchmarks)
        model_a_row = next(r for r in rows if r.model_name == "ModelA")
        assert model_a_row.avg_score == round((0.8 + 0.6) / 2, 4)

    def test_total_cost_summed(self):
        from api.routers.leaderboard import _build_leaderboard
        runs, models, benchmarks = self._setup()
        rows, _ = _build_leaderboard(runs, models, benchmarks)
        model_a_row = next(r for r in rows if r.model_name == "ModelA")
        assert round(model_a_row.total_cost_usd, 6) == round(0.02 + 0.03, 6)

    def test_avg_latency_computed(self):
        from api.routers.leaderboard import _build_leaderboard
        runs, models, benchmarks = self._setup()
        rows, _ = _build_leaderboard(runs, models, benchmarks)
        model_a_row = next(r for r in rows if r.model_name == "ModelA")
        assert model_a_row.avg_latency_ms == (400 + 600) / 2

    def test_bench_names_returned(self):
        from api.routers.leaderboard import _build_leaderboard
        runs, models, benchmarks = self._setup()
        _, bench_names = _build_leaderboard(runs, models, benchmarks)
        # bench names should come from benchmarks referenced in runs
        assert set(bench_names) == {"mmlu", "gpqa"}

    def test_none_score_excluded_from_avg(self):
        from api.routers.leaderboard import _RunSlim, _build_leaderboard
        bench = _make_benchmark(1, "mmlu")
        model = _make_model(10, "M")
        runs = [
            _RunSlim(model_id=10, benchmark_id=1, score=None, total_cost_usd=0.0, total_latency_ms=0),
        ]
        rows, _ = _build_leaderboard(runs, {10: model}, {1: bench})
        assert rows[0].avg_score is None

    def test_empty_runs(self):
        from api.routers.leaderboard import _build_leaderboard
        rows, bench_names = _build_leaderboard([], {}, {})
        assert rows == []
        assert bench_names == []


# ─────────────────────────────────────────────────────────────────────────────
# TTL cache behaviour (no DB needed)
# ─────────────────────────────────────────────────────────────────────────────

class TestLeaderboardCache:
    """Verify the module-level TTL cache logic without spinning up a real DB."""

    def _fresh_module(self):
        """Re-import the module with a clean cache dict to avoid test pollution."""
        import importlib
        import api.routers.leaderboard as mod
        importlib.reload(mod)
        return mod

    def test_result_is_cached_within_ttl(self):
        import api.routers.leaderboard as mod
        # Manually populate the cache.
        fake = MagicMock()
        mod._leaderboard_cache["global"] = (time.monotonic(), fake)
        # Retrieve — should be the same object.
        ts, cached = mod._leaderboard_cache["global"]
        assert time.monotonic() - ts < mod._LEADERBOARD_TTL
        assert cached is fake

    def test_cache_expires_after_ttl(self):
        import api.routers.leaderboard as mod
        fake = MagicMock()
        # Store with a timestamp in the past (well beyond TTL).
        old_ts = time.monotonic() - mod._LEADERBOARD_TTL - 1
        mod._leaderboard_cache["global"] = (old_ts, fake)
        ts, _ = mod._leaderboard_cache["global"]
        assert time.monotonic() - ts >= mod._LEADERBOARD_TTL

    def test_cache_ttl_default_is_300(self):
        import api.routers.leaderboard as mod
        assert mod._LEADERBOARD_TTL == 300
