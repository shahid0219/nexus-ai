"""Instagram Studio — analysis, niche research, reels, captions, calendar,
approval-gated publishing via the official Meta Graph API, honest analytics."""
import json

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import activity, ai_fallback, approvals, credentials, db, ollama_client
from ..security import ApprovalRequired, NexusError, clamp, now_iso, sanitize_filename

router = APIRouter(prefix="/api/instagram", tags=["instagram"])

GRAPH = "https://graph.facebook.com/v21.0"


# ------------------------------------------------------------- analysis -----
class AnalyzeIn(BaseModel):
    profile_text: str = Field(min_length=5, max_length=8000)


@router.post("/profile/analyze")
def profile_analyze(body: AnalyzeIn):
    result = ollama_client.generate(
        "Analyse this Instagram profile and return concrete improvements:\n"
        + body.profile_text,
        module="instagram.profile",
        system="You are a social media strategist. Be specific and honest.",
        fallback=lambda: json.dumps(
            ai_fallback.profile_analysis(body.profile_text), ensure_ascii=False))
    import json
    analysis = None
    if result["generated_by"] == "ollama":
        analysis = None  # free text goes to `text`
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
    payload = {"niche": body.niche, "context": body.context or ""}
    result = ollama_client.generate(
        f"Niche research brief: {body.niche}. Context: {body.context or 'none'}",
        module="instagram.niche",
        system="Produce honest niche analysis; label uncertainty.",
        fallback=lambda: json.dumps(
            ai_fallback.niche_research(body.niche), ensure_ascii=False))
    import json
    try:
        data = json.loads(result["text"]) if result["generated_by"] != "ollama" else None
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
    result = ollama_client.generate(
        f"Give {body.count} Instagram Reels ideas about: {body.topic}",
        module="instagram.reels",
        fallback=lambda: json.dumps(
            ai_fallback.reels(body.topic, body.count), ensure_ascii=False))
    import json
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
    result = ollama_client.generate(
        f"Write {body.count} {body.tone} Instagram captions about: {body.topic}",
        module="instagram.captions",
        fallback=lambda: json.dumps(
            ai_fallback.captions(body.topic, body.count, body.tone), ensure_ascii=False))
    import json
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
