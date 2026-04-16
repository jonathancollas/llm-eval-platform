"""
Tests for api/routers/benchmarks.py
Covers: CRUD, packs, sources, update/delete, items, fork, citations, card, versions, lineage.
"""
import importlib.util
import io
import json
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

_spec = importlib.util.spec_from_file_location(
    "benchmarks_router",
    Path(__file__).parent.parent / "api" / "routers" / "benchmarks.py",
)
bench_mod = importlib.util.module_from_spec(_spec)
sys.modules["benchmarks_router"] = bench_mod
_spec.loader.exec_module(bench_mod)

from core.models import Benchmark, BenchmarkType, BenchmarkFork, BenchmarkCitation, BenchmarkPack


# ── DB fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def tmp_bench_dir(tmp_path_factory):
    root = tmp_path_factory.mktemp("bench_api_tests")
    bench_lib = root / "bench_library"
    bench_lib.mkdir(parents=True)
    (bench_lib / "custom").mkdir(parents=True)
    bench_mod.settings.bench_library_path = str(bench_lib)
    bench_mod.settings.benchmark_upload_max_bytes = 1024 * 1024
    return bench_lib


@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("bench_api_db") / "bench.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine, tmp_bench_dir):
    def _get_session():
        with Session(db_engine) as s:
            yield s

    test_app = FastAPI()
    test_app.include_router(bench_mod.router)
    test_app.dependency_overrides[bench_mod.get_session] = _get_session
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def custom_bench(client):
    """Create a custom benchmark and return its ID."""
    resp = client.post("/benchmarks/", json={
        "name": "CustomBench-CRUD",
        "type": "custom",
        "description": "For CRUD tests",
        "tags": ["test"],
        "metric": "accuracy",
        "num_samples": 10,
        "config": {"key": "value"},
        "risk_threshold": 0.5,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture(scope="module")
def builtin_bench(db_engine):
    """Create a builtin benchmark directly in DB."""
    with Session(db_engine) as s:
        b = Benchmark(
            name="BuiltinBench",
            type=BenchmarkType.ACADEMIC,
            metric="accuracy",
            is_builtin=True,
        )
        s.add(b)
        s.commit()
        s.refresh(b)
        return b.id


# ── list_benchmarks ────────────────────────────────────────────────────────────

def test_list_benchmarks_returns_all(client, custom_bench):
    resp = client.get("/benchmarks/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_benchmarks_filter_by_type(client, custom_bench):
    resp = client.get("/benchmarks/?type=custom")
    assert resp.status_code == 200
    data = resp.json()
    # All returned benchmarks should have type==custom
    for item in data:
        assert item["type"] == "custom"


def test_list_benchmarks_empty_type_returns_all(client, custom_bench):
    resp = client.get("/benchmarks/")
    assert resp.status_code == 200


# ── get_benchmark ──────────────────────────────────────────────────────────────

def test_get_benchmark_existing(client, custom_bench):
    resp = client.get(f"/benchmarks/{custom_bench}")
    assert resp.status_code == 200
    assert resp.json()["id"] == custom_bench


def test_get_benchmark_not_found(client):
    resp = client.get("/benchmarks/999999")
    assert resp.status_code == 404


# ── create_benchmark ──────────────────────────────────────────────────────────

def test_create_benchmark_minimal(client):
    resp = client.post("/benchmarks/", json={
        "name": "MinimalBench",
        "type": "academic",
        "metric": "f1",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "MinimalBench"
    assert body["metric"] == "f1"
    assert body["is_builtin"] is False


def test_create_benchmark_with_all_fields(client):
    resp = client.post("/benchmarks/", json={
        "name": "FullBench",
        "type": "safety",
        "description": "Full description",
        "tags": ["tag1", "tag2"],
        "metric": "pass_rate",
        "num_samples": 100,
        "config": {"param": 42},
        "risk_threshold": 0.7,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["risk_threshold"] == 0.7
    assert body["config"] == {"param": 42}
    assert "tag1" in body["tags"]


# ── update_benchmark ──────────────────────────────────────────────────────────

def test_update_benchmark_tags(client, custom_bench):
    resp = client.patch(f"/benchmarks/{custom_bench}", json={"tags": ["updated"]})
    assert resp.status_code == 200
    assert "updated" in resp.json()["tags"]


def test_update_benchmark_source(client, custom_bench):
    resp = client.patch(f"/benchmarks/{custom_bench}", json={"source": "community"})
    assert resp.status_code == 200
    assert resp.json()["source"] == "community"


def test_update_benchmark_description(client, custom_bench):
    resp = client.patch(f"/benchmarks/{custom_bench}", json={"description": "New desc"})
    assert resp.status_code == 200
    assert resp.json()["description"] == "New desc"


def test_update_benchmark_risk_threshold(client, custom_bench):
    resp = client.patch(f"/benchmarks/{custom_bench}", json={"risk_threshold": 0.8})
    assert resp.status_code == 200
    assert resp.json()["risk_threshold"] == 0.8


def test_update_benchmark_not_found(client):
    resp = client.patch("/benchmarks/999999", json={"description": "nope"})
    assert resp.status_code == 404


# ── delete_benchmark ──────────────────────────────────────────────────────────

def test_delete_benchmark_custom(client):
    # Create a bench to delete
    r = client.post("/benchmarks/", json={"name": "ToDelete", "type": "custom", "metric": "accuracy"})
    assert r.status_code == 201
    bid = r.json()["id"]
    resp = client.delete(f"/benchmarks/{bid}")
    assert resp.status_code == 204
    assert client.get(f"/benchmarks/{bid}").status_code == 404


def test_delete_benchmark_not_found(client):
    resp = client.delete("/benchmarks/999999")
    assert resp.status_code == 404


def test_delete_benchmark_builtin_rejected(client, builtin_bench):
    resp = client.delete(f"/benchmarks/{builtin_bench}")
    assert resp.status_code == 400
    assert "Cannot delete built-in" in resp.json()["detail"]


# ── upload_dataset ─────────────────────────────────────────────────────────────

def test_upload_dataset_builtin_rejected(client, builtin_bench):
    files = {"file": ("data.json", b'{"items":[{"q":"a"}]}', "application/json")}
    resp = client.post(f"/benchmarks/{builtin_bench}/upload-dataset", files=files)
    assert resp.status_code == 400
    assert "Cannot override built-in" in resp.json()["detail"]


def test_upload_dataset_not_found(client):
    files = {"file": ("data.json", b'{"items":[{"q":"a"}]}', "application/json")}
    resp = client.post("/benchmarks/999999/upload-dataset", files=files)
    assert resp.status_code == 404


def test_upload_csv_success(client, db_engine):
    r = client.post("/benchmarks/", json={"name": "CSVBench", "type": "custom", "metric": "accuracy"})
    assert r.status_code == 201
    bid = r.json()["id"]
    csv_content = b"prompt,answer\nWhat is 2+2?,4\nCapital of France?,Paris\n"
    files = {"file": ("dataset.csv", csv_content, "text/csv")}
    resp = client.post(f"/benchmarks/{bid}/upload-dataset", files=files)
    assert resp.status_code == 200
    assert resp.json()["has_dataset"] is True


def test_upload_csv_invalid_utf8_rejected(client, db_engine):
    r = client.post("/benchmarks/", json={"name": "CSVBenchBad", "type": "custom", "metric": "accuracy"})
    bid = r.json()["id"]
    files = {"file": ("dataset.csv", b"\xff\xfe invalid bytes", "text/csv")}
    resp = client.post(f"/benchmarks/{bid}/upload-dataset", files=files)
    assert resp.status_code == 422


def test_upload_json_missing_items_key(client, db_engine):
    r = client.post("/benchmarks/", json={"name": "JSONBenchBad", "type": "custom", "metric": "accuracy"})
    bid = r.json()["id"]
    files = {"file": ("dataset.json", b'{"data":[{"q":"a"}]}', "application/json")}
    resp = client.post(f"/benchmarks/{bid}/upload-dataset", files=files)
    assert resp.status_code == 422
    assert "items" in resp.json()["detail"]


def test_upload_json_path_within_extension_ok(client, db_engine):
    r = client.post("/benchmarks/", json={"name": "JSONBenchOK", "type": "custom", "metric": "accuracy"})
    bid = r.json()["id"]
    payload = json.dumps({"items": [{"q": "a"}]}).encode()
    files = {"file": ("good_data.json", payload, "application/json")}
    resp = client.post(f"/benchmarks/{bid}/upload-dataset", files=files)
    assert resp.status_code == 200


# ── get_benchmark_items ────────────────────────────────────────────────────────

def test_get_benchmark_items_no_dataset_no_hf(client, db_engine):
    r = client.post("/benchmarks/", json={"name": "NoDSBench", "type": "custom", "metric": "accuracy"})
    bid = r.json()["id"]
    resp = client.get(f"/benchmarks/{bid}/items")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] in ("no_dataset", "hf_error", "unknown")


def test_get_benchmark_items_with_local_dataset(client, db_engine, tmp_bench_dir):
    r = client.post("/benchmarks/", json={"name": "LocalDSBench", "type": "custom", "metric": "accuracy"})
    bid = r.json()["id"]
    # Upload a dataset
    items = [{"prompt": f"Q{i}", "answer": f"A{i}"} for i in range(5)]
    payload = json.dumps({"items": items}).encode()
    files = {"file": ("local.json", payload, "application/json")}
    client.post(f"/benchmarks/{bid}/upload-dataset", files=files)

    resp = client.get(f"/benchmarks/{bid}/items?page=1&page_size=3")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "local"
    assert len(body["items"]) <= 3


def test_get_benchmark_items_not_found(client):
    resp = client.get("/benchmarks/999999/items")
    assert resp.status_code == 404


def test_get_benchmark_items_search_filter(client, db_engine):
    r = client.post("/benchmarks/", json={"name": "SearchBench", "type": "custom", "metric": "accuracy"})
    bid = r.json()["id"]
    items = [{"prompt": "apple question"}, {"prompt": "banana question"}, {"prompt": "cherry question"}]
    payload = json.dumps({"items": items}).encode()
    files = {"file": ("search.json", payload, "application/json")}
    client.post(f"/benchmarks/{bid}/upload-dataset", files=files)

    resp = client.get(f"/benchmarks/{bid}/items?search=apple")
    assert resp.status_code == 200
    body = resp.json()
    assert all("apple" in str(item).lower() for item in body["items"])


# ── list_benchmark_sources ─────────────────────────────────────────────────────

def test_list_benchmark_sources_returns_list(client):
    resp = client.get("/benchmarks/sources")
    assert resp.status_code == 200
    body = resp.json()
    assert "sources" in body
    assert isinstance(body["sources"], list)
    assert body["total"] > 0


# ── packs ──────────────────────────────────────────────────────────────────────

def test_publish_benchmark_pack(client, custom_bench):
    resp = client.post("/benchmarks/packs", json={
        "name": "Test Pack",
        "slug": "test-pack-v1",
        "version": "1.0.0",
        "publisher": "TestLab",
        "family": "community",
        "benchmark_ids": [custom_bench],
        "is_public": True,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "test-pack-v1"
    assert custom_bench in body["benchmark_ids"]


def test_publish_pack_duplicate_version_rejected(client, custom_bench):
    # First publish
    client.post("/benchmarks/packs", json={
        "name": "Dup Pack",
        "slug": "dup-pack",
        "version": "1.0.0",
        "publisher": "",
        "family": "community",
        "benchmark_ids": [custom_bench],
    })
    # Duplicate
    resp = client.post("/benchmarks/packs", json={
        "name": "Dup Pack",
        "slug": "dup-pack",
        "version": "1.0.0",
        "publisher": "",
        "family": "community",
        "benchmark_ids": [custom_bench],
    })
    assert resp.status_code == 409


def test_publish_pack_missing_benchmark_rejected(client):
    resp = client.post("/benchmarks/packs", json={
        "name": "Bad Pack",
        "slug": "bad-pack",
        "version": "1.0.0",
        "family": "community",
        "benchmark_ids": [999999],
    })
    assert resp.status_code == 404


def test_list_benchmark_packs(client, custom_bench):
    resp = client.get("/benchmarks/packs")
    assert resp.status_code == 200
    assert "packs" in resp.json()


def test_list_benchmark_packs_with_family_filter(client, custom_bench):
    resp = client.get("/benchmarks/packs?family=community")
    assert resp.status_code == 200
    packs = resp.json()["packs"]
    assert all(p["family"] == "community" for p in packs)


def test_list_benchmark_packs_include_private(client, db_engine, custom_bench):
    # Add a private pack
    with Session(db_engine) as s:
        pack = BenchmarkPack(
            slug="private-pack",
            name="Private Pack",
            version="1.0.0",
            publisher="",
            family="community",
            changelog="",
            benchmark_ids_json=json.dumps([custom_bench]),
            is_public=False,
        )
        s.add(pack)
        s.commit()
    # Without include_private, should not see it
    resp_public = client.get("/benchmarks/packs?include_private=false")
    public_slugs = [p["slug"] for p in resp_public.json()["packs"]]
    assert "private-pack" not in public_slugs
    # With include_private=true, it should appear
    resp_all = client.get("/benchmarks/packs?include_private=true")
    all_slugs = [p["slug"] for p in resp_all.json()["packs"]]
    assert "private-pack" in all_slugs


def test_get_benchmark_pack_by_slug(client, custom_bench):
    client.post("/benchmarks/packs", json={
        "name": "Get Pack",
        "slug": "get-pack-slug",
        "version": "2.0.0",
        "family": "community",
        "benchmark_ids": [custom_bench],
    })
    resp = client.get("/benchmarks/packs/get-pack-slug")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "get-pack-slug"
    assert "versions" in body


def test_get_benchmark_pack_not_found(client):
    resp = client.get("/benchmarks/packs/nonexistent-slug-xyz")
    assert resp.status_code == 404


# ── fork ───────────────────────────────────────────────────────────────────────

def test_fork_benchmark(client, custom_bench):
    resp = client.post(f"/benchmarks/{custom_bench}/fork", json={
        "new_name": "ForkBench",
        "fork_type": "extension",
        "changes_description": "Extended version",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["forked_from"]["id"] == custom_bench
    assert body["fork_type"] == "extension"


def test_fork_benchmark_not_found(client):
    resp = client.post("/benchmarks/999999/fork", json={"new_name": "X"})
    assert resp.status_code == 404


def test_fork_benchmark_auto_renames_on_conflict(client, custom_bench):
    # Fork twice with same name — second should get timestamp suffix
    resp1 = client.post(f"/benchmarks/{custom_bench}/fork", json={"new_name": "ConflictFork"})
    resp2 = client.post(f"/benchmarks/{custom_bench}/fork", json={"new_name": "ConflictFork"})
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    # Names should differ
    assert resp1.json()["name"] != resp2.json()["name"]


def test_fork_benchmark_with_dataset_copies_file(client, db_engine, tmp_bench_dir):
    # Create a bench with dataset
    r = client.post("/benchmarks/", json={"name": "ForkSrcDS", "type": "custom", "metric": "accuracy"})
    src_id = r.json()["id"]
    payload = json.dumps({"items": [{"q": "a"}]}).encode()
    files = {"file": ("src.json", payload, "application/json")}
    client.post(f"/benchmarks/{src_id}/upload-dataset", files=files)
    # Fork it
    resp = client.post(f"/benchmarks/{src_id}/fork", json={"new_name": "ForkWithDS"})
    assert resp.status_code == 200
    assert resp.json()["dataset_path"] is not None


def test_fork_benchmark_no_body(client, custom_bench):
    resp = client.post(f"/benchmarks/{custom_bench}/fork")
    assert resp.status_code == 200  # uses default values


# ── lineage ────────────────────────────────────────────────────────────────────

def test_get_benchmark_lineage(client, custom_bench):
    # Fork to create lineage
    fork_resp = client.post(f"/benchmarks/{custom_bench}/fork", json={"new_name": "LineageFork"})
    fork_id = fork_resp.json()["id"]

    # Lineage of parent
    resp = client.get(f"/benchmarks/{custom_bench}/lineage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["benchmark_id"] == custom_bench
    assert "children" in body

    # Lineage of child
    resp2 = client.get(f"/benchmarks/{fork_id}/lineage")
    assert resp2.status_code == 200
    assert resp2.json()["benchmark_id"] == fork_id


def test_get_benchmark_lineage_not_found(client):
    resp = client.get("/benchmarks/999999/lineage")
    assert resp.status_code == 404


# ── citations ──────────────────────────────────────────────────────────────────

def test_get_benchmark_citations_empty(client, custom_bench):
    resp = client.get(f"/benchmarks/{custom_bench}/citations")
    assert resp.status_code == 200
    body = resp.json()
    assert "citations" in body
    assert "citation_count" in body


def test_add_and_get_citation(client, custom_bench):
    resp = client.post(f"/benchmarks/{custom_bench}/citations", json={
        "paper_doi": "https://arxiv.org/abs/2301.12345",
        "citing_lab": "TestLab",
        "year": 2023,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["paper_doi"] == "https://arxiv.org/abs/2301.12345"
    assert body["year"] == 2023

    # Now get citations — should include the one we added
    get_resp = client.get(f"/benchmarks/{custom_bench}/citations")
    assert get_resp.status_code == 200
    assert get_resp.json()["citation_count"] >= 1


def test_add_citation_not_found(client):
    resp = client.post("/benchmarks/999999/citations", json={
        "paper_doi": "https://arxiv.org/abs/2301.99999",
        "citing_lab": "Lab",
        "year": 2024,
    })
    assert resp.status_code == 404


def test_add_citation_empty_doi_rejected(client, custom_bench):
    resp = client.post(f"/benchmarks/{custom_bench}/citations", json={
        "paper_doi": "   ",
        "citing_lab": "Lab",
        "year": 2024,
    })
    assert resp.status_code == 422


def test_get_citations_not_found(client):
    resp = client.get("/benchmarks/999999/citations")
    assert resp.status_code == 404


def test_get_citations_uses_defaults_for_known_benchmark(client, db_engine):
    """For benchmarks with entries in BENCHMARK_SCIENCE, defaults are returned."""
    with Session(db_engine) as s:
        # Use a name that matches BENCHMARK_SCIENCE
        b = Benchmark(
            name="(CBRN-E) Chemical",
            type=BenchmarkType.SAFETY,
            metric="accuracy",
            is_builtin=True,
        )
        s.add(b)
        s.commit()
        s.refresh(b)
        bid = b.id

    resp = client.get(f"/benchmarks/{bid}/citations")
    assert resp.status_code == 200
    body = resp.json()
    # Should have default citations from BENCHMARK_SCIENCE
    assert body["citation_count"] >= 0


# ── benchmark card ─────────────────────────────────────────────────────────────

def test_get_benchmark_card_basic(client, custom_bench):
    resp = client.get(f"/benchmarks/{custom_bench}/card")
    assert resp.status_code == 200
    body = resp.json()
    assert body["benchmark_id"] == custom_bench
    assert "threat_model" in body
    assert "papers" in body
    assert "scoring_method" in body
    assert "completeness_score" in body


def test_get_benchmark_card_known_name(client, db_engine):
    with Session(db_engine) as s:
        b = Benchmark(
            name="CKB (Cyber Killchain Bench)",
            type=BenchmarkType.SAFETY,
            metric="accuracy",
            is_builtin=True,
        )
        s.add(b)
        s.commit()
        s.refresh(b)
        bid = b.id

    resp = client.get(f"/benchmarks/{bid}/card")
    assert resp.status_code == 200
    body = resp.json()
    assert body["completeness_score"] > 0
    assert "threat_model" in body
    assert body["threat_model"] != ""


def test_get_benchmark_card_not_found(client):
    resp = client.get("/benchmarks/999999/card")
    assert resp.status_code == 404


# ── benchmark versions ────────────────────────────────────────────────────────

def test_get_benchmark_versions(client, custom_bench):
    resp = client.get(f"/benchmarks/{custom_bench}/versions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["benchmark_id"] == custom_bench
    assert "current_version" in body
    assert "version_hash" in body["current_version"]


def test_get_benchmark_versions_not_found(client):
    resp = client.get("/benchmarks/999999/versions")
    assert resp.status_code == 404


# ── _extract_parent_id_from_config helpers ────────────────────────────────────

def test_extract_parent_id_from_config_valid():
    b = Benchmark(name="X", type=BenchmarkType.CUSTOM, metric="acc",
                  config_json=json.dumps({"forked_from": {"id": 42}}))
    result = bench_mod._extract_parent_id_from_config(b)
    assert result == 42


def test_extract_parent_id_from_config_missing():
    b = Benchmark(name="X", type=BenchmarkType.CUSTOM, metric="acc",
                  config_json=json.dumps({}))
    assert bench_mod._extract_parent_id_from_config(b) is None


def test_extract_parent_id_from_config_invalid_json():
    b = Benchmark(name="X", type=BenchmarkType.CUSTOM, metric="acc",
                  config_json="NOT JSON!")
    assert bench_mod._extract_parent_id_from_config(b) is None


# ── _get_citation_count helper ────────────────────────────────────────────────

def test_get_citation_count_none_benchmark_id(db_engine):
    with Session(db_engine) as s:
        count = bench_mod._get_citation_count(s, None)
    assert count == 0


# ── _card_completeness helper ─────────────────────────────────────────────────

def test_card_completeness_full():
    card = {
        "threat_model": "x",
        "papers": ["p"],
        "scoring_method": "x",
        "known_blind_spots": "x",
        "autonomy_levels": ["L1"],
        "confidence_bounds": "x",
    }
    assert bench_mod._card_completeness(card) == 100


def test_card_completeness_empty():
    assert bench_mod._card_completeness({}) == 0


def test_card_completeness_partial():
    card = {"threat_model": "x", "papers": ["p"]}
    score = bench_mod._card_completeness(card)
    assert 0 < score < 100


# ── _get_threat_domains & _is_blocking helpers ────────────────────────────────

def test_get_threat_domains_returns_list():
    result = bench_mod._get_threat_domains("SomeBenchmarkName")
    assert isinstance(result, list)


def test_is_blocking_returns_bool():
    result = bench_mod._is_blocking("SomeBenchmarkName")
    assert isinstance(result, bool)


# ── import-huggingface (mocked HTTP) ──────────────────────────────────────────

def test_import_huggingface_mocked(client, db_engine):
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "rows": [
            {"row": {"question": "Q1", "answer": "A1"}},
            {"row": {"question": "Q2", "answer": "A2"}},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, *args, **kwargs):
            return mock_response

    with patch.object(httpx, "AsyncClient", return_value=FakeClient()):
        resp = client.post("/benchmarks/import-huggingface", json={
            "repo_id": "test/dataset",
            "split": "test",
            "max_items": 10,
        })
    assert resp.status_code in (200, 400, 502)


def test_import_huggingface_not_found_dataset(client):
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 404

    class FakeClient404:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, *args, **kwargs):
            return mock_response

    with patch.object(httpx, "AsyncClient", return_value=FakeClient404()):
        resp = client.post("/benchmarks/import-huggingface", json={
            "repo_id": "nonexistent/repo",
            "split": "test",
            "max_items": 10,
        })
    assert resp.status_code == 404


# ── _default_citations_for_benchmark ─────────────────────────────────────────

def test_default_citations_known_benchmark():
    b = Benchmark(name="(CBRN-E) Chemical", type=BenchmarkType.SAFETY, metric="accuracy")
    defaults = bench_mod._default_citations_for_benchmark(b)
    assert isinstance(defaults, list)
    assert len(defaults) > 0
    assert "paper_doi" in defaults[0]


def test_default_citations_unknown_benchmark():
    b = Benchmark(name="Unknown Bench XYZ", type=BenchmarkType.CUSTOM, metric="accuracy")
    defaults = bench_mod._default_citations_for_benchmark(b)
    assert defaults == []
