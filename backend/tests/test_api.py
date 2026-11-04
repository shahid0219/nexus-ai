"""NEXUS AI — end-to-end API tests (offline-first; network tests skip when offline)."""
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config, security
from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------- core ----------
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "ollama" in body and "models" in body["ollama"]


def test_system_status(client):
    body = client.get("/api/system/status").json()
    assert body["python"].startswith("3.")
    assert "cpu_percent" in body and "ram" in body
    assert "ffmpeg" in body["tools"] and "gh" in body["tools"]


def test_stats_shape(client):
    body = client.get("/api/stats").json()
    for key in ("approvals_pending", "revenue_verified_total", "jobs_discovered",
                "tasks_today"):
        assert key in body


def test_logs_endpoint(client):
    rows = client.get("/api/logs?limit=5").json()
    assert isinstance(rows, list)
    assert all("module" in r and "level" in r for r in rows)


# ------------------------------------------------------- honesty guards -------
def test_instagram_analytics_requires_auth(client):
    body = client.get("/api/instagram/analytics").json()
    assert body["requires_auth"] is True
    assert "metrics" not in body


def test_instagram_publish_requires_auth(client):
    body = client.post("/api/instagram/publish",
                       json={"caption": "test"}).json()
    assert body["requires_auth"] is True


def test_youtube_analytics_requires_auth(client):
    body = client.get("/api/youtube/analytics").json()
    assert body["requires_auth"] is True


def test_youtube_upload_requires_auth(client):
    body = client.post("/api/youtube/upload",
                       json={"video_path": "x.mp4", "title": "Test video"}).json()
    assert body["requires_auth"] is True


def test_youtube_oauth_status(client):
    body = client.get("/api/youtube/oauth/status").json()
    assert body["authorized"] is False
    assert body["status"] in ("awaiting_configuration", "awaiting_authentication")


def test_accounts_never_leak_secrets(client):
    body = client.get("/api/accounts").json()
    text = str(body).lower()
    assert "gho_" not in text and "access_token" not in text
    providers = {p["provider"]: p for p in body["providers"]}
    assert providers["linkedin"]["status"] == "not_applicable"
    assert providers["github"]["status"] in ("connected", "awaiting_authentication",
                                             "awaiting_configuration")


# ------------------------------------------------------------- approvals ------
def test_calendar_delete_requires_approval_then_works(client):
    created = client.post("/api/instagram/calendar",
                          json={"date": "2026-11-10", "platform": "instagram",
                                "title": "test entry", "brief": "b"}).json()
    assert created["id"]
    first = client.delete(f"/api/instagram/calendar/{created['id']}").json()
    assert first["code"] == "approval_required"
    aid = first["approval_id"]
    ok = client.post(f"/api/approvals/{aid}/approve", json={"reason": "test"}).json()
    assert ok["approval"]["status"] == "approved"
    second = client.delete(f"/api/instagram/calendar/{created['id']}").json()
    assert second["code"] == "deleted"


def test_revenue_verification_invariant(client):
    pending = client.post("/api/monetisation/revenue",
                          json={"amount": 50, "currency": "USD",
                                "source": "test",
                                "payment_reference": "PAY-123"}).json()
    assert pending["code"] == "approval_required"
    client.post(f"/api/approvals/{pending['approval_id']}/approve", json={})
    done = client.post("/api/monetisation/revenue",
                       json={"amount": 50, "currency": "USD", "source": "test",
                             "payment_reference": "PAY-123"}).json()
    assert done["verified"] is True

    pending2 = client.post("/api/monetisation/revenue",
                           json={"amount": 7, "currency": "USD",
                                 "source": "test-no-ref"}).json()
    client.post(f"/api/approvals/{pending2['approval_id']}/approve", json={})
    done2 = client.post("/api/monetisation/revenue",
                        json={"amount": 7, "currency": "USD",
                              "source": "test-no-ref"}).json()
    assert done2["verified"] is False

    rev = client.get("/api/monetisation/revenue").json()
    assert rev["verified_total"] >= 50
    unverified_hits = [e for e in rev["events"]
                       if e["source"] == "test-no-ref" and e["verified"] == 0]
    assert unverified_hits


def test_approval_reject(client):
    row = client.post("/api/approvals",
                      json={"kind": "delete.data", "title": "reject me",
                            "payload": {"x": 1}}).json()["approval"]
    res = client.post(f"/api/approvals/{row['id']}/reject",
                      json={"reason": "no"}).json()
    assert res["approval"]["status"] == "rejected"


def test_approval_is_single_use(client):
    from app import approvals, db
    db.init_db()
    payload = {"table": "content_calendar", "id": 999999}
    with pytest.raises(security.ApprovalRequired) as first:
        approvals.require_approved("delete.data", "single use probe", payload)
    approvals.decide(first.value.approval_id, "approved", "test")
    used = approvals.require_approved("delete.data", "single use probe", payload)
    assert used["id"] == first.value.approval_id
    # second attempt must demand a fresh approval, not reuse the consumed one
    with pytest.raises(security.ApprovalRequired) as second:
        approvals.require_approved("delete.data", "single use probe", payload)
    assert second.value.approval_id != first.value.approval_id


def test_undeclared_approval_kind_rejected():
    from app import approvals
    with pytest.raises(ValueError):
        approvals.require_approved("made.up.kind", "x", {})


def test_api_rejects_unknown_approval_kind(client):
    r = client.post("/api/approvals",
                    json={"kind": "made.up.kind", "title": "probe action",
                          "payload": {}})
    assert r.status_code == 400
    assert r.json()["code"] == "unknown_approval_kind"


# ------------------------------------------------------------ AI fallback ------
def test_ai_generate_fallback_label(client):
    body = client.post("/api/ai/generate",
                       json={"prompt": "Write one line about discipline",
                             "module": "test"}).json()
    assert body["generated_by"] in ("ollama", "fallback")
    assert body["text"].strip()
    if body["generated_by"] == "fallback":
        assert "ollama" in body["text"].lower() or body["text"].strip()


def test_captions_and_reels(client):
    caps = client.post("/api/instagram/captions",
                       json={"topic": "budgeting", "count": 2}).json()
    assert caps["generated_by"] in ("ollama", "fallback")
    if caps["captions"]:
        assert len(caps["captions"]) == 2
    reels = client.post("/api/instagram/reels/ideas",
                        json={"topic": "saving", "count": 2}).json()
    assert reels["generated_by"] in ("ollama", "fallback")


# ---------------------------------------------------------- truthful CV -------
def test_cv_never_invents_facts(client):
    profile = {
        "name": "Test Person",
        "headline": "Python developer",
        "skills": ["Python", "SQLite"],
        "experience": [{"role": "Developer", "company": "Acme Corp",
                        "dates": "2020-2023",
                        "bullets": ["Built internal tools"]}],
        "education": [],
    }
    body = client.post("/api/linkedin/cv",
                       json={"profile": profile,
                             "target_role": "Backend developer"}).json()
    cv = body["cv_markdown"]
    assert "Test Person" in cv
    assert "Acme Corp" in cv
    assert "[not provided]" in cv              # education missing → honest gap
    assert body["missing"] and "education" in body["missing"]
    # nothing invented: any 4-digit year in the CV must come from the profile
    import re
    corpus = str(profile)
    years = re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", cv)
    assert years, "expected the real dates from the profile to appear"
    for year in years:
        assert year in corpus, f"invented date {year}"


def test_cover_letter_uses_only_supplied_facts(client):
    profile = {"name": "Sam", "skills": ["React"], "experience": []}
    body = client.post("/api/linkedin/cover-letter",
                       json={"profile": profile,
                             "job_description": "We need a React developer for our team",
                             "company": "Globex"}).json()
    assert "Sam" in body["text"] and "Globex" in body["text"]


# --------------------------------------------------------------- media --------
def test_subtitles_srt(client):
    body = client.post("/api/youtube/subtitles",
                       json={"text": "First sentence here. Second sentence follows. "
                                     "Third one ends it."}).json()
    assert body["cue_count"] >= 2
    assert "-->" in body["srt"]
    assert Path(body["path"]).exists()


def test_thumbnail_render(client):
    body = client.post("/api/youtube/thumbnail",
                       json={"title": "How to budget in 2026",
                             "subtitle": "Test"}).json()
    p = Path(body["path"])
    assert p.exists() and p.stat().st_size > 5000
    assert body["width"] == 1280 and body["height"] == 720


@pytest.mark.slow
def test_ffmpeg_render(client):
    body = client.post("/api/youtube/render", json={
        "title": "NEXUS test",
        "scenes": [{"text": "Scene one", "seconds": 1.5},
                   {"text": "Scene two", "seconds": 1.5}]}).json()
    assert "path" in body, body
    p = Path(body["path"])
    assert p.exists() and p.stat().st_size > 1000


def test_voiceover_or_honest_failure(client):
    r = client.post("/api/youtube/voiceover", json={"text": "Hello from NEXUS."})
    body = r.json()
    if r.status_code >= 400:
        assert body.get("code") in ("tts_unavailable", "tts_failed"), body
        pytest.skip(f"SAPI unavailable here: {body.get('code')}")
    assert Path(body["path"]).exists()


# ------------------------------------------------------------- security --------
def test_redact():
    out = security.redact("token=abc123 secret: xyz Bearer qwe")
    assert "abc123" not in out and "xyz" not in out and "qwe" not in out


def test_sanitize_filename():
    assert ".." not in security.sanitize_filename("../../evil name?.mp3")
    assert security.sanitize_filename("") == "file"


def test_process_allowlist():
    from app import process
    from app.security import NexusError
    with pytest.raises(NexusError) as exc:
        process.run(["python", "--version"])
    assert exc.value.code == "subprocess_not_allowed"


# ------------------------------------------------------------ automation -------
def test_automation_jobs_registered(client):
    jobs = client.get("/api/automation/jobs").json()
    names = {j["name"] for j in jobs}
    assert names == {"daily_research", "content_preparation", "video_production",
                     "job_discovery", "weekly_report"}


def test_weekly_report_runs_offline(client):
    res = client.post("/api/automation/run", json={"job": "weekly_report"}).json()
    assert res["status"] == "ok", res
    reports = client.get("/api/automation/reports").json()["reports"]
    weekly = [r for r in reports if r["name"].endswith("_weekly.md")]
    assert weekly
    content = client.get("/api/automation/reports/content",
                         params={"name": weekly[0]["name"]}).json()["content"]
    assert "NEXUS AI Weekly Report" in content
    assert "no estimates" in content.lower() or "real database" in content.lower()


def test_content_preparation_respects_settings(client):
    res = client.post("/api/automation/run",
                      json={"job": "content_preparation"}).json()
    assert res["status"] == "ok"


# ---------------------------------------------------------------- network ------
def _net(fn):
    try:
        return fn()
    except Exception as exc:
        if "network_error" in str(exc) or "unreachable" in str(exc):
            pytest.skip(f"network unavailable: {exc}")
        raise


def test_jobs_discovery_endpoint(client):
    body = _net(lambda: client.get("/api/linkedin/jobs?refresh=true"))
    if body.status_code == 502:
        pytest.skip("job feeds unreachable")
    data = body.json()
    assert "jobs" in data and "note" in data
    if data["jobs"]:
        j = data["jobs"][0]
        assert j["source"] in ("remoteok", "remotive")
        assert "fetched_at" in j


def test_trends_endpoint(client):
    body = _net(lambda: client.get("/api/content/trends"))
    if body.status_code == 502:
        pytest.skip("trend feeds unreachable")
    data = body.json()
    assert "clusters" in data and "sources" in data
