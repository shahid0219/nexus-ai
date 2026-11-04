"""GitHub module tests — secret scanning, path guards, status, profile preview.

These tests never push, never call the network, and never touch the real repository:
git and gh invocations are stubbed.
"""
import pytest

from app import db
from app.modules import github
from app.security import NexusError


@pytest.fixture(autouse=True)
def clean():
    db.init_db()
    db.execute("DELETE FROM approvals")
    yield
    db.execute("DELETE FROM approvals")


def _stub_git(monkeypatch, stdout="", returncode=0):
    def fake(args, timeout=300, cwd=None):
        joined = " ".join(args)
        if joined.startswith("git "):
            joined = joined[4:]
        payload = stdout
        if joined.startswith("status --porcelain"):
            payload = ""
        elif joined.startswith("rev-list"):
            payload = "0\n"
        elif joined.startswith("log -1"):
            payload = "abc1234\tfeat: something\n"
        elif joined.startswith("branch --show-current"):
            payload = "main\n"
        elif joined.startswith("remote get-url"):
            payload = "https://github.com/shahid0219/nexus-ai.git\n"
        elif joined.startswith("ls-files"):
            payload = ""
        elif joined.startswith("rev-parse"):
            payload = "deadbeef\n"
        return {"returncode": returncode, "stdout": payload, "stderr": ""}
    monkeypatch.setattr(github.process, "run", fake)


def test_forbidden_paths_blocked():
    for bad in ("data/credentials.json", ".env", "frontend/dist/index.html",
                "node_modules/pkg/index.js", "frontend/.npmrc", "key.pem"):
        with pytest.raises(NexusError) as exc:
            github._validate_paths([bad])
        assert exc.value.code == "forbidden_path"


def test_path_traversal_rejected():
    with pytest.raises(NexusError) as exc:
        github._validate_paths(["../outside.txt"])
    assert exc.value.code == "unsafe_path"


def test_absolute_path_rejected():
    with pytest.raises(NexusError) as exc:
        github._validate_paths(["/etc/passwd"])
    assert exc.value.code == "unsafe_path"


def test_empty_paths_refused():
    with pytest.raises(NexusError) as exc:
        github._validate_paths([])
    assert exc.value.code == "paths_required"


def test_normal_paths_allowed():
    assert github._validate_paths(["backend/app/main.py", "README.md"]) == [
        "backend/app/main.py", "README.md"]


def test_scan_text_detects_github_token():
    findings = github._scan_text("x.py", 'TOKEN = "ghp_' + "a" * 30 + '"')
    assert any(f["rule"] == "github_token" for f in findings)
    assert all("a" * 30 not in f["preview"] for f in findings)


def test_scan_text_detects_private_key():
    findings = github._scan_text("k.py", "-----BEGIN RSA PRIVATE KEY-----")
    assert any(f["rule"] == "private_key" for f in findings)


def test_scan_text_detects_openai_key():
    findings = github._scan_text("a.py", 'key = "sk-' + "b" * 32 + '"')
    assert any(f["rule"] == "openai_key" for f in findings)


def test_scan_text_clean_file_has_no_findings():
    assert github._scan_text("ok.py", "print('hello world')") == []


def test_scan_preview_is_redacted():
    findings = github._scan_text("a.py", "api_key = 'sk-" + "c" * 40 + "'")
    assert findings
    assert all("c" * 40 not in f["preview"] for f in findings)


def test_status_reports_remote_and_branch(monkeypatch):
    _stub_git(monkeypatch)
    monkeypatch.setattr(github.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(github, "_gh_auth", lambda: {
        "available": True, "authenticated": True, "account": "shahid0219",
        "scopes": "repo", "detail": "ok"})
    st = github.github_status()
    assert st["remote_ok"] is True
    assert st["branch"] == "main"
    assert st["dirty"] is False
    assert st["last_commit"]["hash"] == "abc1234"


def test_commit_requires_approval_free_but_scans(monkeypatch):
    _stub_git(monkeypatch)
    monkeypatch.setattr(github, "secret_scan", lambda: {
        "scanned_files": 3, "skipped": [], "clean": False, "ts": "now",
        "findings": [{"path": "app/x.py", "rule": "github_token", "line": 4,
                      "preview": "ghp_***"}]})
    with pytest.raises(NexusError) as exc:
        github.commit(github.CommitIn(message="test commit", paths=["app/x.py"],
                                      push=False))
    assert exc.value.code == "secret_detected"


def test_profile_apply_creates_pending_approval(monkeypatch):
    monkeypatch.setattr(github, "_gh_auth", lambda: {
        "available": True, "authenticated": True, "account": "shahid0219",
        "scopes": "repo", "detail": "ok"})
    out = github.profile_apply(github.ProfileApplyIn(
        bio="Backend developer", readme_markdown="# Hi"))
    assert out["code"] == "approval_required"
    row = db.one("SELECT * FROM approvals WHERE kind='github.profile.update'")
    assert row is not None and row["status"] == "pending"


def test_profile_preview_never_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(github, "_gh_auth", lambda: {
        "available": True, "authenticated": True, "account": "shahid0219",
        "scopes": "repo", "detail": "ok"})
    monkeypatch.setattr(github, "_public_repos", lambda limit=100: [
        {"name": "nexus-ai", "visibility": "PRIVATE", "isFork": False,
         "primaryLanguage": {"name": "Python"}, "topics": ["fastapi"],
         "url": "https://github.com/shahid0219/nexus-ai", "description": None}])
    monkeypatch.setattr(github, "_gh_json", lambda *a, **kw: None)
    p = github.profile_preview()
    assert p["profile_repo_exists"] is False
    assert p["nexus_stays_private"] is True
    assert p["public_repos"] == []
    assert "Preview only" in p["note"]


def test_profile_apply_rejected_kind_is_declared():
    from app import approvals
    assert "github.profile.update" in approvals.GATED_KINDS
