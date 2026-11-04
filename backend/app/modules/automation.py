"""Automation — five idempotent jobs, an in-process scheduler, retries with
backoff, run history and markdown reports. Side-effecting steps inside jobs still
pass the approval gate; jobs never publish anything by themselves."""
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel

from .. import activity, config, db
from ..security import NexusError, clamp, now_iso, sanitize_filename

router = APIRouter(prefix="/api/automation", tags=["automation"])

MAX_ATTEMPTS = 3


# ------------------------------------------------------------------ jobs -----
def job_daily_research() -> dict:
    from . import content
    res = content.trends()
    n = sum(len(c.get("items", [])) for c in res.get("clusters", []))
    return {"clusters": len(res.get("clusters", [])), "items": n,
            "stale": res.get("stale", False)}


def job_content_preparation() -> dict:
    topics = [t.strip() for t in db.get_setting("content_topics").split(",") if t.strip()]
    if not topics:
        return {"created": 0, "note": "no content_topics configured in settings — skipped"}
    created = 0
    today = datetime.now(timezone.utc).date()
    rows = db.query("SELECT DISTINCT date FROM content_calendar")
    existing = {r["date"] for r in rows}
    for offset in range(3):
        d = (today + timedelta(days=offset)).isoformat()
        if d in existing:
            continue
        topic = topics[(created + len(existing)) % len(topics)]
        db.execute(
            "INSERT INTO content_calendar(date,platform,title,brief,status,created_ts) "
            "VALUES(?,'instagram',?,?,'draft',?)",
            (d, f"Draft: {topic}", f"Auto-planned by content_preparation ({topic})",
             now_iso()))
        created += 1
    activity.info("automation", f"content_preparation created {created} draft entries")
    return {"created": created, "topics": len(topics)}


def job_video_production() -> dict:
    row = db.one(
        "SELECT * FROM content_calendar WHERE status IN ('draft','planned') "
        "AND title NOT LIKE 'Draft:%' ORDER BY date ASC LIMIT 1")
    if not row:
        row = db.one("SELECT * FROM content_calendar WHERE status IN ('draft','planned') "
                     "ORDER BY date ASC LIMIT 1")
    if not row:
        return {"produced": False, "note": "no pending calendar entries"}
    from . import youtube
    topic = row["title"]
    scr = youtube.script(youtube.ScriptIn(topic=topic, type="short",
                                          notes=row.get("brief")))
    text = scr["script"]
    subs = youtube.subtitles(youtube.SubtitlesIn(text=text[:6000], name=f"cal_{row['id']}"))
    thumb = youtube.thumbnail(youtube.ThumbIn(title=topic[:80], subtitle="NEXUS auto-prep"))
    rendered = None
    if db.get_setting("auto_render") == "1":
        import re
        scenes = [{"text": s.strip()[:120], "seconds": 4.0}
                  for s in re.split(r"\n{2,}", text) if s.strip()][:8]
        if scenes:
            r = youtube.render(youtube.RenderIn(title=topic[:60],
                                                scenes=[youtube.Scene(**s) for s in scenes]))
            rendered = r["path"]
    return {"produced": True, "topic": topic, "script_id": scr["id"],
            "subtitles": subs["path"], "thumbnail": thumb["path"],
            "video": rendered,
            "note": None if rendered else "render skipped (auto_render=0)"}


def job_job_discovery() -> dict:
    from . import linkedin
    fetched, sources = linkedin._fetch_feeds()
    inserted = 0
    for j in fetched:
        cur = db.execute(
            "INSERT OR IGNORE INTO job_listings(source,external_id,title,company,"
            "location,url,tags,salary,fetched_at,raw) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (j["source"], j["external_id"], j["title"], j["company"], j["location"],
             j["url"], j["tags"], j["salary"], now_iso(), db.dumps(j["raw"])))
        if cur:
            inserted += 1
        if any(t in (j["tags"] or "").lower() for t in ("freelance", "contract", "gig")) \
                or "freelance" in (j["title"] or "").lower():
            db.execute(
                "INSERT INTO freelance_leads(source,title,client,url,tags,fetched_at) "
                "VALUES(?,?,?,?,?,?)",
                (j["source"], j["title"], j["company"], j["url"], j["tags"], now_iso()))
    return {"fetched": len(fetched), "new": inserted,
            "sources": [s["name"] for s in sources]}


def job_weekly_report() -> dict:
    stats = {
        "approvals_pending": db.one("SELECT COUNT(*) c FROM approvals WHERE "
                                    "status='pending'")["c"],
        "posts_draft": db.one("SELECT COUNT(*) c FROM posts WHERE status='draft'")["c"],
        "calendar_entries": db.one("SELECT COUNT(*) c FROM content_calendar")["c"],
        "videos": db.one("SELECT COUNT(*) c FROM videos")["c"],
        "jobs": db.one("SELECT COUNT(*) c FROM job_listings")["c"],
        "applications": db.one("SELECT COUNT(*) c FROM job_applications")["c"],
        "revenue_verified": db.one("SELECT COALESCE(SUM(amount),0) s FROM "
                                   "revenue_events WHERE verified=1")["s"],
        "revenue_unverified": db.one("SELECT COALESCE(SUM(amount),0) s FROM "
                                     "revenue_events WHERE verified=0")["s"],
        "ai_calls": db.one("SELECT COUNT(*) c FROM ai_calls")["c"],
        "tasks_failed": db.one("SELECT COUNT(*) c FROM tasks WHERE status='failed'")["c"],
    }
    lines = [f"# NEXUS AI Weekly Report — {datetime.now(timezone.utc).date()}",
             "", "## Metrics (local SQLite, real counts)", ""]
    for k, v in stats.items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## Recent tasks", ""]
    for t in db.query("SELECT ts,module,name,status,duration_ms FROM tasks "
                      "ORDER BY id DESC LIMIT 15"):
        lines.append(f"- {t['ts']} [{t['module']}] {t['name']} — {t['status']} "
                     f"({t['duration_ms']} ms)")
    lines += ["", "## Recent approvals", ""]
    for a in db.query("SELECT ts,kind,title,status FROM approvals ORDER BY id DESC LIMIT 10"):
        lines.append(f"- {a['ts']} {a['kind']}: {a['title']} — **{a['status']}**")
    lines += ["", "> Generated locally by NEXUS AI. All numbers are real database "
              "counts — no estimates.", ""]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = config.REPORTS_DIR / f"{stamp}_weekly.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    db.execute("INSERT INTO reports(ts,kind,path,summary) VALUES(?,?,?,?)",
               (now_iso(), "weekly", str(path), db.dumps(stats)))
    activity.info("automation", f"weekly report written: {path.name}")
    return {"path": str(path), "stats": stats}


JOBS = {
    "daily_research": job_daily_research,
    "content_preparation": job_content_preparation,
    "video_production": job_video_production,
    "job_discovery": job_job_discovery,
    "weekly_report": job_weekly_report,
}


# ------------------------------------------------------------ run + retry ----
def run_job(name: str, trigger: str = "manual") -> dict:
    fn = JOBS.get(name)
    if not fn:
        raise NexusError(f"unknown job: {name}", code="unknown_job", status=404)
    attempts, last_err, result = 0, None, None
    started = time.time()
    while attempts < MAX_ATTEMPTS:
        attempts += 1
        try:
            result = fn()
            status = "ok"
            last_err = None
            break
        except Exception as exc:
            last_err = f"{exc.__class__.__name__}: {exc}"
            activity.warn("automation", f"{name} attempt {attempts} failed", last_err)
            if attempts < MAX_ATTEMPTS:
                time.sleep(min(2 ** attempts, 8))
    duration = int((time.time() - started) * 1000)
    detail = {"trigger": trigger, "result": result, "error": last_err,
              "duration_ms": duration}
    rid = db.execute(
        "INSERT INTO automation_runs(job,ts,status,attempts,detail) VALUES(?,?,?,?,?)",
        (name, now_iso(), status, attempts, db.dumps(detail)))
    db.execute("UPDATE automation_jobs SET last_run_ts=?, last_status=? WHERE name=?",
               (now_iso(), status, name))
    activity.log("info" if status == "ok" else "error", "automation",
                 f"job {name}: {status} ({attempts} attempt(s), {duration} ms)")
    return {"run_id": rid, "job": name, "status": status, "attempts": attempts,
            "detail": detail}


# --------------------------------------------------------------- scheduler ---
class Scheduler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="nexus-scheduler")
        self._stop = threading.Event()
        self.tick = 0

    def run(self):
        # First pass: stamp last_run so jobs wait a full interval, no startup burst.
        for j in db.query("SELECT name, last_run_ts FROM automation_jobs"):
            if not j["last_run_ts"]:
                db.execute("UPDATE automation_jobs SET last_run_ts=? WHERE name=?",
                           (now_iso(), j["name"]))
        while not self._stop.wait(30):
            self.tick += 1
            try:
                self._check_due()
            except Exception as exc:
                activity.error("automation", "scheduler tick failed", str(exc))

    def _check_due(self):
        now = datetime.now(timezone.utc)
        for job in db.query("SELECT * FROM automation_jobs WHERE enabled=1"):
            due = False
            if job["interval_minutes"]:
                last = job["last_run_ts"]
                if last:
                    try:
                        age = now - datetime.fromisoformat(last)
                        due = age >= timedelta(minutes=job["interval_minutes"])
                    except ValueError:
                        due = True
            if not due and job["daily_time"]:
                try:
                    hh, mm = (int(x) for x in job["daily_time"].split(":"))
                    last_day = (job["last_run_ts"] or "")[:10]
                    today = now.date().isoformat()
                    due = (last_day != today
                           and (now.hour, now.minute) >= (hh, mm))
                except ValueError:
                    due = False
            if due:
                run_job(job["name"], trigger="schedule")

    def stop(self):
        self._stop.set()


scheduler = Scheduler()


# -------------------------------------------------------------- endpoints ----
class RunIn(BaseModel):
    job: str


@router.get("/jobs")
def jobs_list():
    return db.query("SELECT * FROM automation_jobs ORDER BY name")


@router.post("/run")
def run(body: RunIn):
    result = run_job(body.job, trigger="manual")
    return result


@router.get("/runs")
def runs(limit: int = Query(30, le=200)):
    rows = db.query("SELECT * FROM automation_runs ORDER BY id DESC LIMIT ?",
                    (clamp(limit, 1, 200, 30),))
    import json
    for r in rows:
        try:
            r["detail"] = json.loads(r["detail"]) if r["detail"] else None
        except (ValueError, TypeError):
            pass
    return rows


@router.get("/reports")
def reports():
    import json as _json
    rows = db.query("SELECT * FROM reports ORDER BY id DESC LIMIT 50")
    out = []
    for r in rows:
        out.append({"id": r["id"], "ts": r["ts"], "kind": r["kind"],
                    "name": sanitize_filename(r["path"].split("\\")[-1].split("/")[-1]),
                    "summary": _json.loads(r["summary"]) if r["summary"] else None})
    files = sorted(config.REPORTS_DIR.glob("*.md"), reverse=True)
    for f in files:
        if not any(o["name"] == f.name for o in out):
            out.append({"id": None, "ts": datetime.fromtimestamp(
                f.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
                "kind": "weekly", "name": f.name, "summary": None})
    return {"reports": out[:50]}


@router.get("/reports/content")
def report_content(name: str):
    safe = sanitize_filename(name)
    path = config.REPORTS_DIR / safe
    if not path.exists() or path.suffix != ".md":
        raise NexusError("report not found", code="not_found", status=404)
    return {"name": safe, "content": path.read_text(encoding="utf-8")}


@router.get("/status")
def scheduler_status():
    running = scheduler.is_alive()
    return {"running": running, "tick": scheduler.tick,
            "interval_s": 30,
            "jobs_enabled": db.one("SELECT COUNT(*) c FROM automation_jobs "
                                   "WHERE enabled=1")["c"]}
