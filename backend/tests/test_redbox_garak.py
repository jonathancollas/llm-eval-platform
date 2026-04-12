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


def test_generate_llm_variants_garak_covers_required_categories():
    variants = redbox._generate_garak_variants(
        "Explain secure coding basics.",
        ["jailbreak", "prompt_injection", "exfiltration", "multilingual"],
        1,
    )
    covered = {v.mutation for v in variants}
    assert covered == {"jailbreak", "prompt_injection", "exfiltration", "multilingual"}
    assert all(v.rationale.startswith("Garak probe:") for v in variants)


def test_generate_scenarios_uses_num_variants_field():
    app = FastAPI()
    app.include_router(redbox.router)
    client = TestClient(app)

    response = client.post(
        "/redbox/generate-scenarios",
        json={
            "seed_prompt": "Summarize this report.",
            "mutation_types": ["exfiltration", "jailbreak"],
            "num_variants_per_type": 1,
            "engine": "garak",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert {v["mutation"] for v in payload["variants"]} == {"exfiltration", "jailbreak"}

