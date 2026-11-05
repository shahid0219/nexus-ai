"""Regression tests for the JSON-shadowing fallback bug (found 2026-11-05).

The four Instagram handlers and the content audience handler imported `json`
*inside* the function, after the fallback lambda that used it. Python therefore
treated `json` as a local name for the whole function, and every fallback raised
`NameError: cannot access local variable 'json'`. The endpoint still returned
data through a second code path, so the HTTP status looked healthy while the AI
call log recorded `fallback_error:NameError`.

These tests pin the behaviour: with no provider available, each handler must
record a clean `fallback` status and the fallback content must actually run.
"""
import pytest

from app import db
from app.modules import content, instagram


@pytest.fixture()
def offline_ai(monkeypatch):
    """Force the router into the deterministic fallback path."""
    import app.ai_router as ar
    monkeypatch.setattr(ar.ollama_client, "health", lambda: {
        "available": False, "models": [], "sizes_gb": {},
        "url": "http://127.0.0.1:11434"})
    db.init_db()
    db.execute("DELETE FROM ai_calls")
    yield
    db.execute("DELETE FROM ai_calls")


def _status_for(module: str) -> str:
    row = db.one("SELECT status FROM ai_calls WHERE module=? ORDER BY id DESC LIMIT 1",
                 (module,))
    assert row is not None, f"no ai_calls row logged for {module}"
    return row["status"]


def test_instagram_profile_fallback_is_not_a_name_error(offline_ai):
    out = instagram.profile_analyze(
        instagram.AnalyzeIn(profile_text="I build local-first developer tools daily"))
    assert out["generated_by"] == "fallback"
    assert _status_for("instagram.profile") == "fallback"


def test_instagram_niche_fallback_is_not_a_name_error(offline_ai):
    out = instagram.niche_research(instagram.NicheIn(niche="devtools"))
    assert out["generated_by"] == "fallback"
    assert out["result"]["niche"] == "devtools"
    assert _status_for("instagram.niche") == "fallback"


def test_instagram_reels_fallback_is_not_a_name_error(offline_ai):
    out = instagram.reels_ideas(instagram.ReelsIn(topic="terminal workflow", count=2))
    assert out["generated_by"] == "fallback"
    assert len(out["ideas"]) == 2
    assert _status_for("instagram.reels") == "fallback"


def test_instagram_captions_fallback_is_not_a_name_error(offline_ai):
    out = instagram.captions(instagram.CaptionsIn(topic="terminal workflow", count=2))
    assert out["generated_by"] == "fallback"
    assert len(out["captions"]) == 2
    assert _status_for("instagram.captions") == "fallback"


def test_content_audience_fallback_is_not_a_name_error(offline_ai):
    out = content.audience(content.AudienceIn(niche="devtools"))
    assert out["generated_by"] == "fallback"
    assert out["result"]["personas"]
    assert _status_for("content.audience") == "fallback"


def test_no_handler_logs_a_fallback_error(offline_ai):
    instagram.profile_analyze(
        instagram.AnalyzeIn(profile_text="local-first developer writing tools"))
    instagram.niche_research(instagram.NicheIn(niche="devtools"))
    instagram.reels_ideas(instagram.ReelsIn(topic="terminal workflow", count=1))
    instagram.captions(instagram.CaptionsIn(topic="terminal workflow", count=1))
    content.audience(content.AudienceIn(niche="devtools"))

    bad = db.query("SELECT module, status FROM ai_calls "
                   "WHERE status LIKE 'fallback_error%'")
    assert bad == [], f"fallback raised: {bad}"
