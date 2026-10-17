"""Harness clients must not share API keys through the process environment.

lm-eval's LocalCompletionsAPI reads OPENAI_API_KEY when building the
Authorization header. Overlapping local-queue campaigns used to publish each
model's key into that variable, so one client's header could carry another
model's credential to a different base URL.
"""
import os
import sys
import threading
from functools import cached_property

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval_engine.harness_runner import _pin_lm_api_key  # noqa: E402


class _CachedHeaderClient:
    """lm-eval 0.4.4 shape: live api_key property, cached header."""

    @property
    def api_key(self) -> str:
        return os.environ.get("OPENAI_API_KEY", "")

    @cached_property
    def header(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}


class _LiveHeaderClient:
    """Same lookup, but the header is recomputed on every access."""

    @property
    def api_key(self) -> str:
        return os.environ.get("OPENAI_API_KEY", "")

    @property
    def header(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}


@pytest.fixture
def restore_openai_env():
    previous = os.environ.get("OPENAI_API_KEY")
    yield
    if previous is None:
        os.environ.pop("OPENAI_API_KEY", None)
    else:
        os.environ["OPENAI_API_KEY"] = previous


@pytest.mark.parametrize("client_cls", [_CachedHeaderClient, _LiveHeaderClient])
def test_pin_keeps_each_client_on_its_own_key(client_cls, restore_openai_env):
    os.environ["OPENAI_API_KEY"] = "ambient-key"
    first = client_cls()
    second = client_cls()

    _pin_lm_api_key(first, "sk-model-a")
    _pin_lm_api_key(second, "sk-model-b")

    assert os.environ["OPENAI_API_KEY"] == "ambient-key"
    os.environ["OPENAI_API_KEY"] = "sk-intruder"
    assert first.api_key == "sk-model-a"
    assert second.api_key == "sk-model-b"
    assert first.header["Authorization"] == "Bearer sk-model-a"
    assert second.header["Authorization"] == "Bearer sk-model-b"


def test_pin_snapshots_ambient_key_when_model_has_none(restore_openai_env):
    os.environ["OPENAI_API_KEY"] = "ambient-key"
    client = _LiveHeaderClient()

    _pin_lm_api_key(client, "")

    os.environ["OPENAI_API_KEY"] = "replaced-later"
    assert client.api_key == "ambient-key"
    assert client.header["Authorization"] == "Bearer ambient-key"


def test_concurrent_pins_do_not_cross_keys(restore_openai_env):
    os.environ["OPENAI_API_KEY"] = "ambient-key"
    barrier = threading.Barrier(8)
    errors: list[BaseException] = []
    clients: list[_LiveHeaderClient] = []

    def _pin_one(index: int) -> None:
        try:
            client = _LiveHeaderClient()
            barrier.wait()
            _pin_lm_api_key(client, f"sk-model-{index}")
            os.environ["OPENAI_API_KEY"] = f"sk-racer-{index}"
            if client.header["Authorization"] != f"Bearer sk-model-{index}":
                raise AssertionError(client.header)
            clients.append(client)
        except BaseException as exc:  # noqa: BLE001 — collected for the main thread
            errors.append(exc)

    threads = [threading.Thread(target=_pin_one, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(clients) == 8
