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
