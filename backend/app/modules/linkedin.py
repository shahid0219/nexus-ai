"""LinkedIn Career Studio — profile, branding, permitted job discovery (public feeds),
matching, truthful CV generation, cover letters, application tracking.

Never scrapes LinkedIn (SECURITY.md §3); job data comes from permitted public JSON
feeds (RemoteOK, Remotive) with attribution. CV output contains ONLY facts present
in the supplied profile — missing items render as [not provided].
"""
import re
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from .. import activity, ai_router, ai_fallback, approvals, db, ollama_client
from ..security import ApprovalRequired, NexusError, clamp, now_iso

router = APIRouter(prefix="/api/linkedin", tags=["linkedin"])

FEEDS = {
    "remoteok": "https://remoteok.com/api",
    "remotive": "https://api.remotive.com/api/virtual-jobs",
}
CACHE_MINUTES = 30
FEED_TIMEOUT = 6.0                                  # per-socket timeout
FEED_DEADLINE = 8.0                                 # hard cap per source
HTTP_TIMEOUT = httpx.Timeout(FEED_TIMEOUT, connect=3.0)
UA = {"User-Agent": "NEXUS-AI/1.0 (local research tool; +https://github.com/shahid0219/nexus-ai)"}


# ------------------------------------------------------------ profile/brand ---
class ProfileIn(BaseModel):
    profile_text: str = Field(min_length=5, max_length=8000)


@router.post("/profile/improve")
def profile_improve(body: ProfileIn):
    result = ai_router.generate(
        "Improve this LinkedIn profile — headline, about, experience bullets. "
        "Rephrase only facts present in the text; never invent employers, dates, "
        "degrees or metrics.\n" + body.profile_text,
        module="linkedin.profile",
        system="Truthful editor. Do not add any fact not present in the input.",
        fallback=lambda: _fallback_improve(body.profile_text))
    return {"text": result["text"], "generated_by": result["generated_by"],
            "disclaimer": "Only rephrased facts from your text — no additions."}


def _fallback_improve(text: str) -> str:
    first = next((l.strip() for l in text.splitlines() if l.strip()), "your profile")
    return (f"[offline fallback — structural edit]\n\n"
            f"HEADLINE (rewrite of line 1):\n"
            f"  {first[:100]} — focused on the outcome you deliver\n\n"
            f"ABOUT (fill from your own facts, 3 short paragraphs):\n"
            f"  1. Who you help and the result you create.\n"
            f"  2. Two concrete things you have actually done (use your own numbers).\n"
            f"  3. What you are looking for next + one call to action.\n\n"
            f"EXPERIENCE BULLETS — one per role, each with verb + object + result:\n"
            f"  • Action you took → what it changed (use only your real details).\n\n"
            f"Rules applied: no invented titles, dates, employers or metrics.")


class BrandingIn(BaseModel):
    facts: str = Field(min_length=5, max_length=6000)
    niche: str | None = Field(default=None, max_length=120)


@router.post("/branding")
def branding(body: BrandingIn):
    result = ai_router.generate(
        f"Developer-branding content ideas using ONLY these facts: {body.facts}\n"
        f"Niche: {body.niche or 'general tech'}",
        module="linkedin.branding",
        fallback=lambda: _fallback_branding(body.facts, body.niche))
    return {"text": result["text"], "generated_by": result["generated_by"],
            "disclaimer": "Grounded in the facts you supplied."}


def _fallback_branding(facts: str, niche: str | None) -> str:
    n = niche or "engineering"
    snippet = " ".join(facts.split())[:160]
    return (f"[offline fallback]\n\nContent calendar for {n} (built from your facts only):\n"
            f"1. Post: 'What I learned shipping {n} work' — anchor on: {snippet}\n"
            f"2. Post: A before/after of one problem you actually solved.\n"
            f"3. Post: Your honest tooling opinion, with one real trade-off.\n"
            f"4. Article outline: {n} pitfalls you have personally hit.\n"
            f"5. Comment strategy: leave 3 substantive comments daily in your niche.\n\n"
            f"Rule: every claim must map to a fact you supplied — nothing invented.")


# ------------------------------------------------------------------- jobs -----
def _fetch_remoteok(search: str | None = None) -> tuple[list[dict], dict]:
    jobs = []
    try:
        r = httpx.get(FEEDS["remoteok"], headers=UA, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        items = data[1:] if isinstance(data, list) and data and isinstance(data[0], dict) \
            and "legal" in data[0] else (data if isinstance(data, list) else [])
        for it in items:
            jobs.append({
                "source": "remoteok", "external_id": str(it.get("id") or it.get("url")),
                "title": it.get("position") or it.get("title") or "Untitled",
                "company": it.get("company"), "location": it.get("location") or "Remote",
                "url": it.get("url"), "tags": ",".join(it.get("tags") or []),
                "salary": (f"{it.get('salary_min')}-{it.get('salary_max')}"
                           if it.get("salary_min") else None),
                "raw": it,
            })
        return jobs, {"name": "remoteok", "ok": True, "count": len(items)}
    except Exception as exc:
        return jobs, {"name": "remoteok", "ok": False, "error": exc.__class__.__name__,
                      "count": 0}


def _fetch_remotive(search: str | None = None) -> tuple[list[dict], dict]:
    jobs = []
    try:
        params = {"search": search} if search else {}
        r = httpx.get(FEEDS["remotive"], headers=UA, params=params, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        items = r.json().get("jobs", [])
        for it in items:
            jobs.append({
                "source": "remotive", "external_id": str(it.get("id")),
                "title": it.get("title") or "Untitled",
                "company": it.get("company_name"),
                "location": it.get("candidate_required_location") or "Remote",
                "url": it.get("url"), "tags": ",".join(it.get("tags") or []),
                "salary": it.get("salary") or None, "raw": it,
            })
        return jobs, {"name": "remotive", "ok": True, "count": len(items)}
    except Exception as exc:
        return jobs, {"name": "remotive", "ok": False, "error": exc.__class__.__name__,
                      "count": 0}


def _fetch_feeds(search: str | None = None) -> tuple[list[dict], list[dict]]:
    """Fetch both permitted feeds concurrently so an unreachable host cannot stall the API."""
    jobs, sources = [], []
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="feed")
    try:
        futures = [pool.submit(_fetch_remoteok, search),
                   pool.submit(_fetch_remotive, search)]
        for fut in futures:
            try:
                got, src = fut.result(timeout=FEED_DEADLINE)
            except Exception as exc:
                got, src = [], {"name": "feed", "ok": False,
                                "error": ("timeout" if isinstance(exc, TimeoutError)
                                          else exc.__class__.__name__), "count": 0}
            jobs.extend(got)
            sources.append(src)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return jobs, sources


def _cache_fresh() -> bool:
    row = db.one("SELECT MAX(fetched_at) t FROM job_listings")
    if not row or not row["t"]:
        return False
    from datetime import datetime, timezone
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(row["t"])
        return age.total_seconds() < CACHE_MINUTES * 60
    except ValueError:
        return False


@router.get("/jobs")
def jobs(skills: str | None = None, remote: bool = True, refresh: bool = False):
    sources: list[dict] = []
    stale = False
    if refresh or not _cache_fresh():
        fetched, sources = _fetch_feeds(search=(skills.split(",")[0] if skills else None))
        if fetched:
            for j in fetched:
                db.execute(
                    "INSERT OR IGNORE INTO job_listings(source,external_id,title,company,"
                    "location,url,tags,salary,fetched_at,raw) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (j["source"], j["external_id"], j["title"], j["company"], j["location"],
                     j["url"], j["tags"], j["salary"], now_iso(), db.dumps(j["raw"])))
        elif not db.one("SELECT id FROM job_listings LIMIT 1"):
            raise NexusError("job feeds unreachable and no cached listings exist",
                             code="network_error", status=502)
        else:
            stale = True
    rows = db.query("SELECT * FROM job_listings ORDER BY id DESC LIMIT 200")
    if skills:
        wanted = [s.strip().lower() for s in skills.split(",") if s.strip()]
        if wanted:
            def score(r):
                hay = f"{r['title']} {r['tags'] or ''} {r['company'] or ''}".lower()
                return sum(1 for w in wanted if w in hay)
            rows = [r for r in rows if score(r) > 0]
            rows.sort(key=lambda r: -score(r))
    out = [{k: r[k] for k in ("id", "source", "title", "company", "location", "url",
                              "tags", "salary", "fetched_at")} for r in rows]
    if remote:
        out = [r for r in out if "remote" in (r["location"] or "").lower()
               or r["source"] in ("remoteok", "remotive")]
    activity.info("linkedin", f"job discovery: {len(out)} listings",
                  {"stale": stale, "sources": [s["name"] for s in sources]})
    return {"jobs": out, "sources": sources, "stale": stale,
            "fetched_at": now_iso(),
            "note": "Sources: RemoteOK & Remotive public APIs (permitted, attributed). "
                    "LinkedIn itself is never scraped."}


class MatchIn(BaseModel):
    profile_skills: list[str] = Field(default_factory=list, max_length=60)
    job_id: int


@router.post("/jobs/match")
def jobs_match(body: MatchIn):
    job = db.one("SELECT * FROM job_listings WHERE id=?", (body.job_id,))
    if not job:
        raise NexusError("job not found", code="not_found", status=404)
    want = [s.strip().lower() for s in body.profile_skills if s.strip()]
    have = set()
    for w in want:
        have.update(x.strip().lower() for x in re.split(r"[,;/+]| and ", w) if x.strip())
    hay = f"{job['title']} {(job['tags'] or '')} {job['company'] or ''}".lower()
    job_tokens = set(re.findall(r"[a-z0-9+#.]{2,}", hay))
    matched = sorted(t for t in have if t in job_tokens)
    missing = sorted(t for t in job_tokens
                     if t not in have and len(t) > 3
                     and t not in {"remote", "senior", "lead", "engineer", "developer"})
    score = round(100 * len(matched) / max(1, min(len(have) or 1, 8)))
    score = min(score, 100)
    return {"job": {k: job[k] for k in ("id", "title", "company", "url", "tags")},
            "score": score, "matched": matched, "missing_top": missing[:8],
            "breakdown": {"your_skills": len(have), "matched": len(matched)},
            "note": "Transparent token-overlap score — not an ATS or recruiter ranking."}


# -------------------------------------------------------------- truthful CV ---
class CvProfile(BaseModel):
    name: str | None = None
    headline: str | None = None
    contact: dict | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[dict] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)
    projects: list[dict] = Field(default_factory=list)
    summary: str | None = None


class CvIn(BaseModel):
    profile: CvProfile
    target_role: str | None = Field(default=None, max_length=120)


_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _validate_no_new_facts(text: str, profile: CvProfile) -> tuple[bool, list[str]]:
    """Reject output containing years/employers/degrees absent from the input facts."""
    corpus = db.dumps(profile.model_dump()).lower()
    problems = []
    for m in _YEAR_RE.finditer(text):
        token = m.group(0)
        if token not in corpus:
            problems.append(f"new date: {token}")
    for m in re.finditer(r"\b([A-Z][A-Za-z0-9&.]+(?:\s+[A-Z][A-Za-z0-9&.]+)+)\b", text):
        phrase = m.group(1)
        if phrase.lower() in {"not provided", "university of", "bachelor of"}:
            continue
        if phrase.lower() not in corpus and len(phrase.split()) <= 6:
            # allow common headings
            if phrase.lower() not in {"work experience", "education", "skills",
                                      "projects", "contact information"}:
                problems.append(f"possible new entity: {phrase}")
    return (len(problems) == 0, problems)


@router.post("/cv")
def cv_generate(body: CvIn):
    p = body.profile
    lines = []
    lines.append(f"# CV — {p.name or '[not provided]'}")
    if p.headline:
        lines.append(f"\n**{p.headline}**")
    contact_bits = [f"{k}: {v}" for k, v in (p.contact or {}).items() if v]
    lines.append("\n## Contact\n" + ("\n".join(contact_bits) if contact_bits
                                     else "[not provided]"))
    lines.append("\n## Summary\n" + (p.summary or "[not provided]"))
    lines.append("\n## Skills")
    lines.append("\n".join(f"- {s}" for s in p.skills) if p.skills else "[not provided]")
    lines.append("\n## Experience")
    if p.experience:
        for e in p.experience:
            lines.append(f"\n### {e.get('role') or '[not provided]'} — "
                         f"{e.get('company') or '[not provided]'} "
                         f"({e.get('dates') or '[not provided]'})")
            bullets = e.get("bullets") or []
            if bullets:
                lines.extend(f"- {b}" for b in bullets)
            else:
                lines.append("- [not provided]")
    else:
        lines.append("\n[not provided]")
    lines.append("\n## Education")
    if p.education:
        for e in p.education:
            lines.append(f"- {e.get('degree') or '[not provided]'} — "
                         f"{e.get('institution') or '[not provided]'} "
                         f"({e.get('dates') or '[not provided]'})")
    else:
        lines.append("[not provided]")
    if p.projects:
        lines.append("\n## Projects")
        for pr in p.projects:
            lines.append(f"- {pr.get('name', '[not provided]')}: "
                         f"{pr.get('description', '[not provided]')}")
    cv_text = "\n".join(lines)

    missing = []
    for field, label in (("name", "name"), ("headline", "headline"),
                         ("summary", "summary")):
        if not getattr(p, field):
            missing.append(label)
    if not p.skills:
        missing.append("skills")
    if not p.experience:
        missing.append("experience")
    if not p.education:
        missing.append("education")

    # Optional AI polish — only accepted if it introduces no new facts.
    generated_by = "deterministic"
    if body.target_role:
        res = ai_router.generate(
            f"Polish this CV summary for {body.target_role}, reusing ONLY these facts:\n"
            + cv_text[:3000],
            module="linkedin.cv",
            system="Do not add any fact not present in the input.",
            fallback=lambda: None)
        if res["generated_by"] != "fallback" and res["text"]:
            ok, problems = _validate_no_new_facts(res["text"], p)
            if ok:
                generated_by = res["generated_by"]
            else:
                activity.warn("linkedin", "CV AI polish rejected by truthfulness guard",
                              {"problems": problems[:5]})
    return {"cv_markdown": cv_text, "missing": missing, "generated_by": generated_by,
            "truthfulness": "All entries built strictly from your profile; missing "
                            "fields show [not provided]. Nothing was invented."}


class CoverIn(BaseModel):
    profile: CvProfile
    job_description: str = Field(min_length=10, max_length=8000)
    company: str | None = Field(default=None, max_length=120)


@router.post("/cover-letter")
def cover_letter(body: CoverIn):
    skills = [s for s in body.profile.skills][:6]
    job = {"company": body.company or "your team", "title": body.profile.headline or "the role"}
    fallback_text = ai_fallback.cover_letter(body.profile.model_dump(), job, skills)
    result = ai_router.generate(
        "Write a truthful cover letter. Facts allowed: "
        + db.dumps(body.profile.model_dump())[:2500]
        + "\nJob: " + body.job_description[:1500]
        + (f"\nAddress it to: {body.company}" if body.company else ""),
        module="linkedin.cover",
        system="Never invent employers, dates, degrees or metrics.",
        fallback=lambda: fallback_text)
    text = result["text"] or ""
    generated_by = result["generated_by"]
    reasons: list[str] = []
    if generated_by != "fallback" and text:
        # A model may only be used if it honours the supplied facts.
        if body.company and body.company.lower() not in text.lower():
            reasons.append("drops the supplied company name")
        if body.profile.name and body.profile.name.lower() not in text.lower():
            reasons.append("drops the supplied applicant name")
        for m in _YEAR_RE.finditer(text):
            if m.group(0) not in db.dumps(body.profile.model_dump()):
                reasons.append(f"invents the date {m.group(0)}")
                break
        for skill in skills[:4]:
            if skill.lower() not in text.lower() and skill.lower() not in \
                    body.job_description.lower():
                reasons.append(f"drops the supplied skill '{skill}'")
                break
    if reasons:
        activity.warn("linkedin", "cover letter AI draft rejected by truthfulness guard",
                      {"problems": reasons[:5]})
        text, generated_by = fallback_text, "fallback"
    return {"text": text, "generated_by": generated_by,
            "rejected_model_reasons": reasons or None,
            "disclaimer": "Uses only your supplied facts; review before sending. "
                          "Sending requires owner approval."}


# ------------------------------------------------------------- applications ---
class ApplicationIn(BaseModel):
    job_id: int | None = None
    role: str = Field(min_length=2, max_length=200)
    company: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=4000)


@router.get("/applications")
def applications():
    return db.query("SELECT * FROM job_applications ORDER BY id DESC LIMIT 200")


@router.post("/applications", status_code=201)
def application_add(body: ApplicationIn):
    aid = db.execute(
        "INSERT INTO job_applications(job_id,role,company,status,created_ts,notes) "
        "VALUES(?,?,?,'draft',?,?)",
        (body.job_id, body.role, body.company, now_iso(), body.notes))
    activity.info("linkedin", f"application tracked: {body.role}")
    return db.one("SELECT * FROM job_applications WHERE id=?", (aid,))


@router.post("/applications/{app_id}/submit")
def application_submit(app_id: int):
    row = db.one("SELECT * FROM job_applications WHERE id=?", (app_id,))
    if not row:
        raise NexusError("application not found", code="not_found", status=404)
    payload = {"application_id": app_id, "role": row["role"], "company": row["company"]}
    try:
        approvals.require_approved(
            "apply.linkedin", f"Submit application: {row['role']} @ {row['company'] or '?'}",
            payload)
    except ApprovalRequired as exc:
        return {"code": "approval_required", "approval_id": exc.approval_id,
                "kind": exc.kind,
                "message": "Job applications require owner approval. Approve, then retry."}
    # No official LinkedIn application API exists for personal accounts — we never
    # simulate submission. The approved state prepares everything for manual sending.
    db.execute("UPDATE job_applications SET status='ready_for_manual_submission', "
               "updated_ts=? WHERE id=?", (now_iso(), app_id))
    activity.info("linkedin", "application approved for manual submission",
                  {"id": app_id})
    return {"code": "ready_for_manual_submission", "application_id": app_id,
            "message": "Approved. LinkedIn offers no official application API for "
                       "personal accounts, so this is prepared for you to submit "
                       "manually at the listing URL — nothing was sent automatically."}
