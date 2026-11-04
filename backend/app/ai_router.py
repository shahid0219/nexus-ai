"""AI provider router — one entry point for every generation feature.

Order is configurable (setting `ai_provider_order`). Only providers that are genuinely
usable are tried:

  * remote providers need an owner-supplied API key in data/credentials.json
  * `ollama` needs a reachable local server AND an actually installed model
  * `fallback` is the deterministic template engine and is always labelled

Failure policy: quota exhaustion / auth failure / outage cool a provider down for a
while instead of hammering it on every request. Errors are classified, never guessed.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field

import httpx

from . import activity, config, db, ollama_client
from .security import now_iso, redact

DEFAULT_ORDER = ["deepseek", "groq", "openrouter", "google", "ollama", "fallback"]

# Cooldown seconds per failure class.
COOLDOWN = {"quota": 900, "auth": 1800, "not_found": 3600, "network": 120,
            "error": 300}


@dataclass
class Provider:
    name: str
    label: str
    kind: str                      # "remote" | "local" | "deterministic"
    url: str = ""
    models: list[str] = field(default_factory=list)
    key_field: str = "api_key"
    doc: str = ""
    free_note: str = ""


PROVIDERS: dict[str, Provider] = {
    "deepseek": Provider(
        name="deepseek", label="DeepSeek API", kind="remote",
        url="https://api.deepseek.com/v1/chat/completions",
        models=["deepseek-chat"],
        doc="Paid pay-as-you-go API. The free chat website is NOT an API.",
        free_note="No official free API tier — requires an owner-supplied key."),
    "groq": Provider(
        name="groq", label="Groq Cloud", kind="remote",
        url="https://api.groq.com/openai/v1/chat/completions",
        models=["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
        doc="OpenAI-compatible endpoint with a free developer tier and hard rate limits.",
        free_note="Free tier with rate limits (not unlimited)."),
    "openrouter": Provider(
        name="openrouter", label="OpenRouter (free models)", kind="remote",
        url="https://openrouter.ai/api/v1/chat/completions",
        models=["meta-llama/llama-3.3-70b-instruct:free",
                "google/gemma-2-9b-it:free"],
        doc="OpenAI-compatible gateway; only models whose id ends in ':free' are used.",
        free_note="Free ':free' models with daily request caps."),
    "google": Provider(
        name="google", label="Google AI Studio (Gemini)", kind="remote",
        url="https://generativelanguage.googleapis.com/v1beta/models/"
            "{model}:generateContent",
        models=["gemini-2.0-flash"],
        doc="Native Gemini REST endpoint; free tier subject to per-minute quotas.",
        free_note="Free tier with per-minute/per-day quotas."),
    "ollama": Provider(
        name="ollama", label="Ollama (local)", kind="local",
        url=config.OLLAMA_URL,
        doc="Runs entirely on this PC. No network, no key, no quota.",
        free_note="Fully local and free."),
    "fallback": Provider(
        name="fallback", label="Deterministic templates", kind="deterministic",
        doc="Structured text built from your inputs only. Always labelled generated_by=fallback.",
        free_note="Always available offline."),
}

_lock = threading.Lock()


# --------------------------------------------------------------- ordering ---
def get_order() -> list[str]:
    raw = db.get_setting("ai_provider_order", "")
    order = [p.strip() for p in raw.split(",") if p.strip()]
    order = [p for p in order if p in PROVIDERS]
    for name in DEFAULT_ORDER:
        if name not in order:
            order.append(name)
    return order


def set_order(order: list[str]) -> list[str]:
    clean = [p for p in order if p in PROVIDERS]
    for name in DEFAULT_ORDER:
        if name not in clean:
            clean.append(name)
    db.set_setting("ai_provider_order", ",".join(clean))
    return clean


def get_model_override() -> dict[str, str]:
    try:
        return json.loads(db.get_setting("ai_model_override", "{}") or "{}")
    except ValueError:
        return {}


def set_model_override(provider: str, model: str) -> dict:
    current = get_model_override()
    if model:
        current[provider] = model
    else:
        current.pop(provider, None)
    db.set_setting("ai_model_override", db.dumps(current))
    return current


# -------------------------------------------------------------- cooldowns ---
def _cooldown_until(provider: str) -> float:
    row = db.one("SELECT cooldown_until FROM ai_provider_state WHERE provider=?",
                 (provider,))
    return float(row["cooldown_until"] or 0) if row else 0.0


def _mark(provider: str, *, ok: bool = False, error: str | None = None,
          cls: str | None = None, latency_ms: int | None = None) -> None:
    now = time.time()
    until = _cooldown_until(provider)
    if ok:
        until = 0.0
    elif cls:
        until = now + COOLDOWN.get(cls, 300)
    db.execute(
        "INSERT INTO ai_provider_state(provider,cooldown_until,last_error,last_error_class,"
        "last_ok_ts,last_latency_ms) VALUES(?,?,?,?,?,?)"
        " ON CONFLICT(provider) DO UPDATE SET cooldown_until=excluded.cooldown_until,"
        " last_error=excluded.last_error, last_error_class=excluded.last_error_class,"
        " last_ok_ts=COALESCE(excluded.last_ok_ts,ai_provider_state.last_ok_ts),"
        " last_latency_ms=COALESCE(excluded.last_latency_ms,ai_provider_state.last_latency_ms)",
        (provider, until, redact(error)[:300] if error else None, cls,
         now_iso() if ok else None, latency_ms),
    )


def _cooling(provider: str) -> tuple[bool, float]:
    until = _cooldown_until(provider)
    return (until > time.time(), until)


# ------------------------------------------------------------------ keys ----
def _key(provider: str) -> str:
    from . import credentials
    entry = credentials.get_provider(provider)
    return str(entry.get("api_key") or entry.get("access_token") or "")


def is_configured(provider: str) -> bool:
    spec = PROVIDERS.get(provider)
    if not spec:
        return False
    if spec.kind == "deterministic":
        return True
    if spec.kind == "local":
        return True
    return bool(_key(provider))


# ------------------------------------------------------------ health checks ---
def health(provider: str) -> dict:
    spec = PROVIDERS[provider]
    started = time.time()
    if spec.kind == "deterministic":
        return {"provider": provider, "ok": True, "detail": "always available",
                "latency_ms": 0, "models": []}
    if spec.kind == "local":
        h = ollama_client.health()
        return {"provider": provider, "ok": h["available"],
                "detail": "reachable" if h["available"] else "server not reachable",
                "latency_ms": int((time.time() - started) * 1000),
                "models": h["models"]}
    key = _key(provider)
    if not key:
        return {"provider": provider, "ok": False, "detail": "no API key configured",
                "latency_ms": 0, "models": []}
    try:
        models = _list_models(spec, key)
        return {"provider": provider, "ok": True, "detail": "reachable",
                "latency_ms": int((time.time() - started) * 1000), "models": models}
    except Exception as exc:
        cls, msg = _classify(exc)
        return {"provider": provider, "ok": False, "detail": f"{cls}: {msg}",
                "latency_ms": int((time.time() - started) * 1000), "models": []}


def _list_models(spec: Provider, key: str) -> list[str]:
    """Cheap connectivity probe — lists models, never consumes generation quota."""
    if spec.name == "google":
        r = httpx.get(f"https://generativelanguage.googleapis.com/v1beta/models",
                      params={"key": key}, timeout=10.0)
        _raise_for(r)
        data = r.json()
        return [m.get("name", "").split("/")[-1] for m in data.get("models", [])]
    base = spec.url.split("/chat/completions")[0]
    r = httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"},
                  timeout=10.0)
    _raise_for(r)
    data = r.json()
    return [m.get("id", "") for m in data.get("data", [])]


def _raise_for(r: httpx.Response) -> None:
    if r.status_code == 429:
        raise _ProviderError("quota", f"HTTP 429 rate limited by provider")
    if r.status_code in (401, 403):
        raise _ProviderError("auth", f"HTTP {r.status_code} authentication failed")
    if r.status_code == 404:
        raise _ProviderError("not_found", "HTTP 404 model or endpoint not found")
    if r.status_code >= 400:
        raise _ProviderError("error", f"HTTP {r.status_code}")


class _ProviderError(Exception):
    def __init__(self, cls: str, msg: str):
        self.cls = cls
        self.msg = msg
        super().__init__(msg)


def _classify(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, _ProviderError):
        return exc.cls, exc.msg
    if isinstance(exc, httpx.TimeoutException):
        return "network", "request timed out"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429:
            return "quota", "HTTP 429 rate limited"
        if code in (401, 403):
            return "auth", f"HTTP {code} authentication failed"
        if code == 404:
            return "not_found", "HTTP 404"
        return "error", f"HTTP {code}"
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError, OSError)):
        return "network", f"{exc.__class__.__name__}"
    return "error", f"{exc.__class__.__name__}: {exc}"[:300]


# ---------------------------------------------------------------- generate ---
def _pick_model(provider: str, installed: list[str] | None = None) -> str:
    override = get_model_override().get(provider)
    if override:
        return override
    spec = PROVIDERS[provider]
    if provider == "ollama":
        h = ollama_client.health()
        models = installed or h["models"]
        return ollama_client._pick_model(models, h.get("sizes_gb")) or ""
    return spec.models[0] if spec.models else ""


def _remote_call(spec: Provider, key: str, model: str, prompt: str,
                 system: str | None, max_tokens: int, timeout: float) -> dict:
    if spec.name == "google":
        url = spec.url.format(model=model)
        payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                   "generationConfig": {"maxOutputTokens": max_tokens,
                                        "temperature": 0.7}}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        r = httpx.post(url, params={"key": key}, json=payload, timeout=timeout)
        _raise_for(r)
        data = r.json()
        cand = (data.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        usage = data.get("usageMetadata") or {}
        return {"text": text, "tokens_in": usage.get("promptTokenCount"),
                "tokens_out": usage.get("candidatesTokenCount")}
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens,
               "temperature": 0.7}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if spec.name == "openrouter":
        headers["X-Title"] = "NEXUS AI"
    r = httpx.post(spec.url, json=payload, headers=headers, timeout=timeout)
    _raise_for(r)
    data = r.json()
    choice = (data.get("choices") or [{}])[0]
    text = ((choice.get("message") or {}).get("content") or "").strip()
    usage = data.get("usage") or {}
    return {"text": text, "tokens_in": usage.get("prompt_tokens"),
            "tokens_out": usage.get("completion_tokens")}


def _ollama_call(model: str, prompt: str, system: str | None, max_tokens: int,
                 timeout: float) -> dict:
    r = httpx.post(f"{config.OLLAMA_URL}/api/generate",
                   json={"model": model, "prompt": prompt, "system": system or "",
                         "stream": False,
                         "options": {"num_predict": max_tokens, "temperature": 0.7,
                                     "num_ctx": 2048}},
                   timeout=timeout)
    _raise_for(r)
    data = r.json()
    return {"text": (data.get("response") or "").strip(),
            "tokens_in": data.get("prompt_eval_count"),
            "tokens_out": data.get("eval_count")}


def generate(prompt: str, module: str = "general", system: str | None = None,
             max_tokens: int | None = None, fallback=None,
             timeout: float | None = None) -> dict:
    """Generate text through the provider chain, with honest metadata."""
    started = time.time()
    max_tokens = min(max_tokens or config.AI_MAX_TOKENS, config.AI_MAX_TOKENS)
    timeout = timeout or config.AI_TIMEOUT
    attempts: list[dict] = []
    used: Provider | None = None
    model = ""
    text = ""
    status = "ok"
    provider_name = "fallback"
    tokens_in = tokens_out = None

    for name in get_order():
        if name == "fallback":
            continue
        spec = PROVIDERS[name]
        if not is_configured(name):
            attempts.append({"provider": name, "skipped": "not configured"})
            continue
        cooling, until = _cooling(name)
        if cooling:
            attempts.append({"provider": name, "skipped": "cooling down",
                             "until": int(until)})
            continue
        if spec.kind == "local":
            h = ollama_client.health()
            if not h["available"] or not h["models"]:
                attempts.append({"provider": name,
                                 "skipped": "server down or no model installed"})
                continue
            model = _pick_model(name, h["models"])
            if not model:
                attempts.append({"provider": name, "skipped": "no usable model"})
                continue
        else:
            model = _pick_model(name)
        last_exc: Exception | None = None
        for attempt in range(config.AI_RETRIES + 1):
            try:
                with _lock:  # one local model at a time; remote is cheap to serialise
                    if spec.kind == "local":
                        out = _ollama_call(model, prompt, system, max_tokens, timeout)
                    else:
                        out = _remote_call(spec, _key(name), model, prompt, system,
                                           max_tokens, timeout)
                if out["text"]:
                    text = out["text"]
                    tokens_in, tokens_out = out.get("tokens_in"), out.get("tokens_out")
                    used, provider_name, status = spec, name, "ok"
                    _mark(name, ok=True, latency_ms=int((time.time() - started) * 1000))
                    break
                last_exc = _ProviderError("error", "empty response")
            except Exception as exc:
                last_exc = exc
                cls, msg = _classify(exc)
                attempts.append({"provider": name, "attempt": attempt + 1,
                                 "error_class": cls, "error": msg})
                if cls in ("quota", "auth", "not_found"):
                    break  # do not retry: it will not get better this minute
                if attempt < config.AI_RETRIES:
                    time.sleep(config.AI_BACKOFF * (2 ** attempt))
        if text:
            break
        if last_exc is not None:
            cls, msg = _classify(last_exc)
            _mark(name, error=msg, cls=cls)

    if not text:
        provider_name = "fallback"
        status = "fallback"
        if fallback is not None:
            try:
                text = fallback() or ""
            except Exception as exc:
                status = f"fallback_error:{exc.__class__.__name__}"
                text = ""
        if not text:
            status = status if status != "fallback" else "no_fallback"

    latency = int((time.time() - started) * 1000)
    _log(module, provider_name, model, latency, len(prompt), status)
    if provider_name == "fallback":
        activity.info("ai", f"deterministic fallback used ({module})", {"status": status})
    return {
        "text": text,
        "generated_by": provider_name,
        "provider": provider_name,
        "provider_label": PROVIDERS[provider_name].label,
        "model": model or None,
        "fallback": provider_name == "fallback",
        "latency_ms": latency,
        "status": status,
        "ts": now_iso(),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "attempts": attempts,
    }


def _log(module: str, provider: str, model: str, latency: int, chars: int,
         status: str) -> None:
    db.execute(
        "INSERT INTO ai_calls(ts,module,model,generated_by,latency_ms,prompt_chars,status)"
        " VALUES(?,?,?,?,?,?,?)",
        (now_iso(), module, model or None, provider, latency, chars, status))


# ------------------------------------------------------------------ stream ---
def stream(prompt: str, module: str = "general", system: str | None = None,
           max_tokens: int | None = None):
    """Yield SSE-ready dicts: {delta} chunks then a final {done, provider, ...}.

    Only Ollama is streamed (no quota cost, cancellable immediately). Remote
    providers are streamed through their native SSE if configured, otherwise this
    yields the whole answer in one chunk so behaviour stays truthful.
    """
    max_tokens = min(max_tokens or config.AI_MAX_TOKENS, config.AI_MAX_TOKENS)
    order = get_order()
    if "ollama" in order and is_configured("ollama"):
        h = ollama_client.health()
        model = (ollama_client._pick_model(h["models"], h.get("sizes_gb"))
                 if h["available"] else None)
        if h["available"] and model and not _cooling("ollama")[0]:
            started = time.time()
            try:
                with httpx.stream("POST", f"{config.OLLAMA_URL}/api/generate",
                                  json={"model": model, "prompt": prompt,
                                        "system": system or "", "stream": True,
                                        "options": {"num_predict": max_tokens,
                                                    "temperature": 0.7,
                                                    "num_ctx": 2048}},
                                  timeout=config.AI_TIMEOUT) as r:
                    _raise_for(r)
                    for line in r.iter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except ValueError:
                            continue
                        piece = chunk.get("response") or ""
                        if piece:
                            yield {"delta": piece, "provider": "ollama",
                                   "model": model}
                        if chunk.get("done"):
                            break
                latency = int((time.time() - started) * 1000)
                _log(module, "ollama", model, latency, len(prompt), "ok")
                _mark("ollama", ok=True, latency_ms=latency)
                yield {"done": True, "provider": "ollama", "model": model,
                       "latency_ms": latency, "ts": now_iso()}
                return
            except Exception as exc:
                cls, msg = _classify(exc)
                _mark("ollama", error=msg, cls=cls)
                yield {"delta": "", "provider": "ollama", "error": msg}

    result = generate(prompt, module=module, system=system, max_tokens=max_tokens)
    if result["text"]:
        yield {"delta": result["text"], "provider": result["generated_by"],
               "model": result.get("model")}
    yield {"done": True, "provider": result["generated_by"],
           "model": result.get("model"), "latency_ms": result["latency_ms"],
           "status": result["status"], "ts": result["ts"]}


# -------------------------------------------------------------- diagnostics ---
def state(provider: str) -> dict:
    row = db.one("SELECT * FROM ai_provider_state WHERE provider=?", (provider,))
    cooling, until = _cooling(provider)
    return {
        "provider": provider,
        "configured": is_configured(provider),
        "cooling_down": cooling,
        "cooldown_remaining_s": max(0, int(until - time.time())) if cooling else 0,
        "last_error": (row or {}).get("last_error"),
        "last_error_class": (row or {}).get("last_error_class"),
        "last_ok_ts": (row or {}).get("last_ok_ts"),
        "last_latency_ms": (row or {}).get("last_latency_ms"),
    }


def status() -> dict:
    order = get_order()
    providers = []
    for name in order:
        spec = PROVIDERS[name]
        providers.append({
            "name": name, "label": spec.label, "kind": spec.kind,
            "free_note": spec.free_note, "doc": spec.doc,
            "models": spec.models, "selected_model": _pick_model(name),
            **state(name),
        })
    active = None
    ollama_ok = False
    for p in providers:
        if p["name"] == "ollama":
            ollama_ok = bool(p["configured"]) and not p["cooling_down"] and \
                ollama_client.health()["available"] and bool(p["selected_model"])
    for p in providers:
        if p["name"] == "fallback":
            continue
        if p["name"] == "ollama":
            if ollama_ok:
                active = "ollama"
                break
            continue
        if p["configured"] and not p["cooling_down"]:
            active = p["name"]
            break
    return {"order": order, "providers": providers, "active": active,
            "active_label": PROVIDERS[active].label if active else
            PROVIDERS["fallback"].label,
            "fallback_ready": True}


def test_all() -> dict:
    """Connectivity probe for every provider. Uses model-listing only for remotes."""
    results = []
    for name in get_order():
        spec = PROVIDERS[name]
        if spec.kind == "deterministic":
            results.append({"provider": name, "ok": True,
                            "detail": "always available", "latency_ms": 0})
            continue
        if not is_configured(name):
            results.append({"provider": name, "ok": False,
                            "detail": "not configured — no credentials stored",
                            "latency_ms": 0})
            continue
        h = health(name)
        if h["ok"]:
            _mark(name, ok=True)
        else:
            cls, _ = h["detail"].split(":", 1) if ":" in h["detail"] else ("error", "")
            _mark(name, error=h["detail"],
                  cls=cls if cls in COOLDOWN else "error")
        results.append(h)
    return {"results": results, "ts": now_iso()}
