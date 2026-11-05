"""Allowlisted subprocess runner. No shell, no arbitrary commands (SECURITY.md §4)."""
import shutil
import subprocess
from pathlib import Path

from . import config
from .security import NexusError


def _basename(binary: str) -> str:
    """Basename for either path separator.

    `Path(...).name` only splits on the host separator, so on Linux a Windows-style
    "C:\\tools\\ffmpeg.exe" would not resolve to "ffmpeg.exe". Accept both.
    """
    return binary.replace("\\", "/").rsplit("/", 1)[-1].strip().lower()


def resolve(binary: str) -> str:
    name = _basename(binary)
    # Accept both bare names and full paths, but only for allowlisted tools, and
    # always return the discovered location rather than the caller's string.
    for allowed in config.ALLOWED_SUBPROCESSES:
        if name == allowed or name == f"{allowed}.exe":
            if allowed == "ffmpeg":
                found = config.ffmpeg_path()
            elif allowed == "ffprobe":
                found = config.ffprobe_path()
            else:
                found = shutil.which(allowed)
            if found:
                return found
            raise NexusError(f"{allowed} is not installed or not on PATH",
                             code="tool_missing", status=503)
    raise NexusError(f"subprocess '{binary}' is not allowlisted",
                     code="subprocess_not_allowed", status=400)


def run(args: list[str], timeout: float = 300, cwd: str | None = None) -> dict:
    """Run an allowlisted binary with an argv list. Never uses shell=True."""
    if not args:
        raise NexusError("empty command", code="subprocess_not_allowed")
    exe = resolve(args[0])
    argv = [exe] + [str(a) for a in args[1:]]
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, errors="replace",
            timeout=timeout, cwd=cwd, shell=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise NexusError(f"{Path(exe).name} timed out after {timeout}s",
                         code="tool_timeout", status=504)
    return {
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-8000:],
        "stderr": (proc.stderr or "")[-8000:],
    }
