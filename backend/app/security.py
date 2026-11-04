"""Security helpers: secret redaction, input guards, approval-gated errors."""
import re
import unicodedata
from datetime import datetime, timezone

SECRET_RE = re.compile(
    r"(?i)(token|secret|password|passwd|api[_-]?key|authorization|bearer|client_secret)"
    r"(\s*[=:]\s*)([^\s\"',;&]+)")
BEARER_RE = re.compile(r"(?i)\b(bearer)\s+[^\s\"']+")
TOKEN_PREFIX_RE = re.compile(r"(?i)\b(gho_|ghp_|ghs_|ghu_|ghr_|sk-|xox[baprs]-)[^\s\"']+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact(text: str | None) -> str:
    """Mask anything that looks like a credential before it is stored or shown."""
    if not text:
        return ""
    out = SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", str(text))
    out = BEARER_RE.sub(lambda m: f"{m.group(1)} ***", out)
    out = TOKEN_PREFIX_RE.sub(lambda m: f"{m.group(1)}***", out)
    return out


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """Strip path traversal and unsafe characters from a user-supplied name."""
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    name = name.replace("..", "_")
    if not name:
        name = "file"
    return name[:max_len]


def clamp(value, lo, hi, default=None):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default if default is not None else lo
    return max(lo, min(hi, v))


class ApprovalRequired(Exception):
    """Raised when an action needs an owner approval record before it may run."""

    def __init__(self, approval_id: int, kind: str, title: str):
        self.approval_id = approval_id
        self.kind = kind
        self.title = title
        super().__init__(f"approval required: {kind}")


class NexusError(Exception):
    """Domain error with an HTTP-ish code the API layer surfaces verbatim."""

    def __init__(self, message: str, code: str = "error", status: int = 400):
        self.code = code
        self.status = status
        super().__init__(message)
