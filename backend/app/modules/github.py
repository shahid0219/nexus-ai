"""GitHub integration — repository status, secret scan, safe commit + push, profile prep.

Security posture:
  * every git invocation is built here with a fixed argument shape; no caller supplies
    raw git arguments and `shell=True` is never used
  * a secret scan runs before staging, and again on the staged diff
  * only paths that the scanner marks safe may be committed
  * any public profile change is previewed and needs owner approval first
"""
from __future__ import annotations

import json
import re
import shutil

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import activity, approvals, config, db, process
from ..security import ApprovalRequired, NexusError, now_iso, redact

router = APIRouter(prefix="/api/github", tags=["github"])

# Files that must never be committed, whatever .gitignore says.
FORBIDDEN_PATHS = [
    r"(^|/)data/credentials\.json$", r"(^|/)data/nexus\.db", r"(^|/)\.env",
    r"(^|/)node_modules/", r"(^|/)frontend/dist/", r"(^|/)\.venv/", r"(^|/)venv/",
    r"\.pem$", r"\.key$", r"(^|/)\.npmrc$", r"(^|/)\.npm-cache",
    r"(^|/)data/uploads/", r"(^|/)data/reports/", r"(^|/)data/artifacts/",
]

SECRET_PATTERNS = [
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("private_key", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("bearer_literal", re.compile(r"(?i)\bauthorization\s*[:=]\s*['\"]?bearer\s+"
                                  r"[A-Za-z0-9._-]{20,}")),
    ("assigned_secret", re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|client[_-]?secret|password|secret)"
        r"\s*[:=]\s*['\"]([A-Za-z0-9._\-/+]{20,})['\"]")),
]

SCAN_MAX_BYTES = 2_000_000

_cache: dict = {"ts": 0.0, "result": None}


def _git(*args: str, timeout: float = 120) -> dict:
    return process.run(["git", *args], timeout=timeout, cwd=str(config.ROOT))


def _git_ok(*args: str, timeout: float = 120) -> str:
    out = _git(*args, timeout=timeout)
    if out["returncode"] != 0:
        msg = redact((out["stderr"] or out["stdout"] or "").strip())[:400]
        raise NexusError(f"git {' '.join(args)} failed: {msg}", code="git_failed",
                         status=400)
    return out["stdout"] or ""


# ------------------------------------------------------------------ status ---
def _remote_url() -> str | None:
    out = _git("remote", "get-url", "origin")
    return (out["stdout"] or "").strip() or None if out["returncode"] == 0 else None


def _gh_json(*args: str) -> dict | None:
    if not shutil.which("gh"):
        return None
    out = process.run(["gh", *args], timeout=90)
    if out["returncode"] != 0:
        return None
    try:
        return json.loads(out["stdout"])
    except ValueError:
        return None


def _gh_auth() -> dict:
    if not shutil.which("gh"):
        return {"available": False, "authenticated": False,
                "detail": "gh CLI not on PATH"}
    out = process.run(["gh", "auth", "status"], timeout=30)
    text = redact((out["stdout"] or "") + (out["stderr"] or ""))
    logged_in = "Logged in to github.com account" in text
    acct = re.search(r"account\s+(\S+)", text)
    scopes = re.search(r"Token scopes:\s*'([^']*)'", text)
    return {"available": True, "authenticated": logged_in,
            "account": acct.group(1) if acct else None,
            "scopes": scopes.group(1) if scopes else None,
            "detail": "authenticated via gh (token never read by NEXUS)"
            if logged_in else "run `gh auth login`"}


@router.get("/status")
def github_status():
    branch = (_git("branch", "--show-current")["stdout"] or "").strip() or None
    porcelain = _git("status", "--porcelain", "--untracked-files=normal")["stdout"] or ""
    changed = [line for line in porcelain.splitlines() if line.strip()]
    ahead = _git("rev-list", "--count", "@{u}..HEAD")
    behind = _git("rev-list", "--count", "HEAD..@{u}")
    last = _git("log", "-1", "--pretty=%H%x09%s")
    last_hash, _, last_subject = (last["stdout"] or "").strip().partition("\t")
    remote = _remote_url()
    return {
        "gh": _gh_auth(),
        "remote": remote,
        "remote_ok": bool(remote and "github.com" in remote),
        "branch": branch,
        "dirty": bool(changed),
        "changed_files": len(changed),
        "changes": changed[:200],
        "ahead": int(ahead["stdout"].strip()) if ahead["returncode"] == 0 else None,
        "behind": int(behind["stdout"].strip()) if behind["returncode"] == 0 else None,
        "last_commit": {"hash": last_hash or None, "subject": last_subject or None},
        "tools": {"git": shutil.which("git") is not None,
                  "gh": shutil.which("gh") is not None},
        "ts": now_iso(),
    }


# ------------------------------------------------------------- secret scan ---
def _scan_text(path: str, text: str) -> list[dict]:
    findings = []
    for name, rx in SECRET_PATTERNS:
        for m in rx.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            snippet = redact(m.group(0))
            findings.append({"path": path, "rule": name, "line": line,
                             "preview": snippet[:40]})
    return findings


@router.get("/secret-scan")
def secret_scan():
    """Scan tracked and untracked (non-ignored) files for credential-shaped strings."""
    files = _git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    names = [f for f in (files["stdout"] or "").split("\0") if f.strip()]
    findings: list[dict] = []
    scanned = 0
    skipped: list[str] = []
    for rel in names:
        norm = rel.replace("\\", "/")
        if any(re.search(p, norm) for p in FORBIDDEN_PATHS):
            findings.append({"path": norm, "rule": "forbidden_path", "line": 0,
                             "preview": "this path must never be committed"})
            continue
        full = config.ROOT / norm
        try:
            if not full.is_file() or full.stat().st_size > SCAN_MAX_BYTES:
                skipped.append(norm)
                continue
            text = full.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            skipped.append(norm)
            continue
        scanned += 1
        findings.extend(_scan_text(norm, text))
    result = {"scanned_files": scanned, "skipped": skipped[:50],
              "findings": findings, "clean": len(findings) == 0, "ts": now_iso()}
    return result


# ------------------------------------------------------------ commit + push ---
class CommitIn(BaseModel):
    message: str = Field(min_length=5, max_length=200)
    paths: list[str] = Field(default_factory=list, max_length=500)
    push: bool = True


def _validate_paths(paths: list[str]) -> list[str]:
    if not paths:
        raise NexusError("no paths supplied — refusing to stage everything implicitly",
                         code="paths_required", status=422)
    clean: list[str] = []
    for p in paths:
        norm = str(p).replace("\\", "/").strip()
        if not norm or norm.startswith("/") or ".." in norm.split("/"):
            raise NexusError(f"unsafe path: {p}", code="unsafe_path", status=400)
        if any(re.search(rx, norm) for rx in FORBIDDEN_PATHS):
            raise NexusError(f"refusing to commit protected path: {p}",
                             code="forbidden_path", status=400)
        clean.append(norm)
    return clean


@router.post("/commit")
def commit(body: CommitIn):
    paths = _validate_paths(body.paths)
    scan = secret_scan()
    blocked = [f for f in scan["findings"] if f["path"] in paths]
    if blocked:
        raise NexusError(
            "secret scan blocked the commit: "
            + ", ".join(sorted({f"{f['path']} ({f['rule']})" for f in blocked}))[:300],
            code="secret_detected", status=400)

    existing = [p for p in paths if (config.ROOT / p).exists()]
    if not existing:
        raise NexusError("none of the supplied paths exist", code="not_found",
                         status=404)

    _git_ok("add", "--", *existing)

    diff = _git("diff", "--cached", "--name-only")
    staged = [p for p in (diff["stdout"] or "").splitlines() if p.strip()]
    if not staged:
        return {"code": "nothing_to_commit", "staged": []}

    staged_scan = _scan_staged()
    if staged_scan:
        _git("reset", "--", *staged)
        raise NexusError("secret scan blocked the staged changes: "
                         + ", ".join(sorted({f"{f['path']} ({f['rule']})"
                                             for f in staged_scan}))[:300],
                         code="secret_detected", status=400)

    _git_ok("commit", "-m", body.message)
    sha = (_git("rev-parse", "HEAD")["stdout"] or "").strip()
    result = {"code": "committed", "sha": sha, "staged": staged,
              "message": body.message, "pushed": False}

    if body.push:
        result["push"] = _push()
        result["pushed"] = result["push"]["code"] == "pushed"
    activity.info("github", f"commit {sha[:8]} created", {"files": len(staged)})
    return result


def _scan_staged() -> list[dict]:
    out = _git("diff", "--cached", "--unified=0")
    findings: list[dict] = []
    path = None
    for line in (out["stdout"] or "").splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        findings.extend(_scan_text(path or "?", line[1:]))
    return findings


def _push() -> dict:
    out = _git("push", "origin", "HEAD", timeout=300)
    if out["returncode"] == 0:
        return {"code": "pushed",
                "detail": redact((out["stderr"] or out["stdout"] or "").strip())[:300]}
    msg = redact((out["stderr"] or out["stdout"] or "").strip())[:400]
    code = "auth_failed" if re.search(r"(?i)auth|credential|permission denied", msg) \
        else "push_failed"
    return {"code": code, "detail": msg}


@router.post("/push")
def push():
    status = github_status()
    if not status["remote_ok"]:
        raise NexusError("origin is not a GitHub URL", code="remote_invalid", status=400)
    if not status["gh"]["authenticated"]:
        raise NexusError("gh is not authenticated — run `gh auth login`",
                         code="not_authenticated", status=401)
    scan = secret_scan()
    if not scan["clean"]:
        raise NexusError("secret scan found issues — resolve them before pushing",
                         code="secret_detected", status=400)
    result = _push()
    if result["code"] != "pushed":
        raise NexusError(result["detail"], code=result["code"], status=400)
    return result


@router.get("/verify")
def verify():
    status = github_status()
    info = _gh_json("repo", "view", "--json",
                    "name,visibility,defaultBranchRef,pushedAt,url")
    remote_head = None
    if status["remote_ok"]:
        out = _git("ls-remote", "origin", "HEAD", timeout=120)
        if out["returncode"] == 0 and (out["stdout"] or "").strip():
            remote_head = out["stdout"].split()[0]
    local_head = (_git("rev-parse", "HEAD")["stdout"] or "").strip() or None
    return {"local_head": local_head, "remote_head": remote_head,
            "in_sync": bool(local_head and remote_head and local_head == remote_head),
            "repo": info, "ts": now_iso()}


# ------------------------------------------------------------------ profile ---
PROFILE_README_MARKER = "<!-- nexus-managed-profile -->"


def _public_repos(limit: int = 100) -> list[dict]:
    data = _gh_json("repo", "list", "--limit", str(limit), "--json",
                    "name,description,visibility,primaryLanguage,topics,url,"
                    "isFork,updatedAt,stargazerCount")
    return data or []


def _real_stack(repos: list[dict]) -> dict:
    """Derive technologies only from repositories that actually exist here."""
    langs: dict[str, int] = {}
    topics: set[str] = set()
    for r in repos:
        lang = (r.get("primaryLanguage") or {}).get("name")
        if lang:
            langs[lang] = langs.get(lang, 0) + 1
        for t in r.get("topics") or []:
            topics.add(t)
    return {"languages": sorted(langs, key=lambda k: -langs[k]),
            "topics": sorted(topics)}


@router.get("/profile/preview")
def profile_preview():
    """Build the proposed profile changes. Nothing is applied here."""
    auth = _gh_auth()
    if not auth["authenticated"]:
        raise NexusError("gh is not authenticated — run `gh auth login`",
                         code="not_authenticated", status=401)
    account = auth.get("account") or "shahid0219"
    repos = _public_repos()
    public = [r for r in repos if r.get("visibility") == "PUBLIC" and not r.get("isFork")]
    stack = _real_stack(public)
    profile_exists = bool(_gh_json("repo", "view", f"{account}/{account}", "--json",
                                   "name"))
    nexus_public = any(r["name"] == "nexus-ai" and r.get("visibility") == "PUBLIC"
                       for r in repos)
    showcase = []
    for r in public:
        showcase.append({"name": r["name"], "description": r.get("description"),
                         "language": (r.get("primaryLanguage") or {}).get("name"),
                         "url": r.get("url"), "topics": r.get("topics") or []})
    return {
        "account": account,
        "profile_repo_exists": profile_exists,
        "nexus_repo_public": nexus_public,
        "nexus_stays_private": not nexus_public,
        "detected_stack": stack,
        "public_repos": showcase,
        "pinned_recommendation": [r["name"] for r in public[:6]],
        "note": "Preview only — nothing has been written to GitHub.",
        "ts": now_iso(),
    }


class ProfileApplyIn(BaseModel):
    bio: str | None = Field(default=None, max_length=160)
    readme_markdown: str | None = Field(default=None, max_length=20000)
    repo_descriptions: dict = Field(default_factory=dict)


@router.post("/profile/apply")
def profile_apply(body: ProfileApplyIn):
    try:
        approvals.require_approved(
            "github.profile.update", "Update public GitHub profile and profile README",
            {"bio": bool(body.bio), "readme": bool(body.readme_markdown),
             "repos": sorted(body.repo_descriptions)[:20]})
    except ApprovalRequired as exc:
        return {"code": "approval_required", "approval_id": exc.approval_id,
                "kind": exc.kind,
                "message": "Editing the public profile requires owner approval. "
                           "Approve, then retry."}
    if body.bio and not shutil.which("gh"):
        raise NexusError("gh CLI required", code="tool_missing", status=503)
    applied = []
    if body.readme_markdown:
        applied.append(_apply_readme(body.readme_markdown))
    for name, desc in (body.repo_descriptions or {}).items():
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", str(name)):
            continue
        out = process.run(["gh", "repo", "edit", str(name), "--description",
                           str(desc)[:350]], timeout=60)
        applied.append({"repo": name, "ok": out["returncode"] == 0})
    activity.info("github", "profile changes applied", {"count": len(applied)})
    return {"code": "applied", "applied": applied,
            "note": "Bio edits need a token with user scope; gh auth refresh is "
                    "required and is never run automatically."}


def _apply_readme(markdown: str) -> dict:
    """Create/update <account>/<account> README in a temp clone (no token handling)."""
    auth = _gh_auth()
    account = auth.get("account") or "shahid0219"
    exists = _gh_json("repo", "view", f"{account}/{account}", "--json", "name")
    if not exists:
        out = process.run(["gh", "repo", "create", f"{account}/{account}",
                           "--public", "--description",
                           "GitHub profile README"], timeout=120)
        if out["returncode"] != 0:
            return {"repo": f"{account}/{account}", "ok": False,
                    "detail": redact(out["stderr"] or out["stdout"])[:200]}
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp(prefix="nexus_profile_"))
    clone = process.run(["gh", "repo", "clone", f"{account}/{account}",
                         str(tmp / "repo"), "--", "--depth=1"], timeout=180)
    if clone["returncode"] != 0:
        return {"repo": f"{account}/{account}", "ok": False,
                "detail": redact(clone["stderr"] or clone["stdout"])[:200]}
    target = tmp / "repo" / "README.md"
    target.write_text(markdown, encoding="utf-8")
    wt = process.run(["git", "-C", str(tmp / "repo"), "add", "README.md"], timeout=60)
    if wt["returncode"] != 0:
        return {"repo": f"{account}/{account}", "ok": False,
                "detail": redact(wt["stderr"])[:200]}
    cm = process.run(["git", "-C", str(tmp / "repo"), "commit", "-m",
                      "docs: update profile README (NEXUS AI)"], timeout=60)
    if cm["returncode"] != 0:
        return {"repo": f"{account}/{account}", "ok": False,
                "detail": redact(cm["stderr"])[:200]}
    ps = process.run(["git", "-C", str(tmp / "repo"), "push", "origin", "HEAD"],
                     timeout=180)
    return {"repo": f"{account}/{account}", "ok": ps["returncode"] == 0,
            "detail": redact(ps["stderr"] or ps["stdout"])[:200]}


@router.get("/profile/repos")
def profile_repos():
    auth = _gh_auth()
    if not auth["authenticated"]:
        raise NexusError("gh is not authenticated", code="not_authenticated",
                         status=401)
    repos = _public_repos()
    return {"account": auth.get("account"),
            "repos": [{"name": r["name"],
                       "description": r.get("description"),
                       "visibility": r.get("visibility"),
                       "language": (r.get("primaryLanguage") or {}).get("name"),
                       "topics": r.get("topics") or [],
                       "url": r.get("url"),
                       "fork": r.get("isFork")} for r in repos],
            "ts": now_iso()}
