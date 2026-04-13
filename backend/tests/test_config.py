import os
import secrets
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _clear_relevant_env(monkeypatch):
    for key in (
        "SECRET_KEY",
        "MERCURY_DEV_MODE",
        "RENDER",
        "RAILWAY_ENVIRONMENT",
        "FLY_APP_NAME",
        "HEROKU_APP_NAME",
        "K_SERVICE",
    ):
        monkeypatch.delenv(key, raising=False)


def test_settings_rejects_short_secret_key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "too-short")
    with pytest.raises(ValueError, match="SECRET_KEY must be at least 32 characters"):
        Settings()


def test_settings_requires_secret_key_when_render_env_set(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(ValueError, match="SECRET_KEY is required in production"):
        Settings()


def test_settings_generates_ephemeral_secret_key_when_missing():
    settings = Settings()
    assert len(settings.secret_key) == 64
    int(settings.secret_key, 16)


def test_settings_accepts_valid_secret_key(monkeypatch):
    key = secrets.token_hex(32)
    monkeypatch.setenv("SECRET_KEY", key)
    assert Settings().secret_key == key


def test_get_settings_cache_clear_refreshes_env(monkeypatch):
    first = secrets.token_hex(32)
    second = secrets.token_hex(32)

    monkeypatch.setenv("SECRET_KEY", first)
    first_settings = get_settings()

    monkeypatch.setenv("SECRET_KEY", second)
    cached_settings = get_settings()
    assert cached_settings.secret_key == first_settings.secret_key == first

    get_settings.cache_clear()
    refreshed_settings = get_settings()
    assert refreshed_settings.secret_key == second
