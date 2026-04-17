"""Tests for Plugin SDK (Milestone 2)."""
import json
import pytest

# ── Plugin SDK imports ────────────────────────────────────────────────────────
from eval_engine.plugin_sdk.interfaces import (
    BenchmarkPlugin, PluginManifest, MetricPlugin, MetricResult,
)
from eval_engine.plugin_sdk.registry import PluginRegistry, plugin_benchmark
from eval_engine.plugin_sdk.validator import (
    validate_benchmark_plugin, validate_metric_plugin,
    validate_judge_plugin, validate_environment_plugin,
)

# ── Versioning imports ────────────────────────────────────────────────────────
from eval_engine.eval_versioning import (
    SemanticVersion, hash_content, compute_diff, create_version, diff_versions,
)

# ── Export imports ────────────────────────────────────────────────────────────
from eval_engine.research_export import (
    ExportConfig, export_json_ld, export_csv, export_latex_table,
    export_bibtex, export_eval_card,
)


# ── Concrete stub classes ─────────────────────────────────────────────────────

class ConcreteMetric(MetricPlugin):
    @property
    def metric_name(self): return "accuracy"
    @property
    def description(self): return "Accuracy metric"
    @property
    def range(self): return (0.0, 1.0)
    def compute(self, items): return MetricResult("accuracy", 0.5)
    def compute_with_ci(self, items, n_bootstrap=1000): return MetricResult("accuracy", 0.5)


class ConcreteBenchmark(BenchmarkPlugin):
    @property
    def plugin_manifest(self):
        return PluginManifest(name="test", version="1.0.0", author="a", description="d")
    @property
    def capability_tags(self): return ["reasoning"]
    @property
    def difficulty(self): return "medium"
    @property
    def domain(self): return "nlp"
    async def run(self, model, n_samples=10): return {}


# ══════════════════════════════════════════════════════════════════════════════
# PluginManifest
# ══════════════════════════════════════════════════════════════════════════════

def test_plugin_manifest_instantiation():
    m = PluginManifest(name="test", version="1.0.0", author="Alice", description="A test plugin")
    assert m.name == "test"
    assert m.version == "1.0.0"
    assert m.author == "Alice"
    assert m.license == "MIT"
    assert m.capability_tags == []


# ══════════════════════════════════════════════════════════════════════════════
# PluginRegistry
# ══════════════════════════════════════════════════════════════════════════════

def test_registry_register_and_retrieve():
    # Use a fresh registry instance to avoid cross-test pollution
    registry = PluginRegistry.__new__(PluginRegistry)
    registry._plugins = {}
    registry.register_benchmark(ConcreteBenchmark)
    result = registry.get_benchmark("ConcreteBenchmark")
    assert result is ConcreteBenchmark

def test_registry_list_plugins():
    registry = PluginRegistry.__new__(PluginRegistry)
    registry._plugins = {}
    registry.register_benchmark(ConcreteBenchmark)
    registry.register_metric(ConcreteMetric)
    all_plugins = registry.list_plugins()
    assert len(all_plugins) == 2
    benchmarks = registry.list_plugins("benchmark")
    assert len(benchmarks) == 1
    assert benchmarks[0].plugin_type == "benchmark"

def test_plugin_benchmark_decorator():
    # Fresh isolated registry to avoid singleton state bleed
    registry = PluginRegistry.__new__(PluginRegistry)
    registry._plugins = {}

    @registry.register_benchmark
    class MyBenchmark(ConcreteBenchmark):
        pass

    assert registry.get_benchmark("MyBenchmark") is MyBenchmark


# ══════════════════════════════════════════════════════════════════════════════
# Validator
# ══════════════════════════════════════════════════════════════════════════════

def test_validate_benchmark_plugin_passes():
    result = validate_benchmark_plugin(ConcreteBenchmark)
    assert result.passed is True
    assert result.compliance_score == 1.0
    assert result.errors == []

def test_validate_benchmark_plugin_missing_methods():
    class Incomplete:
        pass
    result = validate_benchmark_plugin(Incomplete)
    assert result.passed is False
    assert result.compliance_score < 1.0

def test_validate_metric_plugin_passes():
    result = validate_metric_plugin(ConcreteMetric)
    assert result.passed is True

def test_validate_judge_plugin_missing():
    class NoJudge:
        pass
    result = validate_judge_plugin(NoJudge)
    assert result.passed is False

def test_validate_environment_plugin_missing():
    class NoEnv:
        pass
    result = validate_environment_plugin(NoEnv)
    assert result.passed is False


# ══════════════════════════════════════════════════════════════════════════════
# SemanticVersion
# ══════════════════════════════════════════════════════════════════════════════

def test_semver_parse_stable():
    v = SemanticVersion.parse("1.2.3")
    assert v.major == 1
    assert v.minor == 2
    assert v.patch == 3
    assert v.pre is None
    assert str(v) == "1.2.3"

def test_semver_parse_prerelease():
    v = SemanticVersion.parse("2.0.0-beta")
    assert v.major == 2
    assert v.minor == 0
    assert v.patch == 0
    assert v.pre == "beta"
    assert str(v) == "2.0.0-beta"

def test_semver_ordering():
    v100 = SemanticVersion.parse("1.0.0")
    v101 = SemanticVersion.parse("1.0.1")
    v110 = SemanticVersion.parse("1.1.0")
    v200 = SemanticVersion.parse("2.0.0")
    assert v100 < v101
    assert v101 < v110
    assert v110 < v200

def test_semver_bump_patch():
    v = SemanticVersion.parse("1.2.3")
    assert str(v.bump_patch()) == "1.2.4"

def test_semver_bump_minor():
    v = SemanticVersion.parse("1.2.3")
    bumped = v.bump_minor()
    assert bumped.minor == 3
    assert bumped.patch == 0

def test_semver_bump_major():
    v = SemanticVersion.parse("1.2.3")
    bumped = v.bump_major()
    assert bumped.major == 2
    assert bumped.minor == 0
    assert bumped.patch == 0


# ══════════════════════════════════════════════════════════════════════════════
# hash_content
# ══════════════════════════════════════════════════════════════════════════════

def test_hash_content_deterministic():
    h1 = hash_content({"a": 1, "b": 2})
    h2 = hash_content({"a": 1, "b": 2})
    assert h1 == h2

def test_hash_content_different_inputs():
    h1 = hash_content({"a": 1})
    h2 = hash_content({"a": 2})
    assert h1 != h2

def test_hash_content_list():
    h1 = hash_content([1, 2, 3])
    h2 = hash_content([1, 2, 3])
    assert h1 == h2
    assert hash_content([1, 2, 3]) != hash_content([1, 2, 4])


# ══════════════════════════════════════════════════════════════════════════════
# compute_diff
# ══════════════════════════════════════════════════════════════════════════════

def test_compute_diff_added():
    v1 = [{"id": "a", "q": "x"}]
    v2 = [{"id": "a", "q": "x"}, {"id": "b", "q": "y"}]
    diff = compute_diff(v1, v2)
    assert "b" in diff.added
    assert diff.removed == []

def test_compute_diff_removed():
    v1 = [{"id": "a", "q": "x"}, {"id": "b", "q": "y"}]
    v2 = [{"id": "a", "q": "x"}]
    diff = compute_diff(v1, v2)
    assert "b" in diff.removed
    assert diff.breaking_change is True

def test_compute_diff_modified():
    v1 = [{"id": "a", "q": "old"}]
    v2 = [{"id": "a", "q": "new"}]
    diff = compute_diff(v1, v2)
    assert "a" in diff.modified


# ══════════════════════════════════════════════════════════════════════════════
# diff_versions
# ══════════════════════════════════════════════════════════════════════════════

def test_diff_versions_dataset_change():
    v1 = create_version("bench", [{"id": "1", "q": "old"}], {}, {}, "1.0.0")
    v2 = create_version("bench", [{"id": "1", "q": "new"}], {}, {}, "1.1.0")
    result = diff_versions(v1, v2)
    assert result["dataset_changed"] is True
    assert result["breaking_change"] is True

def test_diff_versions_no_change():
    items = [{"id": "1", "q": "same"}]
    v1 = create_version("bench", items, {}, {}, "1.0.0")
    v2 = create_version("bench", items, {}, {}, "1.0.1")
    result = diff_versions(v1, v2)
    assert result["dataset_changed"] is False


# ══════════════════════════════════════════════════════════════════════════════
# Research Export
# ══════════════════════════════════════════════════════════════════════════════

_RUN = {"model_name": "gpt-4", "benchmark_name": "MMLU", "score": 0.85,
        "ci_lower": 0.82, "ci_upper": 0.88, "n_items": 100}
_CFG = ExportConfig(author="Alice")


def test_export_json_ld_valid_json_with_context():
    out = export_json_ld(_RUN, _CFG)
    doc = json.loads(out)
    assert "@context" in doc
    assert doc["model"] == "gpt-4"

def test_export_csv_has_model_header():
    out = export_csv([_RUN], _CFG)
    assert "model" in out.splitlines()[0]

def test_export_latex_table_contains_begin_tabular():
    out = export_latex_table([_RUN], _CFG)
    assert r"\begin{tabular}" in out

def test_export_bibtex_contains_at_misc():
    benchmarks = [{"name": "MMLU", "title": "MMLU Benchmark",
                   "authors": "Hendrycks et al.", "year": "2021", "url": "https://example.com"}]
    out = export_bibtex(benchmarks)
    assert "@misc" in out

def test_export_eval_card_contains_results_section():
    out = export_eval_card(_RUN, {"name": "MMLU", "description": "A benchmark"}, _CFG)
    assert "## Results" in out
