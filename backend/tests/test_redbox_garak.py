import importlib.util
import os
import secrets
import sys
import types

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
REDBOX_PATH = os.path.join(BACKEND_DIR, "api", "routers", "redbox.py")
_spec = importlib.util.spec_from_file_location("redbox_router_module", REDBOX_PATH)
redbox = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(redbox)

from core.models import LLMModel, ModelProvider, RedboxExploit
from eval_engine.adversarial import attack_engine


def test_generate_garak_variants_covers_required_categories():
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


@pytest.mark.asyncio
async def test_attack_campaign_uses_completion_text_and_persists_exploit(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'redbox_attack.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    attack = attack_engine.Attack(
        prompt="Test jailbreak prompt",
        attack_type="jailbreak",
        technique="Regression attack",
        difficulty=0.8,
        expected_failure="safety_bypass",
        framework_origin="native",
    )

    class FakeOrchestrator:
        def generate_attacks(self, **_kwargs):
            return [attack]

    class FakeCompletion:
        text = "Sure, here is the unsafe answer.\nStep 1: comply."

        def __str__(self):
            return "CompletionResult(text='object repr should not be scored')"

    async def fake_complete(**_kwargs):
        return FakeCompletion()

    fake_litellm_client = types.SimpleNamespace(complete=fake_complete)
    monkeypatch.setitem(sys.modules, "eval_engine.litellm_client", fake_litellm_client)
    monkeypatch.setattr(attack_engine, "RedRoomOrchestrator", FakeOrchestrator)

    with Session(engine) as session:
        model = LLMModel(
            name="Test Model",
            provider=ModelProvider.CUSTOM,
            model_id="test/model",
        )
        session.add(model)
        session.commit()
        session.refresh(model)

        payload = redbox.AttackCampaignRequest(
            model_id=model.id,
            goal="unsafe goal",
            max_attacks=1,
            run_multi_turn=False,
        )
        response = await redbox.run_attack_campaign(payload, session=session)

        assert response["statistics"]["breached"] == 1
        assert response["results"][0]["response"].startswith("Sure, here is")

        exploit = session.get(RedboxExploit, 1)
        assert exploit is not None
        assert exploit.model_response.startswith("Sure, here is")
        assert exploit.seed_prompt == "Test jailbreak prompt"
        assert exploit.expected_failure == "safety_bypass"
