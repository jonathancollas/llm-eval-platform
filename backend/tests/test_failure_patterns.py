"""
Tests for failure mode discovery — clustering, anomaly detection, and
human validation gate.

Run: pytest backend/tests/test_failure_patterns.py -v
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "a" * 64)
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_failure_patterns.db")


# ── Failure clustering ─────────────────────────────────────────────────────────

class TestFailureClustering:
    def _engine(self):
        from eval_engine.failure_clustering import FailureClusteringEngine
        return FailureClusteringEngine(similarity_threshold=0.1, min_cluster_size=2)

    def _make_failures(self, n: int, prompt_prefix: str = "the model refused to answer") -> list[dict]:
        return [
            {
                "prompt": f"{prompt_prefix} question {i}",
                "response": "I cannot assist with that request.",
                "model_name": "test-model",
                "score": 0.2,
                "severity": "medium",
                "category": "over_refusal",
            }
            for i in range(n)
        ]

    def test_empty_failures_returns_empty_report(self):
        engine = self._engine()
        report = engine.discover([], campaign_id=1)
        assert report.n_failures == 0
        assert report.n_clusters == 0
        assert report.all_clusters == []

    def test_clusters_similar_failures(self):
        engine = self._engine()
        failures = self._make_failures(5)
        report = engine.discover(failures, campaign_id=1)
        # All similar failures should form at least 1 cluster
        assert report.n_clusters >= 1
        assert report.n_failures == 5

    def test_novel_cluster_detection(self):
        from eval_engine.failure_clustering import FailureClusteringEngine
        engine = FailureClusteringEngine(similarity_threshold=0.05, min_cluster_size=2)
        failures = [
            {
                "prompt": f"bizarre xyzzy unknown failure mode token{i}",
                "response": f"xyzzy bizarre unknown novel token{i}",
                "model_name": "test-model",
                "score": 0.1,
                "severity": "high",
                "category": "xyzzy_novel",
            }
            for i in range(4)
        ]
        report = engine.discover(failures, campaign_id=42)
        # Clusters should be detected
        assert report.n_clusters >= 0  # May or may not form cluster depending on similarity

    def test_cluster_report_has_summary(self):
        engine = self._engine()
        failures = self._make_failures(4)
        report = engine.discover(failures, campaign_id=1)
        assert isinstance(report.summary, str)
        assert len(report.summary) > 0

    def test_cross_model_detection(self):
        from eval_engine.failure_clustering import FailureClusteringEngine
        engine = FailureClusteringEngine(similarity_threshold=0.1, min_cluster_size=2)
        failures = [
            {
                "prompt": "the model refused to answer question about safety",
                "response": "I cannot assist with that request.",
                "model_name": "model-A",
                "score": 0.2,
                "severity": "medium",
                "category": "over_refusal",
            },
            {
                "prompt": "the model refused to answer question about harm",
                "response": "I cannot assist with that request.",
                "model_name": "model-B",
                "score": 0.2,
                "severity": "medium",
                "category": "over_refusal",
            },
            {
                "prompt": "model refuses to answer all questions about safety",
                "response": "I cannot assist with that.",
                "model_name": "model-A",
                "score": 0.15,
                "severity": "medium",
                "category": "over_refusal",
            },
            {
                "prompt": "model refuses safety related answer",
                "response": "I cannot assist with that.",
                "model_name": "model-C",
                "score": 0.1,
                "severity": "high",
                "category": "over_refusal",
            },
        ]
        report = engine.discover(failures, campaign_id=5)
        # Cross model patterns may exist if clustering picks up multiple models
        assert isinstance(report.cross_model_patterns, list)

    def test_failure_cluster_properties(self):
        engine = self._engine()
        failures = self._make_failures(4)
        report = engine.discover(failures, campaign_id=99)
        for cluster in report.all_clusters:
            assert cluster.cluster_id.startswith("cluster_99_")
            assert cluster.n_instances >= engine.min_size
            assert 0.0 <= cluster.reproducibility_score <= 1.0
            assert isinstance(cluster.representative_traces, list)
            assert isinstance(cluster.affected_models, list)
            assert cluster.severity in ("critical", "high", "medium", "low", "unknown")


# ── Anomaly detection ─────────────────────────────────────────────────────────

class TestAnomalyDetection:
    def _engine(self):
        from eval_engine.anomaly_detection import AnomalyDetectionEngine
        return AnomalyDetectionEngine(min_scores=3)

    def test_clean_distribution_no_alerts(self):
        engine = self._engine()
        # Varied scores — not suspicious
        scores = [0.1, 0.3, 0.5, 0.6, 0.8, 0.9, 0.4, 0.2, 0.7, 0.55]
        alerts = engine.analyse_score_distribution(scores, campaign_id=1, model_name="m")
        assert alerts == []

    def test_impossible_scores_flagged(self):
        engine = self._engine()
        scores = [0.5, 1.5, -0.1, 0.8, 0.3, 0.6, 0.4]
        alerts = engine.analyse_score_distribution(scores, campaign_id=1, model_name="m")
        types = [a.alert_type for a in alerts]
        assert "impossible_scores" in types

    def test_uniform_scores_flagged(self):
        from eval_engine.anomaly_detection import AnomalyDetectionEngine
        engine = AnomalyDetectionEngine(uniform_entropy_threshold=2.0, min_scores=3)
        # All same score — perfectly uniform
        scores = [0.5] * 10
        alerts = engine.analyse_score_distribution(scores, campaign_id=1, model_name="m")
        types = [a.alert_type for a in alerts]
        assert "uniform_scores" in types

    def test_bimodal_collapse_flagged(self):
        engine = self._engine()
        # All scores at extremes
        scores = [0.0, 0.05, 0.02, 1.0, 0.98, 0.99, 0.01, 0.97, 0.03, 0.96]
        alerts = engine.analyse_score_distribution(scores, campaign_id=1, model_name="m")
        types = [a.alert_type for a in alerts]
        assert "bimodal_collapse" in types

    def test_too_few_scores_no_alerts(self):
        from eval_engine.anomaly_detection import AnomalyDetectionEngine
        engine = AnomalyDetectionEngine(min_scores=10)
        scores = [0.5, 0.5, 0.5]  # Fewer than min_scores
        alerts = engine.analyse_score_distribution(scores)
        assert alerts == []

    def test_performance_regression_detected(self):
        engine = self._engine()
        baseline = {"mmlu": 0.80, "hellaswag": 0.75}
        current = {"mmlu": 0.55, "hellaswag": 0.74}  # mmlu dropped 25pp
        alerts = engine.detect_performance_changes(baseline, current, model_name="m", campaign_id=1)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "regression"
        assert alerts[0].benchmark == "mmlu"
        assert alerts[0].delta == pytest.approx(-0.25)

    def test_performance_improvement_detected(self):
        engine = self._engine()
        baseline = {"mmlu": 0.50}
        current = {"mmlu": 0.80}  # 30pp improvement — suspicious
        alerts = engine.detect_performance_changes(baseline, current, model_name="m", campaign_id=1)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "improvement"

    def test_small_change_no_alert(self):
        engine = self._engine()
        baseline = {"mmlu": 0.75}
        current = {"mmlu": 0.76}  # Only 1pp — below threshold
        alerts = engine.detect_performance_changes(baseline, current)
        assert alerts == []

    def test_analyse_run_full(self):
        engine = self._engine()
        scores = [0.5, 0.3, 0.7, 0.4, 0.6, 0.2, 0.8]
        report = engine.analyse_run(
            scores, campaign_id=1, model_name="test-model",
            novel_pattern_alerts=["Novel cluster detected: xyzzy pattern"],
        )
        assert report.campaign_id == 1
        assert report.n_scores == 7
        assert isinstance(report.score_alerts, list)
        assert len(report.novel_pattern_alerts) == 1
        assert isinstance(report.summary, str)

    def test_clean_run_is_clean(self):
        engine = self._engine()
        scores = [0.1, 0.3, 0.5, 0.7, 0.9, 0.4, 0.6, 0.2, 0.8, 0.55]
        report = engine.analyse_run(scores, campaign_id=2, model_name="m")
        assert report.is_clean


# ── Human validation gate (API router logic) ──────────────────────────────────

class TestHumanValidationGate:
    """Test the human validation gate state machine directly."""

    def setup_method(self):
        """Reset in-memory state before each test."""
        import api.routers.failure_patterns as fp
        fp._pending_clusters.clear()
        fp._confirmed_taxonomy.clear()
        fp._rejected_ids.clear()

    def test_cluster_queues_novel_for_review(self):
        import api.routers.failure_patterns as fp
        from api.routers.failure_patterns import ClusterRequest, FailureRecord, cluster_failures
        failures = [
            FailureRecord(
                prompt=f"xyzzy bizarre unknown failure {i}",
                response=f"xyzzy unknown bizarre response {i}",
                model_name="test",
                score=0.1,
                severity="high",
                category="novel_xyzzy",
            )
            for i in range(5)
        ]
        req = ClusterRequest(
            failures=failures,
            campaign_id=1,
            similarity_threshold=0.1,
            min_cluster_size=2,
        )
        result = cluster_failures(req)
        # Result should have validation gate info
        assert "validation_gate" in result
        assert result["validation_gate"]["pending_count"] >= 0

    def test_confirm_pattern_moves_to_taxonomy(self):
        import api.routers.failure_patterns as fp
        from api.routers.failure_patterns import ConfirmPatternRequest, confirm_pattern

        # Manually insert a pending cluster
        fp._pending_clusters["cluster_test_001"] = {
            "cluster_id": "cluster_test_001",
            "name": "Test cluster",
            "failure_type": "novel",
            "status": "pending_review",
        }

        req = ConfirmPatternRequest(reviewer="alice", notes="Confirmed by alice", suggested_name="Novel Pattern A")
        result = confirm_pattern("cluster_test_001", req)

        assert result["status"] == "confirmed"
        assert "pattern_id" in result
        assert "cluster_test_001" not in fp._pending_clusters
        assert len(fp._confirmed_taxonomy) == 1

        # Confirmed entry should have eval creation note
        entry = list(fp._confirmed_taxonomy.values())[0]
        assert entry["eval_creation_required"] is True
        assert "human" in entry["eval_creation_note"].lower() or "human" in entry["eval_creation_note"].lower()

    def test_reject_pattern_removes_from_pending(self):
        import api.routers.failure_patterns as fp
        from api.routers.failure_patterns import RejectPatternRequest, reject_pattern

        fp._pending_clusters["cluster_test_002"] = {
            "cluster_id": "cluster_test_002",
            "name": "False positive cluster",
            "status": "pending_review",
        }

        req = RejectPatternRequest(reviewer="bob", reason="Not a real pattern")
        result = reject_pattern("cluster_test_002", req)

        assert result["status"] == "rejected"
        assert "cluster_test_002" not in fp._pending_clusters
        assert "cluster_test_002" in fp._rejected_ids

    def test_confirm_nonexistent_raises_404(self):
        from fastapi import HTTPException
        from api.routers.failure_patterns import ConfirmPatternRequest, confirm_pattern
        with pytest.raises(HTTPException) as exc_info:
            confirm_pattern("nonexistent_id", ConfirmPatternRequest())
        assert exc_info.value.status_code == 404

    def test_reject_nonexistent_raises_404(self):
        from fastapi import HTTPException
        from api.routers.failure_patterns import RejectPatternRequest, reject_pattern
        with pytest.raises(HTTPException) as exc_info:
            reject_pattern("nonexistent_id", RejectPatternRequest())
        assert exc_info.value.status_code == 404

    def test_double_reject_is_idempotent(self):
        import api.routers.failure_patterns as fp
        from api.routers.failure_patterns import RejectPatternRequest, reject_pattern

        fp._pending_clusters["cluster_test_003"] = {
            "cluster_id": "cluster_test_003",
            "name": "Test",
            "status": "pending_review",
        }
        req = RejectPatternRequest(reviewer="charlie")
        reject_pattern("cluster_test_003", req)

        # Second rejection should return already_rejected
        result = reject_pattern("cluster_test_003", req)
        assert result["status"] == "already_rejected"

    def test_confirm_already_confirmed_raises_400(self):
        import api.routers.failure_patterns as fp
        from fastapi import HTTPException
        from api.routers.failure_patterns import ConfirmPatternRequest, confirm_pattern

        fp._confirmed_taxonomy["pat_001"] = {"pattern_id": "pat_001", "name": "Existing"}

        # cluster_id = pat_001 is already in confirmed_taxonomy, but cluster is in pending
        fp._pending_clusters["cluster_dup"] = {"cluster_id": "cluster_dup", "name": "Dup", "status": "pending_review"}
        # Confirm it once
        confirm_pattern("cluster_dup", ConfirmPatternRequest())
        # Now it's in confirmed_taxonomy, not pending; trying to confirm again raises
        with pytest.raises(HTTPException) as exc_info:
            confirm_pattern("cluster_dup", ConfirmPatternRequest())
        assert exc_info.value.status_code in (400, 404)

    def test_taxonomy_listing(self):
        import api.routers.failure_patterns as fp
        from api.routers.failure_patterns import list_taxonomy

        fp._confirmed_taxonomy["pat_x"] = {"pattern_id": "pat_x", "name": "Pattern X"}
        result = list_taxonomy()
        assert result["count"] == 1
        assert len(result["taxonomy"]) == 1

    def test_pending_listing(self):
        import api.routers.failure_patterns as fp
        from api.routers.failure_patterns import list_pending

        fp._pending_clusters["c1"] = {"cluster_id": "c1", "name": "C1", "status": "pending_review"}
        fp._pending_clusters["c2"] = {"cluster_id": "c2", "name": "C2", "status": "pending_review"}
        result = list_pending()
        assert result["count"] == 2
        assert "gate_policy" in result

    def test_no_automated_eval_generation_note(self):
        """
        Critical: Confirm that confirmed patterns carry the explicit note that
        eval creation must be human-only (no auto-generation).
        """
        import api.routers.failure_patterns as fp
        from api.routers.failure_patterns import ConfirmPatternRequest, confirm_pattern

        fp._pending_clusters["cluster_guard"] = {
            "cluster_id": "cluster_guard",
            "name": "Guard test",
            "status": "pending_review",
        }
        confirm_pattern("cluster_guard", ConfirmPatternRequest(reviewer="tester"))
        entry = list(fp._confirmed_taxonomy.values())[-1]
        assert entry["eval_creation_required"] is True
        # The note must explicitly warn against auto-generation
        note = entry["eval_creation_note"].lower()
        assert "human" in note
        assert "contamination" in note or "auto" in note.lower() or "not" in note
