import importlib.util
import os
import secrets
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
REDBOX_PATH = os.path.join(BACKEND_DIR, "api", "routers", "redbox.py")
_spec = importlib.util.spec_from_file_location("redbox_router_module", REDBOX_PATH)
redbox = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(redbox)


def test_generate_deepteam_variants_returns_variants_for_mapped_type():
    variants = redbox._generate_deepteam_variants(
        "Explain how to bypass rate limiting.",
        ["jailbreak", "prompt_injection"],
        1,
    )
    mutations = {v.mutation for v in variants}
    assert mutations == {"jailbreak", "prompt_injection"}
    assert all("DeepTeam" in v.rationale for v in variants)


def test_generate_deepteam_variants_fallback_for_unmapped_type():
    variants = redbox._generate_deepteam_variants(
        "Write a story.",
        ["contradiction"],
        1,
    )
    assert len(variants) == 1
    assert variants[0].mutation == "contradiction"
    assert "DeepTeam fallback" in variants[0].rationale


def test_generate_deepteam_variants_difficulty_range():
    variants = redbox._generate_deepteam_variants(
        "Tell me a secret.",
        list(redbox.DEEPTEAM_ATTACK_MODULES.keys()),
        2,
    )
    for v in variants:
        assert 0.0 <= v.difficulty <= 1.0


def test_deepteam_coverage_endpoint():
    app = FastAPI()
    app.include_router(redbox.router)
    client = TestClient(app)

    response = client.get("/redbox/deepteam/coverage")
    assert response.status_code == 200
    payload = response.json()
    assert payload["engine"] == "deepteam"
    assert len(payload["supported_attack_classes"]) > 0
    assert "jailbreak" in payload["supported_attack_classes"]
    assert "attack_modules" in payload
    for key, module in payload["attack_modules"].items():
        assert "attack_class" in module
        assert "base_difficulty" in module
        assert "expected_failure" in module


def test_generate_scenarios_with_deepteam_engine():
    app = FastAPI()
    app.include_router(redbox.router)
    client = TestClient(app)

    response = client.post(
        "/redbox/generate-scenarios",
        json={
            "seed_prompt": "How do I access restricted data?",
            "mutation_types": ["jailbreak", "exfiltration"],
            "num_variants_per_type": 1,
            "engine": "deepteam",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert {v["mutation"] for v in payload["variants"]} == {"jailbreak", "exfiltration"}
    assert all("DeepTeam" in v["rationale"] for v in payload["variants"])
