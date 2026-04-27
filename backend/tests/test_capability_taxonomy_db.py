"""Tests for M3 capability taxonomy DB tables and heatmap API."""
import os
import secrets
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from core.models import (
    Benchmark,
    BenchmarkCapabilityMapping,
    BenchmarkType,
    CapabilityDomainRecord,
    CapabilityEvalScore,
    CapabilitySubCapabilityRecord,
    LLMModel,
    ModelProvider,
)


def _make_engine():
    return create_engine("sqlite://", connect_args={"check_same_thread": False})


def _setup_db(engine):
    SQLModel.metadata.create_all(engine)
    return Session(engine)


# ── Model creation helpers ────────────────────────────────────────────────────

def _seed_taxonomy(session: Session):
    """Seed minimal taxonomy: one domain with two sub-capabilities."""
    domain = CapabilityDomainRecord(
        slug="reasoning",
        display_name="Reasoning",
        description="Logical and mathematical reasoning",
        sort_order=0,
    )
    session.add(domain)
    session.flush()

    sc1 = CapabilitySubCapabilityRecord(
        domain_id=domain.id,
        slug="logical",
        display_name="Logical",
        description="Deductive inference",
        difficulty="medium",
        risk_level="low",
    )
    sc2 = CapabilitySubCapabilityRecord(
        domain_id=domain.id,
        slug="mathematical",
        display_name="Mathematical",
        description="Symbolic maths",
        difficulty="hard",
        risk_level="low",
    )
    session.add(sc1)
    session.add(sc2)
    session.flush()
    return domain, sc1, sc2


# ── CapabilityDomainRecord ────────────────────────────────────────────────────

def test_capability_domain_can_be_created():
    engine = _make_engine()
    with _setup_db(engine) as session:
        domain = CapabilityDomainRecord(slug="cybersecurity", display_name="Cybersecurity",
                                        description="Cyber-domain capabilities", sort_order=0)
        session.add(domain)
        session.commit()
        session.refresh(domain)
        assert domain.id is not None
        assert domain.slug == "cybersecurity"


def test_capability_domain_slug_is_unique():
    from sqlalchemy.exc import IntegrityError
    engine = _make_engine()
    with _setup_db(engine) as session:
        session.add(CapabilityDomainRecord(slug="dup", display_name="A", sort_order=0))
        session.commit()
    with _setup_db(engine) as session:
        session.add(CapabilityDomainRecord(slug="dup", display_name="B", sort_order=1))
        with pytest.raises(IntegrityError):
            session.commit()


# ── CapabilitySubCapabilityRecord ─────────────────────────────────────────────

def test_sub_capability_belongs_to_domain():
    engine = _make_engine()
    with _setup_db(engine) as session:
        domain, sc1, sc2 = _seed_taxonomy(session)
        session.commit()

        fetched = session.exec(
            select(CapabilitySubCapabilityRecord).where(
                CapabilitySubCapabilityRecord.domain_id == domain.id
            )
        ).all()
        assert len(fetched) == 2
        slugs = {sc.slug for sc in fetched}
        assert slugs == {"logical", "mathematical"}


def test_sub_capability_parent_id_is_nullable():
    """parent_id self-FK must be nullable (reserved for graph migration)."""
    engine = _make_engine()
    with _setup_db(engine) as session:
        domain, sc1, _sc2 = _seed_taxonomy(session)
        session.commit()
        assert sc1.parent_id is None


# ── BenchmarkCapabilityMapping ────────────────────────────────────────────────

def test_benchmark_capability_mapping_links_correctly():
    engine = _make_engine()
    with _setup_db(engine) as session:
        domain, sc1, _sc2 = _seed_taxonomy(session)
        bench = Benchmark(name="GSM8K", type=BenchmarkType.ACADEMIC, metric="accuracy")
        session.add(bench)
        session.flush()

        mapping = BenchmarkCapabilityMapping(
            benchmark_id=bench.id,
            sub_capability_id=sc1.id,
            mapping_source="auto",
        )
        session.add(mapping)
        session.commit()

        result = session.exec(
            select(BenchmarkCapabilityMapping).where(
                BenchmarkCapabilityMapping.benchmark_id == bench.id
            )
        ).all()
        assert len(result) == 1
        assert result[0].sub_capability_id == sc1.id
        assert result[0].mapping_source == "auto"


def test_benchmark_capability_mapping_source_manual():
    engine = _make_engine()
    with _setup_db(engine) as session:
        domain, sc1, _sc2 = _seed_taxonomy(session)
        bench = Benchmark(name="MathBench", type=BenchmarkType.ACADEMIC, metric="accuracy")
        session.add(bench)
        session.flush()
        session.add(BenchmarkCapabilityMapping(
            benchmark_id=bench.id, sub_capability_id=sc1.id, mapping_source="manual"
        ))
        session.commit()

        mapping = session.exec(select(BenchmarkCapabilityMapping)).first()
        assert mapping.mapping_source == "manual"


# ── CapabilityEvalScore ───────────────────────────────────────────────────────

def test_capability_eval_score_stores_ci():
    engine = _make_engine()
    with _setup_db(engine) as session:
        domain, sc1, _sc2 = _seed_taxonomy(session)
        model = LLMModel(name="gpt-4o", provider=ModelProvider.OPENAI, model_id="openai/gpt-4o")
        session.add(model)
        session.flush()

        score = CapabilityEvalScore(
            model_id=model.id,
            sub_capability_id=sc1.id,
            score=0.82,
            ci_lower=0.76,
            ci_upper=0.88,
            n_items=50,
        )
        session.add(score)
        session.commit()
        session.refresh(score)

        assert score.id is not None
        assert score.score == 0.82
        assert score.ci_lower == 0.76
        assert score.ci_upper == 0.88
        assert score.n_items == 50


def test_capability_eval_score_eval_run_id_is_nullable():
    engine = _make_engine()
    with _setup_db(engine) as session:
        domain, sc1, _sc2 = _seed_taxonomy(session)
        model = LLMModel(name="claude-3", provider=ModelProvider.ANTHROPIC, model_id="anthropic/claude-3")
        session.add(model)
        session.flush()
        score = CapabilityEvalScore(model_id=model.id, sub_capability_id=sc1.id, score=0.7)
        session.add(score)
        session.commit()
        session.refresh(score)
        assert score.eval_run_id is None


# ── _seed_capability_taxonomy integration ─────────────────────────────────────

def test_seed_capability_taxonomy_is_idempotent(monkeypatch, tmp_path):
    """Calling _seed_capability_taxonomy twice should not duplicate rows."""
    import core.database as core_db

    db_file = tmp_path / "test_taxonomy_seed.db"
    test_engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(test_engine)

    monkeypatch.setattr(core_db, "engine", test_engine)
    monkeypatch.setattr(core_db.settings, "database_url", f"sqlite:///{db_file}")

    core_db._seed_capability_taxonomy()
    core_db._seed_capability_taxonomy()

    with Session(test_engine) as session:
        domain_count = len(session.exec(select(CapabilityDomainRecord)).all())
        sub_cap_count = len(session.exec(select(CapabilitySubCapabilityRecord)).all())

    # 7 domains and all sub-capabilities from CAPABILITY_ONTOLOGY
    assert domain_count == 7
    # 4+4+4+4+4+4+3 = 27 sub-capabilities
    assert sub_cap_count == 27


def test_seed_populates_all_7_domains(monkeypatch, tmp_path):
    import core.database as core_db

    db_file = tmp_path / "test_7_domains.db"
    test_engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr(core_db, "engine", test_engine)
    monkeypatch.setattr(core_db.settings, "database_url", f"sqlite:///{db_file}")

    core_db._seed_capability_taxonomy()

    with Session(test_engine) as session:
        domains = session.exec(select(CapabilityDomainRecord)).all()
    slugs = {d.slug for d in domains}
    expected = {"cybersecurity", "reasoning", "instruction_following", "knowledge", "agentic", "safety", "multimodal"}
    assert slugs == expected


# ── Heatmap API ───────────────────────────────────────────────────────────────

def _load_cap_router():
    """Load the capability router module directly to avoid celery import via __init__."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "capability_router_isolated",
        os.path.join(os.path.dirname(__file__), "..", "api", "routers", "capability.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_test_client(test_engine, cap_router_mod):
    from fastapi import FastAPI
    from core.database import get_session

    def _override():
        with Session(test_engine) as session:
            yield session

    app = FastAPI()
    app.include_router(cap_router_mod.router)
    app.dependency_overrides[get_session] = _override
    return TestClient(app)


def test_heatmap_returns_expected_shape(monkeypatch, tmp_path):
    """GET /capability/heatmap returns correct keys even with no models."""
    import core.database as core_db

    db_file = tmp_path / "heatmap_test.db"
    test_engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(test_engine)

    monkeypatch.setattr(core_db, "engine", test_engine)
    monkeypatch.setattr(core_db.settings, "database_url", f"sqlite:///{db_file}")
    core_db._seed_capability_taxonomy()

    cap_router = _load_cap_router()
    client = _build_test_client(test_engine, cap_router)

    resp = client.get("/capability/heatmap")
    assert resp.status_code == 200
    body = resp.json()
    assert "domains" in body
    assert "models" in body
    assert "scores" in body
    assert "coverage" in body
    assert len(body["domains"]) == 7


def test_heatmap_reflects_model_scores(monkeypatch, tmp_path):
    """When a CapabilityEvalScore row exists, heatmap reflects it."""
    import core.database as core_db

    db_file = tmp_path / "heatmap_scores.db"
    test_engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(test_engine)

    monkeypatch.setattr(core_db, "engine", test_engine)
    monkeypatch.setattr(core_db.settings, "database_url", f"sqlite:///{db_file}")
    core_db._seed_capability_taxonomy()

    with Session(test_engine) as session:
        model = LLMModel(name="test-gpt", provider=ModelProvider.OPENAI, model_id="openai/test-gpt")
        session.add(model)
        session.flush()
        sc = session.exec(select(CapabilitySubCapabilityRecord).where(
            CapabilitySubCapabilityRecord.slug == "logical"
        )).first()
        assert sc is not None, "taxonomy must be seeded"
        score = CapabilityEvalScore(
            model_id=model.id,
            sub_capability_id=sc.id,
            score=0.75,
            ci_lower=0.68,
            ci_upper=0.82,
            n_items=40,
        )
        session.add(score)
        session.commit()
        model_id = model.id

    cap_router = _load_cap_router()
    client = _build_test_client(test_engine, cap_router)

    resp = client.get("/capability/heatmap")
    assert resp.status_code == 200
    body = resp.json()
    mid = str(model_id)
    assert mid in body["scores"]
    assert body["scores"][mid].get("logical") == pytest.approx(0.75, abs=0.01)
    assert body["coverage"][mid].get("logical") is True


def test_coverage_endpoint_lists_gaps(monkeypatch, tmp_path):
    """GET /capability/coverage correctly shows uncovered sub-capabilities."""
    import core.database as core_db

    db_file = tmp_path / "coverage_test.db"
    test_engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(test_engine)

    monkeypatch.setattr(core_db, "engine", test_engine)
    monkeypatch.setattr(core_db.settings, "database_url", f"sqlite:///{db_file}")
    core_db._seed_capability_taxonomy()

    with Session(test_engine) as session:
        model = LLMModel(name="gap-model", provider=ModelProvider.CUSTOM, model_id="custom/gap-model")
        session.add(model)
        session.commit()
        model_id = model.id

    cap_router = _load_cap_router()
    client = _build_test_client(test_engine, cap_router)

    resp = client.get("/capability/coverage")
    assert resp.status_code == 200
    body = resp.json()
    assert "models" in body
    model_entry = next((m for m in body["models"] if m["model_id"] == model_id), None)
    assert model_entry is not None
    # Model has no scored capabilities → all are gaps
    assert model_entry["evaluated_count"] == 0
    assert model_entry["coverage_pct"] == 0.0
    assert len(model_entry["gaps"]) == body["total_sub_capabilities"]
