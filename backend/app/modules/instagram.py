"""Instagram Studio — analysis, niche research, reels, captions, calendar,
approval-gated publishing via the official Meta Graph API, honest analytics."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import activity, ai_router, ai_fallback, approvals, credentials, db
from ..security import ApprovalRequired, NexusError, now_iso

router = APIRouter(prefix="/api/instagram", tags=["instagram"])

GRAPH = "https://graph.facebook.com/v21.0"


# ------------------------------------------------------------- analysis -----
class AnalyzeIn(BaseModel):
    profile_text: str = Field(min_length=5, max_length=8000)


@router.post("/profile/analyze")
def profile_analyze(body: AnalyzeIn):
    result = ai_router.generate(
        "Analyse this Instagram profile and return concrete improvements:\n"
        + body.profile_text,
        module="instagram.profile",
        system="You are a social media strategist. Be specific and honest.",
        fallback=lambda: json.dumps(
            ai_fallback.profile_analysis(body.profile_text), ensure_ascii=False))
    analysis = None
    if result["generated_by"] != "fallback":
        analysis = None  # model prose goes to `text`
    else:
        try:
            analysis = json.loads(result["text"])
        except (ValueError, TypeError):
            analysis = ai_fallback.profile_analysis(body.profile_text)
    activity.info("instagram", "profile analysed",
                  {"generated_by": result["generated_by"]})
    return {"analysis": analysis, "text": result["text"] or None,
            "generated_by": result["generated_by"],
            "disclaimer": "AI-generated guidance — not measured account data."}


class NicheIn(BaseModel):
    niche: str = Field(min_length=2, max_length=120)
    context: str | None = Field(default=None, max_length=4000)


@router.post("/niche/research")
def niche_research(body: NicheIn):
    result = ai_router.generate(
        f"Niche research brief: {body.niche}. Context: {body.context or 'none'}",
        module="instagram.niche",
        system="Produce honest niche analysis; label uncertainty.",
        fallback=lambda: json.dumps(
            ai_fallback.niche_research(body.niche), ensure_ascii=False))
    try:
        data = json.loads(result["text"]) if result["generated_by"] == "fallback" else None
    except (ValueError, TypeError):
        data = None
    analysis = data or ai_fallback.niche_research(body.niche)
    db.execute("INSERT INTO niche_research(niche,result,generated_by,created_ts) "
               "VALUES(?,?,?,?)",
               (body.niche, db.dumps(analysis), result["generated_by"], now_iso()))
    activity.info("instagram", f"niche research: {body.niche}",
                  {"generated_by": result["generated_by"]})
    return {"result": analysis, "generated_by": result["generated_by"],
            "tag": "hypothesis"}


class ReelsIn(BaseModel):
    topic: str = Field(min_length=2, max_length=200)
    count: int = Field(default=3, ge=1, le=8)


@router.post("/reels/ideas")
def reels_ideas(body: ReelsIn):
    result = ai_router.generate(
        f"Give {body.count} Instagram Reels ideas about: {body.topic}",
        module="instagram.reels",
        fallback=lambda: json.dumps(
            ai_fallback.reels(body.topic, body.count), ensure_ascii=False))
    ideas = None
    if result["generated_by"] == "fallback":
        try:
            ideas = json.loads(result["text"])
        except (ValueError, TypeError):
            ideas = ai_fallback.reels(body.topic, body.count)
    return {"ideas": ideas, "text": result["text"] or None,
            "generated_by": result["generated_by"]}


class CaptionsIn(BaseModel):
    topic: str = Field(min_length=2, max_length=300)
    count: int = Field(default=3, ge=1, le=10)
    tone: str = Field(default="engaging", max_length=40)


@router.post("/captions")
def captions(body: CaptionsIn):
    result = ai_router.generate(
        f"Write {body.count} {body.tone} Instagram captions about: {body.topic}",
        module="instagram.captions",
        fallback=lambda: json.dumps(
            ai_fallback.captions(body.topic, body.count, body.tone), ensure_ascii=False))
    caps = None
    if result["generated_by"] == "fallback":
        try:
            caps = json.loads(result["text"])
        except (ValueError, TypeError):
            caps = ai_fallback.captions(body.topic, body.count, body.tone)
    if caps:
        for c in caps[:3]:
            db.execute("INSERT INTO posts(platform,content,status,created_ts) "
                       "VALUES('instagram',?,'draft',?)",
                       (c.get("caption", ""), now_iso()))
    return {"captions": caps, "text": result["text"] or None,
            "generated_by": result["generated_by"]}


# ------------------------------------------------------------- calendar -----
class CalendarIn(BaseModel):
    date: str = Field(min_length=8, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$")
    platform: str = Field(default="instagram", max_length=30)
    title: str = Field(min_length=2, max_length=200)
    brief: str | None = Field(default=None, max_length=2000)
    status: str = Field(default="draft", max_length=20)


@router.get("/calendar")
def calendar_list():
    return db.query("SELECT * FROM content_calendar ORDER BY date ASC, id ASC LIMIT 400")


@router.post("/calendar", status_code=201)
def calendar_add(body: CalendarIn):
    if body.status not in ("draft", "planned", "approved", "published"):
        raise NexusError("status must be draft|planned|approved|published",
                         code="invalid_status")
    cid = db.execute(
        "INSERT INTO content_calendar(date,platform,title,brief,status,created_ts) "
        "VALUES(?,?,?,?,?,?)",
        (body.date, body.platform.lower(), body.title, body.brief, body.status, now_iso()))
    activity.info("instagram", f"calendar entry created: {body.title}")
    return db.one("SELECT * FROM content_calendar WHERE id=?", (cid,))


@router.delete("/calendar/{entry_id}")
def calendar_delete(entry_id: int):
    row = db.one("SELECT * FROM content_calendar WHERE id=?", (entry_id,))
    if not row:
        raise NexusError("calendar entry not found", code="not_found", status=404)
    try:
        approvals.require_approved(
            "delete.data", f"Delete calendar entry #{entry_id}: {row['title']}",
            {"table": "content_calendar", "id": entry_id})
    except ApprovalRequired as exc:
        return {"code": "approval_required", "approval_id": exc.approval_id,
                "kind": exc.kind,
                "message": "Deleting data requires owner approval. Approve it, then retry."}
    db.execute("DELETE FROM content_calendar WHERE id=?", (entry_id,))
    activity.info("instagram", f"calendar entry deleted: {entry_id}")
    return {"code": "deleted", "id": entry_id}


# ------------------------------------------------------- publishing gate -----
class PublishIn(BaseModel):
    caption: str = Field(min_length=1, max_length=2200)
    media_url: str | None = Field(default=None, max_length=2000)
    ig_user_id: str | None = Field(default=None, max_length=60)


@router.post("/publish")
def publish(body: PublishIn):
    creds = credentials.get_provider("meta")
    token = creds.get("access_token")
    if not token:
        return {"requires_auth": True, "provider": "meta",
                "message": "Meta/Instagram Graph token not configured. "
                           "Add it in Account Centre to enable authorised publishing."}
    ig_user = body.ig_user_id or creds.get("ig_user_id")
    if not ig_user:
        return {"requires_auth": True, "provider": "meta",
                "message": "Instagram business account id (ig_user_id) missing."}
    payload = body.model_dump()
    try:
        record = approvals.require_approved(
            "publish.instagram", f"Publish to Instagram: {body.caption[:60]}…", payload)
    except ApprovalRequired as exc:
        return {"code": "approval_required", "approval_id": exc.approval_id,
                "kind": exc.kind,
                "message": "Publishing requires owner approval. Approve, then retry."}
    if not body.media_url:
        raise NexusError(
            "The official Instagram Graph API publishes photo/video posts only and needs a "
            "publicly accessible media_url. Text-only publishing is not supported by the API.",
            code="media_url_required", status=422)
    try:
        r = httpx.post(f"{GRAPH}/{ig_user}/media", timeout=30,
                       data={"image_url": body.media_url, "caption": body.caption,
                             "access_token": token})
        data = r.json()
        if r.status_code != 200 or "id" not in data:
            raise NexusError(data.get("error", {}).get("message", "Graph API error"),
                             code="graph_error", status=502)
        container = data["id"]
        r2 = httpx.post(f"{GRAPH}/{ig_user}/media_publish", timeout=30,
                        data={"creation_id": container, "access_token": token})
        data2 = r2.json()
        if r2.status_code != 200 or "id" not in data2:
            raise NexusError(data2.get("error", {}).get("message", "publish failed"),
                             code="graph_error", status=502)
        post_id = db.execute(
            "INSERT INTO posts(platform,content,status,approval_id,created_ts,published_ts,"
            "remote_id) VALUES('instagram',?,'published',?,?,?,?)",
            (body.caption, record["id"], now_iso(), now_iso(), data2["id"]))
        activity.info("instagram", "published via Graph API", {"post_id": post_id})
        return {"code": "published", "remote_id": data2["id"], "post_id": post_id}
    except httpx.HTTPError as exc:
        raise NexusError(f"Graph API unreachable: {exc}", code="network_error", status=502)


# ----------------------------------------------------------- meta oauth -----
META_AUTH = "https://www.facebook.com/v21.0/dialog/oauth"
META_TOKEN = "https://graph.facebook.com/v21.0/oauth/access_token"
META_REDIRECT = "https://www.facebook.com/connect/login_success.html"
META_SCOPES = ("instagram_basic,instagram_content_publish,"
               "instagram_manage_insights,pages_show_list,pages_read_engagement")


class MetaCallbackIn(BaseModel):
    code: str = Field(min_length=5, max_length=4000)
    redirect_uri: str | None = Field(default=None, max_length=500)


@router.get("/oauth/status")
def oauth_status():
    c = credentials.get_provider("meta")
    return {
        "app_configured": bool(c.get("app_id") and c.get("app_secret")),
        "authorized": bool(c.get("access_token")),
        "has_ig_user_id": bool(c.get("ig_user_id")),
        "expires_at": c.get("expires_at"),
        "scopes": c.get("scopes"),
        "redirect_uri": c.get("redirect_uri") or META_REDIRECT,
        "status": ("connected" if c.get("access_token") and c.get("ig_user_id")
                   else ("awaiting_authentication" if c.get("app_id")
                         else "awaiting_configuration")),
        "note": "Instagram publishing requires a Business or Creator account linked "
                "to a Facebook Page. Personal accounts cannot publish via the API.",
    }


class MetaAppIn(BaseModel):
    app_id: str = Field(min_length=5, max_length=40)
    app_secret: str = Field(min_length=8, max_length=200)
    ig_user_id: str | None = Field(default=None, max_length=60)


@router.post("/oauth/configure")
def oauth_configure(body: MetaAppIn):
    view = credentials.set_provider(
        "meta", {"app_id": body.app_id, "app_secret": body.app_secret},
        config_={"redirect_uri": META_REDIRECT, "scopes": META_SCOPES,
                 **({"ig_user_id": body.ig_user_id} if body.ig_user_id else {})})
    activity.info("instagram", "meta app credentials stored")
    return {"code": "stored", "provider": "meta",
            "present": view.get("present"), "has_client": view.get("has_client"),
            "note": "Meta app id/secret stored locally in data/credentials.json "
                    "(gitignored) and never returned by the API."}


@router.get("/oauth/start")
def oauth_start():
    c = credentials.get_provider("meta")
    app_id = c.get("app_id")
    if not app_id:
        raise NexusError("Meta app not configured — add an app id and secret first",
                         code="awaiting_configuration", status=400)
    state = uuid.uuid4().hex
    db.execute("INSERT INTO oauth_states(provider,state,created_ts,status) "
               "VALUES('meta',?,?,'pending') "
               "ON CONFLICT(provider) DO UPDATE SET state=excluded.state, "
               "created_ts=excluded.created_ts, status='pending'", (state, now_iso()))
    redirect = c.get("redirect_uri") or META_REDIRECT
    url = (f"{META_AUTH}?client_id={app_id}&redirect_uri={redirect}"
           f"&response_type=code&state={state}&scope={META_SCOPES}")
    return {
        "auth_url": url, "state": state, "redirect_uri": redirect,
        "manual": "Open auth_url, approve access, then copy the whole redirect URL you "
                  "land on (it contains ?code=…) and submit it in Instagram Studio.",
        "eligibility": "Requires an Instagram Business/Creator account connected to a "
                       "Facebook Page that you administer.",
    }


@router.post("/oauth/callback")
def oauth_callback(body: MetaCallbackIn):
    """Exchange an authorisation code for a long-lived token. The code comes from the
    redirect URL the owner lands on; the app secret never leaves this process."""
    c = credentials.get_provider("meta")
    app_id, secret = c.get("app_id"), c.get("app_secret")
    if not app_id or not secret:
        raise NexusError("Meta app not configured", code="awaiting_configuration",
                         status=400)
    redirect = body.redirect_uri or c.get("redirect_uri") or META_REDIRECT
    try:
        r = httpx.get(META_TOKEN, params={
            "client_id": app_id, "client_secret": secret, "redirect_uri": redirect,
            "code": body.code.strip()}, timeout=30)
    except httpx.HTTPError as exc:
        raise NexusError(f"Meta token endpoint unreachable: {exc.__class__.__name__}",
                         code="network_error", status=502)
    data = r.json()
    if "access_token" not in data:
        err = data.get("error") or {}
        raise NexusError(err.get("message") or "token exchange failed",
                         code="oauth_failed", status=400)
    token = data["access_token"]
    # Exchange for a long-lived token when the app secret is available.
    expires_at = None
    try:
        ll = httpx.get(f"{GRAPH}/oauth/access_token", params={
            "grant_type": "fb_exchange_token", "client_id": app_id,
            "client_secret": secret, "fb_exchange_token": token}, timeout=30)
        lld = ll.json()
        if "access_token" in lld:
            token = lld["access_token"]
            expires_at = (datetime.now(timezone.utc) + timedelta(
                seconds=int(lld.get("expires_in", 5184000)))).isoformat(timespec="seconds")
    except (httpx.HTTPError, ValueError, KeyError):
        pass
    credentials.set_provider("meta", {"access_token": token},
                             config_={"expires_at": expires_at,
                                      "redirect_uri": redirect, "scopes": META_SCOPES})
    db.execute("UPDATE oauth_states SET status='connected', detail=? WHERE provider='meta'",
               ("token stored",))
    identity = _verify_identity()
    activity.info("instagram", "meta oauth completed",
                  {"authorized": identity.get("ok", False)})
    return {"code": "connected", "identity": identity,
            "note": "Token stored locally; it is never returned by the API."}


def _verify_identity() -> dict:
    """Check the token actually maps to an Instagram professional account + scopes."""
    c = credentials.get_provider("meta")
    token = c.get("access_token")
    if not token:
        return {"ok": False, "reason": "no token"}
    try:
        me = httpx.get(f"{GRAPH}/me", params={
            "fields": "id,name", "access_token": token}, timeout=20).json()
        pages = httpx.get(f"{GRAPH}/me/accounts", params={
            "fields": "id,name,instagram_business_account",
            "access_token": token}, timeout=20).json()
        perms = httpx.get(f"{GRAPH}/me/permissions", params={
            "access_token": token}, timeout=20).json()
    except httpx.HTTPError as exc:
        return {"ok": False, "reason": f"network: {exc.__class__.__name__}"}
    granted = sorted(p.get("permission") for p in perms.get("data", [])
                     if p.get("status") == "granted")
    ig_accounts = []
    for page in pages.get("data", []):
        iba = page.get("instagram_business_account") or {}
        if iba.get("id"):
            ig_accounts.append({"page": page.get("name"), "ig_user_id": iba["id"]})
    required = {"instagram_basic", "instagram_content_publish"}
    missing = sorted(required - set(granted))
    ok = bool(ig_accounts) and not missing
    if ok and not c.get("ig_user_id"):
        credentials.set_provider("meta", {}, config_={"ig_user_id":
                                                      ig_accounts[0]["ig_user_id"]})
    return {
        "ok": ok,
        "facebook_user": me.get("name") or me.get("id"),
        "instagram_accounts": ig_accounts,
        "granted_permissions": granted,
        "missing_permissions": missing,
        "blocked_by_permission": bool(missing),
        "reason": (None if ok else
                   ("no Instagram professional account is linked to a Page you manage"
                    if not ig_accounts else
                    f"missing permissions: {', '.join(missing)}")),
    }


@router.get("/oauth/verify")
def oauth_verify():
    c = credentials.get_provider("meta")
    if not c.get("access_token"):
        return {"ok": False, "requires_auth": True,
                "reason": "no Meta token stored — run the OAuth flow first"}
    return _verify_identity()


@router.get("/analytics")
def analytics():
    creds = credentials.get_provider("meta")
    token = creds.get("access_token")
    ig_user = creds.get("ig_user_id")
    if not token or not ig_user:
        return {"requires_auth": True, "provider": "meta",
                "message": "Analytics need a configured Meta token and ig_user_id. "
                           "No numbers are shown without real API data."}
    try:
        r = httpx.get(f"{GRAPH}/{ig_user}/insights",
                      params={"metric": "impressions,reach,follower_count",
                              "period": "day", "access_token": token},
                      timeout=30)
        data = r.json()
        if r.status_code != 200 or "data" not in data:
            raise NexusError(data.get("error", {}).get("message", "insights failed"),
                             code="graph_error", status=502)
        metrics = {m["name"]: {"values": m.get("values", []),
                               "period": m.get("period")} for m in data["data"]}
        return {"requires_auth": False, "metrics": metrics, "fetched_at": now_iso(),
                "source": "Meta Graph API insights"}
    except httpx.HTTPError as exc:
        raise NexusError(f"Graph API unreachable: {exc}", code="network_error", status=502)
