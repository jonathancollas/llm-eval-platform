import os
import secrets
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import Settings, get_settings, resolve_bench_library_path

BUNDLED_BENCH_LIBRARY = Path(__file__).resolve().parent.parent / "bench_library"
REFUSALS_MARKER = BUNDLED_BENCH_LIBRARY / "safety" / "refusals.json"


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


def test_settings_accepts_secret_key_meeting_minimum_length(monkeypatch):
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


def test_resolve_bench_library_falls_back_from_empty_docker_defaults():
    """README compose used /bench_library mounted from an empty host folder."""
    assert REFUSALS_MARKER.is_file()
    for docker_default in ("/bench_library", "/app/bench_library"):
        resolved = resolve_bench_library_path(docker_default)
        assert Path(resolved) == BUNDLED_BENCH_LIBRARY
        assert (Path(resolved) / "safety" / "refusals.json").is_file()


def test_resolve_bench_library_keeps_explicit_custom_path(tmp_path):
    resolved = resolve_bench_library_path(str(tmp_path))
    assert resolved == str(tmp_path)


def test_resolve_bench_library_keeps_path_that_already_has_datasets():
    resolved = resolve_bench_library_path(str(BUNDLED_BENCH_LIBRARY))
    assert Path(resolved) == BUNDLED_BENCH_LIBRARY


def test_settings_docker_default_bench_library_uses_bundled_datasets(monkeypatch):
    monkeypatch.setenv("BENCH_LIBRARY_PATH", "/bench_library")
    settings = Settings()
    assert (Path(settings.bench_library_path) / "safety" / "refusals.json").is_file()


def test_docker_compose_mounts_backend_bench_library():
    """Quick start must bind-mount the bundled datasets, not the empty root folder."""
    repo = Path(__file__).resolve().parents[2]
    compose = (repo / "docker-compose.yml").read_text()
    assert compose.count("./backend/bench_library:/bench_library") == 2
    assert "- ./bench_library:/bench_library" not in compose
    assert REFUSALS_MARKER.is_file()
