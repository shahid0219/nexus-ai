"""Real Ollama integration tests (not mocks).

These only run when a live Ollama server is reachable AND at least one installed
model fits the size policy. When they run, they exercise the actual HTTP path the
application uses, so a passing result means a model really generated text.

Skipping is explicit and honest: the skip reason names what is missing.
"""
import pytest

from app import config, db, ollama_client


def _live():
    try:
        h = ollama_client.health()
    except Exception:
        return None
    if not h.get("available"):
        return None
    fitting = [m for m in h.get("models", [])
               if ollama_client._fits(m, h.get("sizes_gb", {}))]
    if not fitting:
        return None
    return h


@pytest.fixture(scope="module")
def live():
    h = _live()
    if h is None:
        pytest.skip("no reachable Ollama with a model that fits the size policy")
    db.init_db()
    return h


def test_live_server_reports_installed_models(live):
    assert live["available"] is True
    assert live["models"], "Ollama reported no installed models"
    assert isinstance(live["sizes_gb"], dict)


def test_live_model_selection_respects_size_policy(live):
    picked = ollama_client._pick_model(live["models"], live.get("sizes_gb"))
    assert picked, "no model selected despite one being available"
    size = live["sizes_gb"].get(picked)
    if size is not None:
        assert size <= config.AI_MAX_MODEL_GB, (
            f"selected {picked} at {size} GB exceeds the "
            f"{config.AI_MAX_MODEL_GB} GB policy")


def test_live_generation_returns_real_text(live):
    model = ollama_client._pick_model(live["models"], live.get("sizes_gb"))
    result = ollama_client.generate(
        "Reply with exactly the word: LIVE_OK",
        module="test.live",
        max_tokens=16,
    )
    assert result["generated_by"] == "ollama", (
        f"expected a real model response, got {result['generated_by']} "
        f"(status={result['status']})")
    assert result["model"], "a real generation must name the model used"
    assert result["text"].strip(), "model returned empty text"
    assert result["latency_ms"] > 0
    assert model == result["model"] or result["model"] == model


def test_live_router_generation_uses_ollama(live):
    from app import ai_router
    out = ai_router.generate("Reply with exactly: ROUTER_OK",
                             module="test.router.live", max_tokens=16)
    assert out["generated_by"] == "ollama", out.get("status")
    assert out["provider"] == "ollama"
    assert out["model"]
    assert out["text"].strip()


def test_live_status_reflects_reality(live):
    from app import ai_router
    st = ai_router.status()
    assert st["active"] == "ollama"
    ollama = next(p for p in st["providers"] if p["name"] == "ollama")
    assert ollama["configured"] is True
    assert ollama["models"], "status must list installed models"
    assert st["ollama"]["available"] is True
    assert st["ollama"]["selected_model"]
    assert st["hint"] is None
