"""Account Centre — GitHub (via system `gh`, token never read), Meta, Google/YouTube,
LinkedIn. Secrets live only in data/credentials.json; responses are presence/scopes only."""
import re
import shutil

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import activity, approvals, config, credentials, process
from ..security import ApprovalRequired, NexusError, now_iso, redact

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

PROVIDERS = {
    "github": "GitHub",
    "meta": "Meta (Instagram/Facebook)",
    "google": "Google / YouTube",
    "linkedin": "LinkedIn",
}


def _github_status() -> dict:
    if not shutil.which("gh"):
        return {"provider": "github", "label": PROVIDERS["github"],
                "status": "awaiting_configuration", "present": False,
                "note": "GitHub CLI (gh) not found on PATH."}
    try:
        out = process.run(["gh", "auth", "status"], timeout=20)
        text = redact((out["stdout"] or "") + (out["stderr"] or ""))
    except NexusError as exc:
        return {"provider": "github", "label": PROVIDERS["github"],
                "status": "awaiting_configuration", "present": False,
                "note": str(exc)}
    if "Logged in to github.com account" in text:
        acct = re.search(r"account\s+(\S+)", text)
        scopes = re.search(r"Token scopes:\s*'([^']*)'", text)
        return {"provider": "github", "label": PROVIDERS["github"], "status": "connected",
                "present": True, "account": acct.group(1) if acct else None,
                "scopes": scopes.group(1) if scopes else None,
                "note": "Uses your system gh login — NEXUS never reads the token."}
    return {"provider": "github", "label": PROVIDERS["github"],
            "status": "awaiting_authentication", "present": False,
            "note": "Run `gh auth login` in a terminal to connect GitHub."}


def _cred_status(provider: str, label: str, needed: str,
                 pending_note: str) -> dict:
    view = credentials.public_view(provider)
    if view["present"] and (view.get("has_token") or needed == "config"):
        status = "connected"
    elif view["present"]:
        status = "awaiting_authentication"
    else:
        status = "awaiting_configuration"
    return {"provider": provider, "label": label, "status": status,
            "present": view["present"], "scopes": view.get("scopes"),
            "updated_at": view.get("updated_at"), "note": pending_note,
            "has_client": view.get("has_client"), "has_token": view.get("has_token")}


@router.get("")
def accounts():
    github = _github_status()
    meta = _cred_status("meta", PROVIDERS["meta"], "token",
                        "Add an Instagram Graph API access token + ig_user_id to enable "
                        "authorised publishing and real analytics.")
    google = _cred_status("google", PROVIDERS["google"], "config",
                          "Import an OAuth client (client_id/client_secret) from Google "
                          "Cloud Console, then authorise in YouTube Studio.")
    linkedin = {"provider": "linkedin", "label": PROVIDERS["linkedin"],
                "status": "not_applicable", "present": False,
                "note": "LinkedIn offers no official posting/application API for "
                        "personal accounts. NEXUS uses permitted public feeds only "
                        "and never automates LinkedIn itself."}
    return {"providers": [github, meta, google, linkedin]}


class ConfigureIn(BaseModel):
    secrets: dict = Field(default_factory=dict)
    config: dict | None = None


@router.post("/{provider}/configure")
def configure(provider: str, body: ConfigureIn):
    provider = provider.lower().strip()
    if provider not in PROVIDERS:
        raise NexusError(f"unknown provider: {provider}", code="unknown_provider",
                         status=404)
    if provider == "github":
        raise NexusError("GitHub uses your system `gh` authentication. NEXUS never "
                         "accepts or stores a GitHub token. Run `gh auth login` instead.",
                         code="use_system_gh", status=400)
    if provider == "linkedin":
        raise NexusError("No official LinkedIn API exists for personal accounts — "
                         "there is nothing to configure (see Account Centre note).",
                         code="not_applicable", status=400)
    if provider == "meta":
        if not (body.secrets.get("access_token") or credentials.get_provider("meta")
                .get("access_token")):
            raise NexusError("meta requires an access_token secret",
                             code="missing_secret", status=422)
        view = credentials.set_provider(
            "meta", body.secrets,
            config_={**(body.config or {}),
                     "scopes": (body.config or {}).get("scopes", "instagram_basic,"
                                 "instagram_content_publish,instagram_manage_insights")})
        activity.info("accounts", "meta credentials stored")
        return {"code": "stored", "account": view,
                "note": "Token stored locally in data/credentials.json (gitignored)."}
    if provider == "google":
        missing = [k for k in ("client_id", "client_secret")
                   if not (body.secrets.get(k) or credentials.get_provider("google")
                           .get(k))]
        if missing:
            raise NexusError(f"google requires: {', '.join(missing)}",
                             code="missing_secret", status=422)
        view = credentials.set_provider("google", body.secrets,
                                        config_=(body.config or {}))
        activity.info("accounts", "google OAuth client stored")
        return {"code": "stored", "account": view,
                "note": "Next: authorise via YouTube Studio → OAuth."}
    raise NexusError("unreachable", code="error")


@router.delete("/{provider}")
def disconnect(provider: str):
    provider = provider.lower().strip()
    if provider not in PROVIDERS:
        raise NexusError(f"unknown provider: {provider}", code="unknown_provider",
                         status=404)
    if not credentials.get_provider(provider):
        return {"code": "not_connected", "provider": provider}
    try:
        approvals.require_approved(
            f"account.delete.{provider}",
            f"Disconnect {PROVIDERS[provider]} and delete stored credentials",
            {"provider": provider})
    except ApprovalRequired as exc:
        return {"code": "approval_required", "approval_id": exc.approval_id,
                "kind": exc.kind,
                "message": "Deleting stored credentials requires owner approval. "
                           "Approve, then retry."}
    credentials.delete_provider(provider)
    activity.info("accounts", f"{provider} credentials deleted")
    return {"code": "deleted", "provider": provider}
