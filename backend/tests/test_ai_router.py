"""AI router tests — provider selection, failover, cooldown, Ollama, honesty.

All network calls are monkeypatched; nothing here touches a real provider or consumes
quota. The router must never claim a provider succeeded when it did not.
"""
import httpx
import pytest

from app import ai_router, config, db


@pytest.fixture(autouse=True)
def clean_state():
    db.init_db()
    db.execute("DELETE FROM ai_provider_state")
    db.set_setting("ai_provider_order", "")
    db.set_setting("ai_model_override", "{}")
    yield
    db.execute("DELETE FROM ai_provider_state")
    db.set_setting("ai_provider_order", "")
    db.set_setting("ai_model_override", "{}")


def _no_keys(monkeypatch):
    monkeypatch.setattr(ai_router, "_key", lambda provider: "")


def _ollama_off(monkeypatch):
    monkeypatch.setattr(ai_router.ollama_client, "health",
                        lambda: {"available": False, "models": [], "sizes_gb": {},
                                 "url": "http://127.0.0.1:11434"})


def _fake_response(status: int, payload: dict | None = None):
    return httpx.Response(status, json=payload or {},
                          request=httpx.Request("POST", "http://test"))


# --------------------------------------------------------------- ordering ---
def test_default_order_contains_local_and_fallback():
    order = ai_router.get_order()
    assert order[-1] == "fallback"
    assert "ollama" in order
    assert order.index("ollama") < order.index("fallback")


def test_set_order_appends_missing_and_keeps_fallback_last():
    order = ai_router.set_order(["groq", "ollama"])
    assert order[:2] == ["groq", "ollama"]
    assert order[-1] == "fallback"
    assert "deepseek" in order


def test_unknown_provider_in_order_is_dropped():
    order = ai_router.set_order(["not_a_provider", "ollama"])
    assert "not_a_provider" not in order
    assert order[0] == "ollama"


# ------------------------------------------------------- no provider at all ---
def test_no_provider_uses_labelled_fallback(monkeypatch):
    _no_keys(monkeypatch)
    _ollama_off(monkeypatch)
    out = ai_router.generate("hello", fallback=lambda: "templated")
    assert out["text"] == "templated"
    assert out["generated_by"] == "fallback"
    assert out["fallback"] is True
    assert out["provider_label"] == "Deterministic templates"
    assert out["model"] is None
    assert out["ts"]


def test_no_provider_and_no_fallback_reports_no_output(monkeypatch):
    _no_keys(monkeypatch)
    _ollama_off(monkeypatch)
    out = ai_router.generate("hello")
    assert out["text"] == ""
    assert out["status"] == "no_fallback"
    assert out["generated_by"] == "fallback"


# --------------------------------------------------------- quota failover ----
def test_429_cools_provider_and_fails_over(monkeypatch):
    _no_keys(monkeypatch)
    _ollama_off(monkeypatch)
    monkeypatch.setattr(ai_router, "_key",
                        lambda p: "k" if p == "groq" else "")
    calls = {"n": 0}

    def fake_post(*a, **kw):
        calls["n"] += 1
        return _fake_response(429)

    monkeypatch.setattr(ai_router.httpx, "post", fake_post)
    out = ai_router.generate("hi", fallback=lambda: "fb")
    assert out["generated_by"] == "fallback"
    assert calls["n"] == 1  # quota errors are not retried
    st = ai_router.state("groq")
    assert st["last_error_class"] == "quota"
    assert st["cooling_down"] is True
    assert st["cooldown_remaining_s"] > 0


def test_cooled_provider_is_skipped_on_next_call(monkeypatch):
    _no_keys(monkeypatch)
    _ollama_off(monkeypatch)
    monkeypatch.setattr(ai_router, "_key",
                        lambda p: "k" if p == "groq" else "")
    calls = {"n": 0}

    def fake_post(*a, **kw):
        calls["n"] += 1
        return _fake_response(429)

    monkeypatch.setattr(ai_router.httpx, "post", fake_post)
    ai_router.generate("hi", fallback=lambda: "fb")
    calls["n"] = 0
    out = ai_router.generate("hi again", fallback=lambda: "fb")
    assert calls["n"] == 0  # cooled down: never retried
    assert any(a.get("skipped") == "cooling down" for a in out["attempts"])


def test_quota_failover_uses_next_healthy_provider(monkeypatch):
    _no_keys(monkeypatch)
    _ollama_off(monkeypatch)
    monkeypatch.setattr(ai_router, "_key",
                        lambda p: "k" if p in ("groq", "openrouter") else "")

    def fake_post(url, *a, **kw):
        if "groq" in url:
            return _fake_response(429)
        return _fake_response(200, {"choices": [{"message": {"content": "from or"}}],
                                    "usage": {"prompt_tokens": 3,
                                              "completion_tokens": 4}})

    monkeypatch.setattr(ai_router.httpx, "post", fake_post)
    out = ai_router.generate("hi", fallback=lambda: "fb")
    assert out["generated_by"] == "openrouter"
    assert out["text"] == "from or"
    assert out["model"]
    assert out["tokens_in"] == 3 and out["tokens_out"] == 4
    assert out["fallback"] is False


# ------------------------------------------------------- auth / not found ----
def test_auth_failure_is_classified_and_cooled(monkeypatch):
    _no_keys(monkeypatch)
    _ollama_off(monkeypatch)
    monkeypatch.setattr(ai_router, "_key",
                        lambda p: "k" if p == "deepseek" else "")
    monkeypatch.setattr(ai_router.httpx, "post",
                        lambda *a, **kw: _fake_response(401))
    ai_router.generate("hi", fallback=lambda: "fb")
    st = ai_router.state("deepseek")
    assert st["last_error_class"] == "auth"
    assert st["cooling_down"] is True


def test_model_not_found_is_classified(monkeypatch):
    _no_keys(monkeypatch)
    _ollama_off(monkeypatch)
    monkeypatch.setattr(ai_router, "_key",
                        lambda p: "k" if p == "groq" else "")
    monkeypatch.setattr(ai_router.httpx, "post",
                        lambda *a, **kw: _fake_response(404))
    ai_router.generate("hi", fallback=lambda: "fb")
    assert ai_router.state("groq")["last_error_class"] == "not_found"


# --------------------------------------------------------------- timeouts ---
def test_timeout_fails_over_after_retries(monkeypatch):
    _no_keys(monkeypatch)
    _ollama_off(monkeypatch)
    monkeypatch.setattr(ai_router, "_key",
                        lambda p: "k" if p == "groq" else "")
    calls = {"n": 0}

    def fake_post(*a, **kw):
        calls["n"] += 1
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(ai_router.httpx, "post", fake_post)
    monkeypatch.setattr(ai_router.config, "AI_BACKOFF", 0)
    out = ai_router.generate("hi", fallback=lambda: "fb")
    assert out["generated_by"] == "fallback"
    assert calls["n"] == config.AI_RETRIES + 1  # transient errors do retry
    assert ai_router.state("groq")["last_error_class"] == "network"


# ---------------------------------------------------------------- ollama ----
def test_ollama_selected_when_model_installed(monkeypatch):
    _no_keys(monkeypatch)
    monkeypatch.setattr(ai_router.ollama_client, "health", lambda: {
        "available": True, "models": ["qwen2.5-coder:3b", "gemma3:1b"],
        "sizes_gb": {"qwen2.5-coder:3b": 1.9, "gemma3:1b": 0.8},
        "url": "http://127.0.0.1:11434"})
    monkeypatch.setattr(ai_router, "_ollama_call",
                        lambda model, *a, **kw: {"text": "local answer",
                                                 "tokens_in": 5, "tokens_out": 9})
    out = ai_router.generate("hi", fallback=lambda: "fb")
    assert out["generated_by"] == "ollama"
    assert out["model"] == "qwen2.5-coder:3b"
    assert out["text"] == "local answer"
    assert out["fallback"] is False


def test_oversized_local_model_is_never_selected(monkeypatch):
    _no_keys(monkeypatch)
    monkeypatch.setattr(ai_router.ollama_client, "health", lambda: {
        "available": True, "models": ["orcarouter/Qwen3.8-27B-Uncensored:latest"],
        "sizes_gb": {"orcarouter/Qwen3.8-27B-Uncensored:latest": 17.0},
        "url": "http://127.0.0.1:11434"})
    monkeypatch.setattr(ai_router, "_ollama_call",
                        lambda *a, **kw: {"text": "should not run"})
    out = ai_router.generate("hi", fallback=lambda: "fb")
    assert out["generated_by"] == "fallback"
    assert any(a.get("skipped") == "no usable model" for a in out["attempts"])


def test_ollama_server_down_is_skipped_not_failed(monkeypatch):
    _no_keys(monkeypatch)
    _ollama_off(monkeypatch)
    out = ai_router.generate("hi", fallback=lambda: "fb")
    assert out["generated_by"] == "fallback"
    assert any("server down" in (a.get("skipped") or "") for a in out["attempts"])


# ------------------------------------------------------------- redaction ----
def test_stored_errors_are_redacted(monkeypatch):
    _no_keys(monkeypatch)
    _ollama_off(monkeypatch)
    monkeypatch.setattr(ai_router, "_key",
                        lambda p: "k" if p == "groq" else "")

    class Boom(Exception):
        pass

    monkeypatch.setattr(ai_router, "httpx", type("X", (), {"post": staticmethod(
        lambda *a, **kw: (_ for _ in ()).throw(
            Boom("failed with token=sk-abcdef123456"))),
        "TimeoutException": httpx.TimeoutException,
        "HTTPStatusError": httpx.HTTPStatusError,
        "ConnectError": httpx.ConnectError,
        "NetworkError": httpx.NetworkError,
        "Response": httpx.Response,
        "Request": httpx.Request,
        "get": httpx.get,
        "stream": httpx.stream}))
    ai_router.generate("hi", fallback=lambda: "fb")
    err = ai_router.state("groq")["last_error"] or ""
    assert "sk-abcdef123456" not in err
    assert "***" in err


# ---------------------------------------------------------------- metadata ----
def test_every_result_has_truthful_metadata(monkeypatch):
    _no_keys(monkeypatch)
    _ollama_off(monkeypatch)
    out = ai_router.generate("hi", fallback=lambda: "fb")
    for key in ("text", "generated_by", "provider", "provider_label", "model",
                "fallback", "latency_ms", "status", "ts", "attempts"):
        assert key in out
    assert out["generated_by"] == out["provider"]
    assert out["fallback"] == (out["provider"] == "fallback")


def test_ai_calls_are_logged_with_real_provider(monkeypatch):
    _no_keys(monkeypatch)
    _ollama_off(monkeypatch)
    monkeypatch.setattr(ai_router, "_key",
                        lambda p: "k" if p == "groq" else "")
    monkeypatch.setattr(ai_router.httpx, "post", lambda *a, **kw: _fake_response(
        200, {"choices": [{"message": {"content": "ok"}}], "usage": {}}))
    ai_router.generate("hi", module="unit.test", fallback=lambda: "fb")
    row = db.one("SELECT * FROM ai_calls WHERE module='unit.test'")
    assert row is not None
    assert row["generated_by"] == "groq"


# ---------------------------------------------------------------- status ----
def test_status_lists_every_provider_with_truthful_flags(monkeypatch):
    _no_keys(monkeypatch)
    _ollama_off(monkeypatch)
    st = ai_router.status()
    names = [p["name"] for p in st["providers"]]
    assert names == ai_router.get_order()
    assert st["fallback_ready"] is True
    assert st["active"] is None  # nothing configured and Ollama is down
    assert st["active_label"] == "Deterministic templates"
    for p in st["providers"]:
        assert "configured" in p and "cooling_down" in p


def test_test_all_does_not_hit_generation_endpoints(monkeypatch):
    _no_keys(monkeypatch)
    _ollama_off(monkeypatch)

    def boom(*a, **kw):
        raise AssertionError("generation endpoint must not be called")

    monkeypatch.setattr(ai_router.httpx, "post", boom)
    res = ai_router.test_all()
    assert res["results"]
    assert all("provider" in r and "ok" in r for r in res["results"])
