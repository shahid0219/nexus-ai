"""Deployment-related regression tests.

Found while actually running the Docker image on 2026-11-05:

1. `/api/github/status` returned HTTP 503 in the container because `git` is not
   installed there. That took down the whole GitHub page even though every other
   feature works. It now reports `available: false` with an explanation.
2. Video rendering failed with "no TTF font found" because font paths were
   hardcoded to `C:/Windows/Fonts/...`. They are now discovered across Windows,
   Linux, macOS and a bundled `tools/fonts` directory.
"""
from pathlib import Path

import pytest

from app.modules import github, youtube


def test_github_status_degrades_without_git(monkeypatch):
    monkeypatch.setattr(github.shutil, "which", lambda name: None)
    out = github.github_status()
    assert out["available"] is False
    assert out["tools"]["git"] is False
    assert out["changes"] == []
    assert "git" in out["gh"]["detail"]
    assert out["note"]


def test_github_status_degrades_without_a_checkout(monkeypatch):
    monkeypatch.setattr(github.shutil, "which",
                        lambda name: r"C:\Program Files\Git\bin\git.exe")
    monkeypatch.setattr(github.config, "ROOT", Path("C:/definitely/not/a/repo"))
    out = github.github_status()
    assert out["available"] is False
    assert "git checkout" in out["gh"]["detail"]


def test_github_status_is_available_in_a_real_checkout():
    """The developer machine is a checkout with git, so this must be live."""
    import shutil
    if not shutil.which("git") or not (github.config.ROOT / ".git").exists():
        pytest.skip("not running inside the git checkout")
    out = github.github_status()
    assert out["available"] is True
    assert out["tools"]["git"] is True
    assert "branch" in out


def test_font_discovery_prefers_a_real_ttf():
    found = youtube._font_path()
    if found is None:
        pytest.skip("no TTF font installed in this environment")
    assert isinstance(found, Path)
    assert found.is_file()
    assert found.suffix.lower() in (".ttf", ".ttc")


def test_font_candidates_are_cross_platform():
    # Compare as POSIX text: Windows stringifies Path("/usr/share/...") with
    # backslashes, so the raw str() form would hide the Linux entries.
    text = " ".join(p.as_posix() for p in youtube._font_candidates)
    assert "C:/Windows" in text
    assert "/usr/share/fonts" in text
    assert "/System/Library/Fonts" in text
    assert "tools/fonts" in text


def test_fontfile_reports_actionable_error_when_missing(monkeypatch):
    monkeypatch.setattr(youtube, "_font_path", lambda: None)
    with pytest.raises(Exception) as exc:
        youtube._fontfile()
    assert "font" in str(exc.value).lower()
    assert "fonts-dejavu-core" in str(exc.value) or "tools/fonts" in str(exc.value)
