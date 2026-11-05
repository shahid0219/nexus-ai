"""NEXUS AI configuration — paths, ports, model policy, allowlists."""
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "NEXUS AI"
VERSION = "1.0.0"

ROOT = Path(__file__).resolve().parents[2]          # .../nexus-ai
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIST = ROOT / "frontend" / "dist"
DATA_DIR = ROOT / "data"
ARTIFACTS_DIR = DATA_DIR / "artifacts"
REPORTS_DIR = DATA_DIR / "reports"
UPLOADS_DIR = DATA_DIR / "uploads"
CREDENTIALS_FILE = DATA_DIR / "credentials.json"
DB_PATH = DATA_DIR / "nexus.db"

HOST = "127.0.0.1"                                  # localhost only — never 0.0.0.0
PORT = int(os.environ.get("NEXUS_PORT", "8777"))    # 8765 belongs to ai_business
DEV_PORT = 5173

# --- Local AI policy (4GB VRAM) -------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
# Ordered preference. Anything whose file is bigger than AI_MAX_MODEL_GB is skipped
# so a small GPU never tries to load a model that will not fit.
PREFERRED_MODELS = [
    "qwen2.5-coder:3b", "qwen2.5:3b", "gemma3:1b", "ministral-3:3b",
    "qwen3.5:4b", "llama3.2:3b", "llama3.2:1b", "phi3:mini", "gemma2:2b",
]
AI_MAX_MODEL_GB = float(os.environ.get("NEXUS_AI_MAX_MODEL_GB", "5.5"))
AI_MAX_TOKENS = int(os.environ.get("NEXUS_AI_TOKENS", "1024"))
AI_TIMEOUT = float(os.environ.get("NEXUS_AI_TIMEOUT", "90"))
AI_RETRIES = int(os.environ.get("NEXUS_AI_RETRIES", "1"))
AI_BACKOFF = float(os.environ.get("NEXUS_AI_BACKOFF", "1.5"))
# One request at a time keeps a 4GB card stable.
AI_LOCK_TIMEOUT = 120.0

# --- Subprocess allowlist (SECURITY.md §4: no shell=True, no arbitrary exec)
ALLOWED_SUBPROCESSES = {"ffmpeg", "ffprobe", "gh", "git"}

# --- External egress allowlist (SECURITY.md §6) ---------------------------
ALLOWED_HOSTS = {
    "127.0.0.1", "localhost",
    "graph.facebook.com", "instagram.com", "www.instagram.com",
    "oauth2.googleapis.com", "www.googleapis.com", "accounts.google.com",
    "api.remotive.com", "remoteok.com",
    "hn.algolia.com", "www.reddit.com",
    "api.github.com", "github.com",
}

for _d in (DATA_DIR, ARTIFACTS_DIR, REPORTS_DIR, UPLOADS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def frontend_built() -> bool:
    return (FRONTEND_DIST / "index.html").exists()


# --- tool discovery --------------------------------------------------------
# `shutil.which` only searches PATH. On Windows a truncated or stale PATH is a
# common reason a working install looks "missing", so fall back to the well-known
# install locations before reporting a tool as absent.
def _candidate_bins(tool: str) -> list[Path]:
    """Known install directories for an optional binary, most-specific first."""
    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    program_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
    if tool in ("ffmpeg", "ffprobe"):
        return [
            ROOT / "tools" / "ffmpeg" / "bin",
            local / "Microsoft" / "WinGet" / "Packages",
            local / "hermes" / "tools",
            program_files / "ffmpeg" / "bin",
            Path("C:/ffmpeg/bin"),
            Path("C:/ffmpeg/ffmpeg/bin"),
            local / "chocolatey" / "bin",
            Path("C:/ProgramData/chocolatey/bin"),
        ]
    return []


def _find_tool(tool: str) -> str | None:
    """Resolve an optional binary: PATH first, then known install locations."""
    found = shutil.which(tool)
    if found:
        return found
    exe = f"{tool}.exe" if os.name == "nt" else tool
    for base in _candidate_bins(tool):
        if not base.exists():
            continue
        direct = base / exe
        if direct.is_file():
            return str(direct)
        # WinGet keeps each package in a versioned subfolder whose name may
        # differ from the binary (e.g. `ffmpeg-8.1.1-full_build/bin/ffprobe.exe`),
        # so search any nested bin/ directory rather than matching the tool name.
        try:
            if base.name == "Packages":
                for sub in base.glob("*/**/bin/" + exe):
                    if sub.is_file():
                        return str(sub)
            else:
                for sub in base.glob("**/bin/" + exe):
                    if sub.is_file():
                        return str(sub)
        except OSError:
            continue
    return None


def ffmpeg_path() -> str | None:
    return _find_tool("ffmpeg")


def ffprobe_path() -> str | None:
    return _find_tool("ffprobe")


def tool_version(name: str) -> str | None:
    """Presence-only probe for tools we never execute (node/git/gh)."""
    return shutil.which(name)


def python_version() -> str:
    return sys.version.split()[0]
