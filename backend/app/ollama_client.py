"""Local AI client — Ollama with a deterministic, labelled offline fallback.

Rules: 4GB VRAM policy (small models, one request at a time, token cap), no code
execution tools ever, every call logged in ai_calls with generated_by in
{ollama, fallback}. The fallback is honest: it is real deterministic content, never
presented as a model response.
"""
import threading
import time

import httpx

from . import activity, config, db
from .security import now_iso

_ai_lock = threading.Lock()


def health() -> dict:
    try:
        r = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=2.0)
        if r.status_code == 200:
            raw = r.json().get("models", [])
            models = [m.get("name", "") for m in raw]
            sizes = {}
            for m in raw:
                name = m.get("name", "")
                if name:
                    sizes[name] = round((m.get("size") or 0) / 2**30, 1)
            return {"available": True, "models": models, "sizes_gb": sizes,
                    "url": config.OLLAMA_URL}
    except Exception:
        pass
    return {"available": False, "models": [], "sizes_gb": {}, "url": config.OLLAMA_URL}


def _fits(name: str, sizes: dict[str, float]) -> bool:
    size = sizes.get(name)
    return size is None or size <= config.AI_MAX_MODEL_GB


def _pick_model(available_models: list[str],
                sizes: dict[str, float] | None = None) -> str | None:
    """Pick the best model that actually fits the 4GB-VRAM policy."""
    sizes = sizes if sizes is not None else health().get("sizes_gb", {})
    fitting = [m for m in available_models if _fits(m, sizes)]
    if not fitting:
        return None  # never load something that cannot fit
    lowered = [m.lower() for m in fitting]
    for wanted in config.PREFERRED_MODELS:
        base = wanted.split(":")[0]
        for i, have in enumerate(lowered):
            if have == wanted.lower() or have.startswith(base + ":"):
                return fitting[i]
    return min(fitting, key=lambda m: sizes.get(m, 999))


def generate(prompt: str, module: str, system: str | None = None,
             max_tokens: int | None = None, fallback=None) -> dict:
    """Generate text. Tries Ollama first; falls back to `fallback()` if provided.

    Returns {text, generated_by, model, latency_ms}. Raises nothing on AI failure —
    callers always receive usable text or an explicit error dict.
    """
    started = time.time()
    max_tokens = min(max_tokens or config.AI_MAX_TOKENS, config.AI_MAX_TOKENS)
    h = health()
    model = None
    text = None
    status = "ok"

    if h["available"]:
        model = _pick_model(h["models"], h.get("sizes_gb"))
        if model:
            try:
                with _ai_lock:  # one request at a time on 4GB VRAM
                    r = httpx.post(
                        f"{config.OLLAMA_URL}/api/generate",
                        json={
                            "model": model,
                            "prompt": prompt,
                            "system": system or "",
                            "stream": False,
                            "options": {
                                "num_predict": max_tokens,
                                "temperature": 0.7,
                                "num_ctx": 2048,
                            },
                        },
                        timeout=config.AI_TIMEOUT,
                    )
                if r.status_code == 200:
                    text = r.json().get("response", "").strip() or None
                else:
                    status = f"ollama_http_{r.status_code}"
            except Exception as exc:
                status = f"ollama_error:{exc.__class__.__name__}"

    generated_by = "ollama"
    if text is None:
        generated_by = "fallback"
        if fallback is not None:
            try:
                text = fallback()
            except Exception as exc:
                status = f"fallback_error:{exc.__class__.__name__}"
                text = ""
        else:
            text = ""
            status = "no_fallback"

    latency = int((time.time() - started) * 1000)
    db.execute(
        "INSERT INTO ai_calls(ts,module,model,generated_by,latency_ms,prompt_chars,status)"
        " VALUES(?,?,?,?,?,?,?)",
        (now_iso(), module, model, generated_by, latency, len(prompt), status),
    )
    if generated_by == "fallback":
        activity.info("ai", f"offline fallback used ({module})", {"status": status})
    return {
        "text": text,
        "generated_by": generated_by,
        "model": model,
        "latency_ms": latency,
        "status": status,
    }


def structured(prompt: str, module: str, fallback_obj, system: str | None = None,
               max_tokens: int | None = None) -> dict:
    """Like generate() but the fallback returns a dict/object directly.

    Used when a deterministic structured answer is better than free text. The Ollama
    path still returns free text in `text`; callers that need structure should prefer
    their own deterministic builders and only use generate() for creative prose.
    """
    started = time.time()
    h = health()
    model = None
    text = None
    status = "ok"
    if h["available"]:
        model = _pick_model(h["models"], h.get("sizes_gb"))
        if model:
            try:
                with _ai_lock:
                    r = httpx.post(
                        f"{config.OLLAMA_URL}/api/generate",
                        json={"model": model, "prompt": prompt, "system": system or "",
                              "stream": False,
                              "options": {"num_predict": min(max_tokens or config.AI_MAX_TOKENS,
                                                             config.AI_MAX_TOKENS),
                                          "temperature": 0.7, "num_ctx": 2048}},
                        timeout=config.AI_TIMEOUT,
                    )
                if r.status_code == 200:
                    text = r.json().get("response", "").strip() or None
                else:
                    status = f"ollama_http_{r.status_code}"
            except Exception as exc:
                status = f"ollama_error:{exc.__class__.__name__}"
    latency = int((time.time() - started) * 1000)
    generated_by = "ollama" if text is not None else "fallback"
    db.execute(
        "INSERT INTO ai_calls(ts,module,model,generated_by,latency_ms,prompt_chars,status)"
        " VALUES(?,?,?,?,?,?,?)",
        (now_iso(), module, model, generated_by, latency, len(prompt), status))
    return {"text": text, "structured": fallback_obj, "generated_by": generated_by,
            "model": model, "latency_ms": latency, "status": status}
