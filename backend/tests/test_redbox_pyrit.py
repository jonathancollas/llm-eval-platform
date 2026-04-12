import importlib.util
import os
import pathlib
import sys

import pytest

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Test-only key for Settings initialization during unit tests.
os.environ.setdefault("SECRET_KEY", "a" * 64)

_REDBOX_PATH = pathlib.Path(__file__).resolve().parents[1] / "api" / "routers" / "redbox.py"
_SPEC = importlib.util.spec_from_file_location("redbox_router_module", _REDBOX_PATH)
redbox = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(redbox)


@pytest.mark.asyncio
async def test_generate_pyrit_variants_returns_empty_if_pyrit_not_installed(monkeypatch):
    def _fake_import_module(name: str):
        if name == "pyrit":
            raise ModuleNotFoundError("pyrit not installed")
        raise AssertionError(f"Unexpected import: {name}")

    monkeypatch.setattr(redbox.importlib, "import_module", _fake_import_module)

    variants = await redbox._generate_pyrit_variants("seed objective", ["jailbreak", "multi_turn"], 2)
    assert variants == []


@pytest.mark.asyncio
async def test_generate_llm_variants_combines_pyrit_and_fallback(monkeypatch):
    pyrit_variant = redbox.ForgeVariant(
        mutation="jailbreak",
        prompt="pyrit prompt",
        difficulty=0.8,
        expected_failure="safety_bypass",
        rationale="pyrit",
    )

    async def _fake_pyrit(seed: str, mutation_types: list[str], n: int):
        assert seed == "seed objective"
        assert mutation_types == ["jailbreak", "ambiguity"]
        assert n == 1
        return [pyrit_variant]

    def _fake_rule_based(seed: str, mutation_types: list[str], n: int):
        assert seed == "seed objective"
        assert mutation_types == ["ambiguity"]
        assert n == 1
        return [
            redbox.ForgeVariant(
                mutation="ambiguity",
                prompt="rule prompt",
                difficulty=0.3,
                expected_failure="instruction_drift",
                rationale="rule",
            )
        ]

    monkeypatch.setattr(redbox, "_generate_pyrit_variants", _fake_pyrit)
    monkeypatch.setattr(redbox, "_generate_rule_based", _fake_rule_based)
    monkeypatch.setattr(redbox.settings, "anthropic_api_key", "", raising=False)

    variants = await redbox._generate_llm_variants(
        seed="seed objective",
        mutation_types=["jailbreak", "ambiguity"],
        n=1,
        use_pyrit=True,
    )

    assert [v.mutation for v in variants] == ["jailbreak", "ambiguity"]
    assert variants[0].rationale == "pyrit"
    assert variants[1].rationale == "rule"
