"""Credential store — secrets live only in data/credentials.json (gitignored).

The API never returns secret values, only presence/scopes/expiry (SECURITY.md §1).
"""
import json
import os

from . import config
from .security import now_iso

REQUIRED_KEYS = {
    "meta": ["access_token"],
    "google": ["client_id", "client_secret"],
    "github": [],
    "linkedin": [],
}


def _read() -> dict:
    if not config.CREDENTIALS_FILE.exists():
        return {}
    try:
        return json.loads(config.CREDENTIALS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write(data: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = config.CREDENTIALS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, config.CREDENTIALS_FILE)
    try:
        os.chmod(config.CREDENTIALS_FILE, 0o600)
    except OSError:
        pass  # Windows ACLs are inherited; file is gitignored regardless


def get_provider(provider: str) -> dict:
    return _read().get(provider, {})


def set_provider(provider: str, secrets: dict, config_: dict | None = None) -> dict:
    data = _read()
    entry = data.get(provider, {})
    for k, v in (secrets or {}).items():
        if v:  # never overwrite with empty values
            entry[k] = str(v)
    if config_:
        entry.update(config_)
    entry["updated_at"] = now_iso()
    data[provider] = entry
    _write(data)
    return public_view(provider)


def delete_provider(provider: str) -> bool:
    data = _read()
    if provider in data:
        del data[provider]
        _write(data)
        return True
    return False


def public_view(provider: str) -> dict:
    """Presence/scopes only — secret values never leave this process."""
    entry = get_provider(provider)
    if not entry:
        return {"provider": provider, "present": False}
    view = {
        "provider": provider,
        "present": True,
        "updated_at": entry.get("updated_at"),
        "scopes": entry.get("scopes"),
        "expires_at": entry.get("expires_at"),
        "note": entry.get("note"),
        "has_client": bool(entry.get("client_id") or entry.get("app_id")),
        "has_token": bool(entry.get("access_token") or entry.get("refresh_token")),
        "has_api_key": bool(entry.get("api_key")),
    }
    return view


def has_meta_token() -> bool:
    return bool(get_provider("meta").get("access_token"))


def has_google_token() -> bool:
    return bool(get_provider("google").get("access_token"))
