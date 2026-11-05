"""Content Intelligence — global trends from permitted public feeds, audience
research (labelled hypotheses), platform-specific content generation."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import activity, ai_router, ai_fallback, db
from ..security import NexusError, now_iso

router = APIRouter(prefix="/api/content", tags=["content"])

UA = {"User-Agent": "NEXUS-AI/1.0 (local research tool; +github.com/shahid0219/nexus-ai)"}
FEED_TIMEOUT = 6.0                                  # per-socket timeout
FEED_DEADLINE = 8.0                                 # hard cap per source
HTTP_TIMEOUT = httpx.Timeout(FEED_TIMEOUT, connect=3.0)
PLATFORM_LIMITS = {"instagram": 2200, "youtube": 5000, "linkedin": 3000, "x": 280}

STOPWORDS = set("""a an and are as at be by for from has have how i in is it its of on or
that the this to was we what when where which who why will with you your not but if then
than so more most can could should would about into over after before their there they
them he she his her was were been being do does did done just very new get make made also
one two three top best""".split())


def _hn_top() -> list[dict]:
    r = httpx.get("https://hn.algolia.com/api/v1/search",
                  params={"tags": "front_page", "hitsPerPage": 25}, headers=UA,
                  timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    out = []
    for h in r.json().get("hits", []):
        out.append({"title": h.get("title") or "", "url": h.get("url")
                    or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                    "source": "hackernews", "score": h.get("points") or 0,
                    "at": h.get("created_at")})
    return out


def _reddit_top(sub: str = "technology") -> list[dict]:
    r = httpx.get(f"https://www.reddit.com/r/{sub}/top.json",
                  params={"limit": 20, "t": "day"}, headers=UA, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    out = []
    for child in r.json().get("data", {}).get("children", []):
        d = child.get("data", {})
        out.append({"title": d.get("title") or "",
                    "url": "https://www.reddit.com" + d.get("permalink", ""),
                    "source": f"reddit/r/{sub}", "score": d.get("ups") or 0,
                    "at": datetime.fromtimestamp(d.get("created_utc", 0),
                                                 tz=timezone.utc).isoformat()
                    if d.get("created_utc") else None})
    return out


def _keywords(text: str, n: int = 6) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.]{2,}", text.lower())
    freq = {}
    for w in words:
        if w not in STOPWORDS:
            freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:n]]


def _cluster(items: list[dict]) -> list[dict]:
    """Group stories that share top keywords into transparent clusters."""
    clusters: dict[str, dict] = {}
    for it in items:
        kws = _keywords(it["title"] + " " + (it.get("source") or ""), 4)
        if not kws:
            kws = ["misc"]
        key = kws[0]
        c = clusters.setdefault(key, {"keywords": [], "items": [], "fetched_at": now_iso()})
        for k in kws:
            if k not in c["keywords"]:
                c["keywords"].append(k)
        c["items"].append(it)
    out = []
    for key, c in sorted(clusters.items(), key=lambda kv: -len(kv[1]["items"]))[:8]:
        c["title"] = " / ".join(c["keywords"][:3]).title()
        c["items"] = sorted(c["items"], key=lambda x: -(x.get("score") or 0))[:6]
        out.append(c)
    return out


@router.get("/trends")
def trends():
    items, sources = [], []
    fetchers = [("hackernews", _hn_top, 25), ("reddit", _reddit_top, 20)]
    pool = ThreadPoolExecutor(max_workers=len(fetchers), thread_name_prefix="trend")
    try:
        futures = [(name, want, pool.submit(fn)) for name, fn, want in fetchers]
        for name, want, fut in futures:
            try:
                got = fut.result(timeout=FEED_DEADLINE)
                items += got
                sources.append({"name": name, "ok": True, "count": len(got) or want})
            except Exception as exc:
                sources.append({"name": name, "ok": False,
                                "error": (exc.__class__.__name__
                                          if not isinstance(exc, TimeoutError)
                                          else "timeout"),
                                "count": 0})
    finally:
        # Never block the response on a stuck socket.
        pool.shutdown(wait=False, cancel_futures=True)
    if not items:
        cached = db.query("SELECT * FROM trends_cache ORDER BY id DESC LIMIT 30")
        if cached:
            return {"clusters": [{"title": c["title"], "keywords":
                                  (c["keywords"] or "").split(","),
                                  "items": __import__("json").loads(c["sources"]),
                                  "fetched_at": c["fetched_at"]} for c in cached],
                    "sources": sources, "fetched_at": now_iso(), "stale": True,
                    "note": "Live feeds unreachable — showing last cached clusters."}
        raise NexusError("trend sources unreachable and no cache exists",
                         code="network_error", status=502)
    clusters = _cluster(items)
    for c in clusters:
        db.execute("INSERT INTO trends_cache(cluster_key,title,keywords,sources,fetched_at) "
                   "VALUES(?,?,?,?,?)",
                   (c["title"][:60], c["title"], ",".join(c["keywords"]),
                    db.dumps(c["items"]), now_iso()))
    synth = ai_router.generate(
        "Summarise these trending topics in 3 bullets:\n"
        + "\n".join(i["title"] for i in items[:12]),
        module="content.trends",
        fallback=lambda: "\n".join(f"- {i['title']}" for i in items[:6]))
    activity.info("content", f"trends fetched: {len(items)} items, "
                             f"{len(clusters)} clusters")
    return {"clusters": clusters, "sources": sources, "fetched_at": now_iso(),
            "synthesis": synth["text"], "generated_by": synth["generated_by"],
            "stale": False}


class AudienceIn(BaseModel):
    niche: str = Field(min_length=2, max_length=120)


@router.post("/audience")
def audience(body: AudienceIn):
    result = ai_router.generate(
        f"Audience research brief for niche: {body.niche}",
        module="content.audience",
        fallback=lambda: json.dumps(
            ai_fallback.audience(body.niche), ensure_ascii=False))
    try:
        data = json.loads(result["text"]) if result["generated_by"] == "fallback" else None
    except (ValueError, TypeError):
        data = None
    analysis = data or ai_fallback.audience(body.niche)
    db.execute("INSERT INTO audience_research(niche,result,generated_by,created_ts) "
               "VALUES(?,?,?,?)",
               (body.niche, db.dumps(analysis), result["generated_by"], now_iso()))
    return {"result": analysis, "generated_by": result["generated_by"],
            "tag": analysis.get("tag", "hypothesis")}


class GenerateIn(BaseModel):
    topic: str = Field(min_length=2, max_length=300)
    platforms: list[str] = Field(default_factory=lambda: ["instagram"], max_length=6)


@router.post("/generate")
def generate(body: GenerateIn):
    results, meta = {}, {}
    for platform in body.platforms:
        p = platform.lower().strip()
        if p not in PLATFORM_LIMITS:
            raise NexusError(f"unsupported platform: {platform}",
                             code="invalid_platform")
        res = ai_router.generate(
            f"Write a {p} post about: {body.topic}",
            module=f"content.{p}",
            fallback=lambda p=p: ai_fallback.platform_content(body.topic, p))
        text = res["text"] or ai_fallback.platform_content(body.topic, p)
        limit = PLATFORM_LIMITS[p]
        if p == "x":
            # split into a thread of ≤280-char segments
            segs, cur = [], ""
            for para in text.split("\n"):
                trial = (cur + "\n" + para).strip()
                if len(trial) <= 280:
                    cur = trial
                else:
                    if cur:
                        segs.append(cur)
                    cur = para[:277] + "…"
            if cur:
                segs.append(cur)
            text = "\n\n".join(segs[:6])
        elif len(text) > limit:
            text = text[:limit - 1] + "…"
        results[p] = text
        meta[p] = {"generated_by": res["generated_by"], "chars": len(text),
                   "limit": limit}
        db.execute("INSERT INTO posts(platform,content,status,created_ts) VALUES(?,?,?,?)",
                   (p, text, "draft", now_iso()))
    activity.info("content", f"generated content for {len(results)} platforms",
                  {"topic": body.topic[:60]})
    return {"results": results, "meta": meta}
