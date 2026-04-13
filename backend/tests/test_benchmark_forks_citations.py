import os
import sys
import importlib.util
import uuid
import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

BACKEND_DIR = Path(__file__).resolve().parent.parent
BENCHMARKS_PATH = BACKEND_DIR / "api" / "routers" / "benchmarks.py"
_spec = importlib.util.spec_from_file_location("benchmarks_router_module", BENCHMARKS_PATH)
benchmarks = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(benchmarks)


def _create_benchmark(client: TestClient, name: str) -> int:
    resp = client.post(
        "/benchmarks/",
        json={
            "name": name,
            "type": "custom",
            "description": "fixture benchmark",
            "tags": ["custom"],
            "metric": "accuracy",
            "config": {},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_fork_lineage_and_citation_graph(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/forks_and_citations.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(benchmarks.router)
    app.dependency_overrides[benchmarks.get_session] = _get_session_override

    with TestClient(app) as client:
        parent_id = _create_benchmark(client, f"fork-parent-{uuid.uuid4().hex[:8]}")
        fork_resp = client.post(
            f"/benchmarks/{parent_id}/fork",
            json={
                "new_name": f"fork-child-{uuid.uuid4().hex[:8]}",
                "fork_type": "multilingual",
                "changes_description": "Added FR/ES datasets",
                "forked_by": 42,
            },
        )
        assert fork_resp.status_code == 200, fork_resp.text
        child_id = fork_resp.json()["id"]

        parent_lineage = client.get(f"/benchmarks/{parent_id}/lineage")
        assert parent_lineage.status_code == 200
        payload = parent_lineage.json()
        assert payload["fork_count"] == 1
        assert payload["children"][0]["id"] == child_id
        assert payload["children"][0]["fork_type"] == "multilingual"

        child_lineage = client.get(f"/benchmarks/{child_id}/lineage")
        assert child_lineage.status_code == 200
        assert child_lineage.json()["parent"]["id"] == parent_id

        add_citation = client.post(
            f"/benchmarks/{parent_id}/citations",
            json={"paper_doi": "10.1234/example.benchmark.2026", "citing_lab": "MIT Lab", "year": 2026},
        )
        assert add_citation.status_code == 200, add_citation.text

        citation_graph = client.get(f"/benchmarks/{parent_id}/citations")
        assert citation_graph.status_code == 200
        graph = citation_graph.json()
        assert graph["citation_count"] == 1
        assert graph["labs"][0]["name"] == "MIT Lab"
        assert graph["influence_score"] >= 2  # citation + at least one fork child/lab contribution

        listed = client.get("/benchmarks/")
        assert listed.status_code == 200
        parent_entry = next((b for b in listed.json() if b["id"] == parent_id), None)
        assert parent_entry is not None
        assert parent_entry["citation_count"] == 1
