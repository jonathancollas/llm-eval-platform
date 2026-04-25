"""Path-traversal prevention tests for core.utils.resolve_safe_path.

Every documented attack vector (traversal, absolute paths, drive letters,
null bytes, symlink escapes, empty input) gets at least one test.

Audit reference: P0-4 / P0-5 — security boundaries on filesystem access.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.utils import resolve_safe_path  # noqa: E402


# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def safe_base(tmp_path: Path) -> Path:
    """A real directory with one inner file the tests can target legitimately."""
    inner = tmp_path / "data"
    inner.mkdir()
    (inner / "ok.json").write_text('{"a": 1}', encoding="utf-8")
    (inner / "sub").mkdir()
    (inner / "sub" / "nested.json").write_text('{"a": 2}', encoding="utf-8")
    return inner


# ═══════════════════════════════════════════════════════════════════════════
#  Happy path
# ═══════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    def test_simple_filename_is_resolved(self, safe_base: Path):
        result = resolve_safe_path(safe_base, "ok.json")
        assert result == (safe_base / "ok.json").resolve()
        assert result.read_text() == '{"a": 1}'

    def test_nested_relative_path_is_resolved(self, safe_base: Path):
        result = resolve_safe_path(safe_base, "sub/nested.json")
        assert result == (safe_base / "sub" / "nested.json").resolve()

    def test_dot_prefix_is_resolved(self, safe_base: Path):
        # './ok.json' is a legitimate way to express the current dir.
        result = resolve_safe_path(safe_base, "./ok.json")
        assert result == (safe_base / "ok.json").resolve()

    def test_internal_dot_dot_that_resolves_within_base(self, safe_base: Path):
        # 'sub/../ok.json' resolves to 'ok.json' which IS in base — should pass
        # because the FINAL resolved path is contained.
        result = resolve_safe_path(safe_base, "sub/../ok.json")
        assert result == (safe_base / "ok.json").resolve()


# ═══════════════════════════════════════════════════════════════════════════
#  Path traversal attacks
# ═══════════════════════════════════════════════════════════════════════════


class TestTraversalRejected:
    @pytest.mark.parametrize(
        "evil",
        [
            "../etc/passwd",
            "../../etc/passwd",
            "../../../../../../etc/passwd",
            "sub/../../etc/passwd",
            "sub/../../../etc/passwd",
            "./../etc/passwd",
        ],
    )
    def test_dot_dot_escape_raises(self, safe_base: Path, evil: str):
        with pytest.raises(ValueError, match="path traversal"):
            resolve_safe_path(safe_base, evil)

    def test_pure_dot_dot_raises(self, safe_base: Path):
        with pytest.raises(ValueError):
            resolve_safe_path(safe_base, "..")


# ═══════════════════════════════════════════════════════════════════════════
#  Absolute paths rejected
# ═══════════════════════════════════════════════════════════════════════════


class TestAbsolutePathsRejected:
    @pytest.mark.parametrize(
        "evil",
        [
            "/etc/passwd",
            "/var/log/syslog",
            "/",
        ],
    )
    def test_unix_absolute_rejected(self, safe_base: Path, evil: str):
        with pytest.raises(ValueError, match="absolute paths are not allowed"):
            resolve_safe_path(safe_base, evil)

    @pytest.mark.parametrize(
        "evil",
        [
            "C:/Windows/System32/config/SAM",
            "D:/Users/admin/Documents/secrets.txt",
            "Z:/anything",
        ],
    )
    def test_windows_drive_letter_rejected(self, safe_base: Path, evil: str):
        with pytest.raises(ValueError, match="drive-letter|absolute"):
            resolve_safe_path(safe_base, evil)

    def test_unc_path_rejected(self, safe_base: Path):
        with pytest.raises(ValueError, match="absolute|drive"):
            resolve_safe_path(safe_base, "\\\\server\\share\\file")


# ═══════════════════════════════════════════════════════════════════════════
#  Null byte injection
# ═══════════════════════════════════════════════════════════════════════════


class TestNullByteRejected:
    def test_null_byte_in_filename_raises(self, safe_base: Path):
        with pytest.raises(ValueError, match="null byte"):
            resolve_safe_path(safe_base, "ok.json\x00../../etc/passwd")

    def test_null_byte_at_end_raises(self, safe_base: Path):
        with pytest.raises(ValueError, match="null byte"):
            resolve_safe_path(safe_base, "ok.json\x00")

    def test_null_byte_at_start_raises(self, safe_base: Path):
        with pytest.raises(ValueError, match="null byte"):
            resolve_safe_path(safe_base, "\x00ok.json")


# ═══════════════════════════════════════════════════════════════════════════
#  Empty / wrong type input
# ═══════════════════════════════════════════════════════════════════════════


class TestBadInput:
    def test_empty_string_raises(self, safe_base: Path):
        with pytest.raises(ValueError, match="empty"):
            resolve_safe_path(safe_base, "")

    def test_whitespace_only_raises(self, safe_base: Path):
        with pytest.raises(ValueError, match="empty"):
            resolve_safe_path(safe_base, "   ")

    @pytest.mark.parametrize("evil", [None, 123, b"bytes", ["list"], {"dict": 1}])
    def test_non_string_raises(self, safe_base: Path, evil):
        with pytest.raises(ValueError, match="must be a string"):
            resolve_safe_path(safe_base, evil)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════
#  Symlink escape (POSIX-only — Windows symlinks need elevation)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(os.name == "nt", reason="symlink tests are POSIX-only")
class TestSymlinkEscape:
    def test_symlink_pointing_outside_base_is_rejected(
        self, tmp_path: Path
    ):
        # Setup: base/inside_link → ../outside
        base = tmp_path / "base"
        base.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("classified")
        (base / "inside_link").symlink_to(outside)

        # Resolving 'inside_link/secret.txt' through base should escape detection.
        # The current resolver follows symlinks at .resolve() time, then checks
        # containment, so this must raise.
        with pytest.raises(ValueError, match="path traversal"):
            resolve_safe_path(base, "inside_link/secret.txt")

    def test_symlink_pointing_inside_base_is_allowed(
        self, tmp_path: Path
    ):
        base = tmp_path / "base"
        base.mkdir()
        target = base / "real.json"
        target.write_text('{"a": 3}')
        (base / "shortcut").symlink_to(target)

        result = resolve_safe_path(base, "shortcut")
        assert result == target.resolve()


# ═══════════════════════════════════════════════════════════════════════════
#  Non-existent path is allowed (caller checks .exists() afterwards)
# ═══════════════════════════════════════════════════════════════════════════


class TestNonExistent:
    def test_resolves_a_non_existent_filename(self, safe_base: Path):
        # Resolving doesn't require the target to exist — that's the caller's job.
        result = resolve_safe_path(safe_base, "missing.json")
        assert result == (safe_base / "missing.json").resolve()
        assert not result.exists()
