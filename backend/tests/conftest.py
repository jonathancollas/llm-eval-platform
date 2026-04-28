"""
conftest.py — global test configuration for Mercury Retrograde.
Ensures test_http.py always gets a fresh DB with the current schema.
"""
import os
import pathlib
import pytest
from sqlmodel import SQLModel


def pytest_runtest_setup(item):
    """Before each test in test_http.py, ensure schema is current."""
    if "test_http" in str(item.fspath):
        # Force DATABASE_URL to test_http.db for this module
        os.environ["DATABASE_URL"] = "sqlite:///./test_http.db"
        # Recreate tables with current schema on the active engine
        try:
            from core.database import engine
            SQLModel.metadata.create_all(engine)
        except Exception:
            pass


@pytest.fixture(scope="session", autouse=True)
def clean_test_http_db():
    """Remove stale test_http.db before session so schema is always fresh."""
    db_path = pathlib.Path(__file__).parent.parent / "test_http.db"
    if db_path.exists():
        try:
            db_path.unlink()
        except OSError:
            pass
    yield


@pytest.fixture(autouse=True)
def _redroom_authorized_scope_for_tests(request):
    """Open AuthorizedScope for tests in test_redroom_*.

    Adversarial engine functions (run_pair, run_coevolution,
    run_compositional_attack, run_garak_subprocess, …) refuse to run
    outside an :class:`AuthorizedScope`. The runner opens that scope
    after charter.enforce(). Tests that call those functions directly
    need to be inside a scope; this fixture opens one for the entire
    test_redroom_* suite so individual tests don't have to.

    Tests that explicitly want to assert the unauthorized branch
    decorate themselves with ``@pytest.mark.no_authorized_scope``.
    """
    from eval_engine.redroom._authorized_scope import AuthorizedScope

    is_redroom = "test_redroom_" in str(request.fspath)
    opt_out = request.node.get_closest_marker("no_authorized_scope") is not None

    if is_redroom and not opt_out:
        with AuthorizedScope():
            yield
    else:
        yield


def pytest_configure(config):
    """Register custom markers used by the redroom test suite."""
    config.addinivalue_line(
        "markers",
        "no_authorized_scope: skip the autouse AuthorizedScope fixture "
        "(test exercises the unauthorized branch directly)",
    )
