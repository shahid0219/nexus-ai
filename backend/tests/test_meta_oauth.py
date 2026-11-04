"""Integration tests for the Meta/Instagram OAuth flow and account verification.

All HTTP is stubbed — no real Meta calls, no credentials, no posting.
"""
import httpx
import pytest

from app import credentials, db
from app.modules import instagram


@pytest.fixture(autouse=True)
def clean():
    db.init_db()
    credentials.delete_provider("meta")
    yield
    credentials.delete_provider("meta")


def _resp(status=200, payload=None):
    return httpx.Response(status, json=payload or {},
                          request=httpx.Request("GET", "http://test"))


def test_status_reports_awaiting_configuration_when_empty():
    st = instagram.oauth_status()
    assert st["status"] == "awaiting_configuration"
    assert st["app_configured"] is False
    assert st["authorized"] is False


def test_configure_stores_app_secret_without_exposing_it():
    out = instagram.oauth_configure(instagram.MetaAppIn(
        app_id="1234567890", app_secret="supersecretvalue", ig_user_id=None))
    assert out["code"] == "stored"
    raw = credentials.get_provider("meta")
    assert raw["app_secret"] == "supersecretvalue"
    view = credentials.public_view("meta")
    assert "supersecretvalue" not in str(view)
    assert view["has_client"] is True


def test_status_after_configure_is_awaiting_authentication():
    instagram.oauth_configure(instagram.MetaAppIn(
        app_id="1234567890", app_secret="supersecretvalue"))
    st = instagram.oauth_status()
    assert st["app_configured"] is True
    assert st["authorized"] is False
    assert st["status"] == "awaiting_authentication"


def test_start_requires_configured_app():
    from app.security import NexusError
    with pytest.raises(NexusError) as exc:
        instagram.oauth_start()
    assert exc.value.code == "awaiting_configuration"


def test_start_returns_official_facebook_auth_url():
    instagram.oauth_configure(instagram.MetaAppIn(
        app_id="1234567890", app_secret="supersecretvalue"))
    out = instagram.oauth_start()
    assert out["auth_url"].startswith("https://www.facebook.com/v21.0/dialog/oauth")
    assert "client_id=1234567890" in out["auth_url"]
    assert "state=" in out["auth_url"]
    assert "instagram_content_publish" in out["auth_url"]
    assert "eligibility" in out


def test_callback_stores_long_lived_token(monkeypatch):
    instagram.oauth_configure(instagram.MetaAppIn(
        app_id="1234567890", app_secret="supersecretvalue"))

    def fake_get(url, params=None, timeout=None, **kw):
        if "oauth/access_token" in url and params.get("grant_type") == "fb_exchange_token":
            return _resp(200, {"access_token": "LONG_LIVED", "expires_in": 5184000})
        if "/me/permissions" in url:
            return _resp(200, {"data": [
                {"permission": "instagram_basic", "status": "granted"},
                {"permission": "instagram_content_publish", "status": "granted"}]})
        if "/me/accounts" in url:
            return _resp(200, {"data": [{"name": "My Page",
                                         "instagram_business_account": {"id": "1789"}}]})
        if url.endswith("/me"):
            return _resp(200, {"id": "1", "name": "Shahid"})
        return _resp(200, {"access_token": "SHORT", "expires_in": 3600})

    monkeypatch.setattr(instagram.httpx, "get", fake_get)
    out = instagram.oauth_callback(instagram.MetaCallbackIn(code="abc123"))
    assert out["code"] == "connected"
    stored = credentials.get_provider("meta")
    assert stored["access_token"] == "LONG_LIVED"
    assert stored["ig_user_id"] == "1789"
    assert out["identity"]["ok"] is True
    assert out["identity"]["facebook_user"] == "Shahid"


def test_callback_surfaces_provider_error(monkeypatch):
    from app.security import NexusError
    instagram.oauth_configure(instagram.MetaAppIn(
        app_id="1234567890", app_secret="supersecretvalue"))
    monkeypatch.setattr(instagram.httpx, "get", lambda *a, **kw: _resp(
        400, {"error": {"message": "Invalid verification code"}}))
    with pytest.raises(NexusError) as exc:
        instagram.oauth_callback(instagram.MetaCallbackIn(code="badcode"))
    assert exc.value.code == "oauth_failed"


def test_verify_without_token_is_honest():
    out = instagram.oauth_verify()
    assert out["ok"] is False
    assert out["requires_auth"] is True


def test_verify_detects_missing_permissions(monkeypatch):
    credentials.set_provider("meta", {"access_token": "TOK"})
    monkeypatch.setattr(instagram.httpx, "get", lambda url, **kw: (
        _resp(200, {"data": [{"permission": "instagram_basic",
                              "status": "granted"}]})
        if "/me/permissions" in url else
        _resp(200, {"data": [{"name": "P",
                              "instagram_business_account": {"id": "1"}}]})
        if "/me/accounts" in url else
        _resp(200, {"id": "1", "name": "Shahid"})))
    out = instagram.oauth_verify()
    assert out["ok"] is False
    assert out["blocked_by_permission"] is True
    assert "instagram_content_publish" in out["missing_permissions"]


def test_verify_detects_missing_professional_account(monkeypatch):
    credentials.set_provider("meta", {"access_token": "TOK"})
    monkeypatch.setattr(instagram.httpx, "get", lambda url, **kw: (
        _resp(200, {"data": [
            {"permission": "instagram_basic", "status": "granted"},
            {"permission": "instagram_content_publish", "status": "granted"}]})
        if "/me/permissions" in url else
        _resp(200, {"data": []}) if "/me/accounts" in url else
        _resp(200, {"id": "1", "name": "Shahid"})))
    out = instagram.oauth_verify()
    assert out["ok"] is False
    assert "professional account" in out["reason"]


def test_analytics_never_invents_numbers_without_token():
    out = instagram.analytics()
    assert out["requires_auth"] is True
    assert "metrics" not in out


def test_publish_requires_auth_without_token():
    out = instagram.publish(instagram.PublishIn(caption="hello"))
    assert out["requires_auth"] is True
    assert "message" in out
