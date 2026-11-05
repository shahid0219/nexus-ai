"""Tool-discovery and process allowlist tests.

Covers a real bug found on 2026-11-05: this machine's user PATH is truncated, so
`shutil.which("ffmpeg")` returned None even though FFmpeg was installed. Video
rendering therefore failed with `tool_missing` while `start_nexus.bat` worked.
`config` now falls back to known install locations (including WinGet's versioned
package folders), and `process.resolve` uses that same lookup.
"""
import os
from pathlib import Path

import pytest

from app import config, process
from app.security import NexusError


def test_find_tool_falls_back_to_known_location(tmp_path, monkeypatch):
    """A binary present in a known folder is found even when PATH is empty."""
    fake_bin = tmp_path / "tools" / "ffmpeg" / "bin"
    fake_bin.mkdir(parents=True)
    exe = fake_bin / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)

    monkeypatch.setattr(config.shutil, "which", lambda name: None)
    monkeypatch.setattr(config, "ROOT", tmp_path)

    assert config.ffmpeg_path() == str(exe)


def test_find_tool_handles_winget_versioned_folder(tmp_path, monkeypatch):
    """WinGet nests binaries under a package folder whose name need not match."""
    packages = tmp_path / "Packages"
    nested = packages / "Gyan.FFmpeg_x" / "ffmpeg-8.1.1-full_build" / "bin"
    nested.mkdir(parents=True)
    exe = nested / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)

    monkeypatch.setattr(config.shutil, "which", lambda name: None)
    monkeypatch.setattr(config, "_candidate_bins", lambda tool: [packages])

    found = config.ffprobe_path()
    assert found is not None
    assert Path(found).name == exe.name


def test_missing_tool_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda name: None)
    monkeypatch.setattr(config, "_candidate_bins",
                        lambda tool: [tmp_path / "nothing-here"])
    assert config.ffmpeg_path() is None


def test_process_resolve_uses_config_discovery(monkeypatch):
    monkeypatch.setattr(config, "ffmpeg_path", lambda: r"C:\fake\ffmpeg.exe")
    assert process.resolve("ffmpeg") == r"C:\fake\ffmpeg.exe"
    assert process.resolve(r"C:\fake\ffmpeg.exe") == r"C:\fake\ffmpeg.exe"


def test_process_resolve_reports_missing_when_discovery_fails(monkeypatch):
    monkeypatch.setattr(config, "ffmpeg_path", lambda: None)
    with pytest.raises(NexusError) as exc:
        process.resolve("ffmpeg")
    assert exc.value.code == "tool_missing"


def test_non_allowlisted_binary_still_refused(monkeypatch):
    monkeypatch.setattr(config, "ffmpeg_path", lambda: r"C:\fake\ffmpeg.exe")
    with pytest.raises(NexusError) as exc:
        process.resolve("powershell")
    assert exc.value.code == "subprocess_not_allowed"


def test_git_and_gh_remain_allowlisted():
    assert "git" in config.ALLOWED_SUBPROCESSES
    assert "gh" in config.ALLOWED_SUBPROCESSES
    assert "ffmpeg" in config.ALLOWED_SUBPROCESSES
    assert "ffprobe" in config.ALLOWED_SUBPROCESSES
    # A shell must never be allowlisted.
    for banned in ("cmd", "powershell", "bash", "sh", "python"):
        assert banned not in config.ALLOWED_SUBPROCESSES
