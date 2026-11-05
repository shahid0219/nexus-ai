"""Monetisation — digital products, freelance leads, affiliate research,
sponsorship opportunities, verified revenue tracking. No fabricated numbers:
revenue is verified ONLY with a payment reference (db: verified flag)."""
import csv
import io

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from .. import activity, ai_router, approvals, db
from ..security import ApprovalRequired, NexusError, now_iso

router = APIRouter(prefix="/api/monetisation", tags=["monetisation"])

# Curated, dated directory — terms must be re-verified at the source before use.
AFFILIATE_PROGRAMS = [
    {"name": "Amazon Associates", "category": "physical products",
     "terms": "Standard commission rates vary by category; qualifying purchase "
              "attribution window applies.", "source_url": "https://affiliate-program.amazon.com",
     "as_of": "2025-01"},
    {"name": "GitHub Copilot affiliate (via partner networks)", "category": "developer tools",
     "terms": "Availability and rates vary by region/network; check current terms.",
     "source_url": "https://github.com/features/copilot", "as_of": "2025-01"},
    {"name": "Canva Affiliate Program", "category": "design tools",
     "terms": "Application-based approval; commission per referred subscription.",
     "source_url": "https://www.canva.com/affiliates/", "as_of": "2025-01"},
    {"name": "Notion Affiliate Program", "category": "productivity",
     "terms": "Application-based; rewards for referred team sign-ups.",
     "source_url": "https://www.notion.com/affiliates", "as_of": "2025-01"},
    {"name": "Coursera Affiliate", "category": "education",
     "terms": "Commission on course enrolments via affiliate links; network-run.",
     "source_url": "https://about.coursera.org/affiliates", "as_of": "2025-01"},
]


# --------------------------------------------------------------- products -----
class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    idea: str | None = Field(default=None, max_length=4000)
    status: str = Field(default="idea", max_length=30)
    checklist: dict | None = None


@router.get("/products")
def products():
    return db.query("SELECT * FROM digital_products ORDER BY id DESC LIMIT 200")


@router.post("/products", status_code=201)
def product_add(body: ProductIn):
    pid = db.execute(
        "INSERT INTO digital_products(name,status,idea,checklist,created_ts) "
        "VALUES(?,?,?,?,?)",
        (body.name, body.status, body.idea, db.dumps(body.checklist or {}), now_iso()))
    activity.info("monetisation", f"product registered: {body.name}")
    return db.one("SELECT * FROM digital_products WHERE id=?", (pid,))


# ------------------------------------------------------------------ leads -----
@router.get("/leads")
def leads(limit: int = 200):
    rows = db.query("SELECT * FROM freelance_leads ORDER BY id DESC LIMIT ?", (limit,))
    feeds = db.query(
        "SELECT id, source, title, company AS client, url, tags, fetched_at "
        "FROM job_listings WHERE tags LIKE '%freelance%' OR tags LIKE '%contract%' "
        "OR title LIKE '%freelance%' OR title LIKE '%contract%' "
        "ORDER BY id DESC LIMIT ?", (limit,))
    merged = [{"source": r["source"], "title": r["title"], "client": r["client"],
               "url": r["url"], "tags": r["tags"], "fetched_at": r["fetched_at"],
               "origin": "feed"} for r in rows]
    merged += [{"source": r["source"], "title": r["title"], "client": r["client"],
                "url": r["url"], "tags": r["tags"], "fetched_at": r["fetched_at"],
                "origin": "job_feed"} for r in feeds]
    return {"leads": merged[:limit],
            "note": "Aggregated from permitted public feeds — verify each lead at source."}


# ------------------------------------------------------------- affiliates -----
@router.get("/affiliates")
def affiliates():
    return {"programs": AFFILIATE_PROGRAMS,
            "as_of": "2025-01",
            "disclaimer": "Static, dated directory — commission terms change; "
                          "verify at the official source before promoting anything."}


class AffiliateAnalyzeIn(BaseModel):
    niche: str = Field(min_length=2, max_length=120)
    audience: str | None = Field(default=None, max_length=1000)


@router.post("/affiliates/analyze")
def affiliate_analyze(body: AffiliateAnalyzeIn):
    result = ai_router.generate(
        f"Which affiliate programs fit niche '{body.niche}' "
        f"(audience: {body.audience or 'unknown'})? Programs: "
        + "; ".join(p["name"] for p in AFFILIATE_PROGRAMS),
        module="monetisation.affiliate",
        fallback=lambda: ("\n".join(
            f"- {p['name']} ({p['category']}): plausible if your audience overlaps "
            f"{body.niche}; confirm current terms at {p['source_url']}"
            for p in AFFILIATE_PROGRAMS[:4])
            + "\n\n[offline fallback — fit assessment only, no commission data fetched]"))
    return {"text": result["text"], "generated_by": result["generated_by"],
            "disclaimer": "Fit analysis only — no live commission rates were fetched."}


# ---------------------------------------------------------- sponsorships -------
class SponsorIn(BaseModel):
    brand: str = Field(min_length=2, max_length=160)
    niche: str | None = Field(default=None, max_length=120)
    contact: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)


@router.get("/sponsorships")
def sponsorships():
    return db.query("SELECT * FROM sponsorship_opportunities ORDER BY id DESC LIMIT 200")


@router.post("/sponsorships", status_code=201)
def sponsorship_add(body: SponsorIn):
    sid = db.execute(
        "INSERT INTO sponsorship_opportunities(brand,niche,contact,url,notes,created_ts) "
        "VALUES(?,?,?,?,?,?)",
        (body.brand, body.niche, body.contact, body.url, body.notes, now_iso()))
    activity.info("monetisation", f"sponsorship tracked: {body.brand}")
    return db.one("SELECT * FROM sponsorship_opportunities WHERE id=?", (sid,))


@router.post("/sponsorships/{sid}/draft")
def sponsorship_draft(sid: int):
    row = db.one("SELECT * FROM sponsorship_opportunities WHERE id=?", (sid,))
    if not row:
        raise NexusError("opportunity not found", code="not_found", status=404)
    result = ai_router.generate(
        f"Draft a short sponsorship outreach email to {row['brand']} "
        f"(niche: {row['niche'] or 'general'}). No claims beyond stated facts.",
        module="monetisation.sponsorship",
        fallback=lambda: (f"Subject: Partnership idea for {row['brand']}\n\n"
                          f"Hi {row['brand']} team,\n\n"
                          f"I create content in the {row['niche'] or 'tech'} space for a "
                          f"growing audience and would like to propose a sponsored segment "
                          f"that fits your product. Happy to share media kit and past "
                          f"performance on request.\n\n"
                          f"Best regards\n\n"
                          f"[Draft only — nothing is sent. Sending requires approval.]"))
    activity.info("monetisation", "outreach draft created (not sent)",
                  {"opportunity": sid})
    return {"text": result["text"], "generated_by": result["generated_by"],
            "status": "draft_never_sent",
            "disclaimer": "Draft only. Sending any outreach requires owner approval "
                          "and a permitted channel."}


# ---------------------------------------------------------------- revenue -----
class RevenueIn(BaseModel):
    amount: float = Field(gt=0, le=10_000_000)
    currency: str = Field(default="USD", max_length=8)
    source: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    payment_reference: str | None = Field(default=None, max_length=200)


@router.get("/revenue")
def revenue():
    events = db.query("SELECT * FROM revenue_events ORDER BY id DESC LIMIT 500")
    vt = db.one("SELECT COALESCE(SUM(amount),0) s, COUNT(*) c FROM revenue_events "
                "WHERE verified=1") or {"s": 0, "c": 0}
    ut = db.one("SELECT COALESCE(SUM(amount),0) s, COUNT(*) c FROM revenue_events "
                "WHERE verified=0") or {"s": 0, "c": 0}
    return {"events": events, "verified_total": vt["s"], "verified_count": vt["c"],
            "unverified_total": ut["s"], "unverified_count": ut["c"],
            "note": "Verified totals include only events with a payment reference."}


@router.post("/revenue", status_code=201)
def revenue_add(body: RevenueIn):
    payload = body.model_dump()
    try:
        approvals.require_approved(
            "revenue.record", f"Record revenue: {body.amount} {body.currency} "
                              f"via {body.source}", payload)
    except ApprovalRequired as exc:
        return {"code": "approval_required", "approval_id": exc.approval_id,
                "kind": exc.kind,
                "message": "Recording revenue is a financial action and requires "
                           "owner approval. Approve, then retry."}
    verified = 1 if (body.payment_reference or "").strip() else 0
    rid = db.execute(
        "INSERT INTO revenue_events(ts,amount,currency,source,description,"
        "payment_reference,verified) VALUES(?,?,?,?,?,?,?)",
        (now_iso(), body.amount, body.currency.upper()[:8], body.source,
         body.description, body.payment_reference, verified))
    activity.info("monetisation", f"revenue recorded (verified={bool(verified)})",
                  {"amount": body.amount, "source": body.source})
    row = db.one("SELECT * FROM revenue_events WHERE id=?", (rid,))
    return {"event": row, "verified": bool(verified),
            "note": None if verified else "No payment reference — counted as unverified."}


@router.get("/revenue/export")
def revenue_export():
    events = db.query("SELECT * FROM revenue_events ORDER BY id ASC")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "ts", "amount", "currency", "source", "description",
                     "payment_reference", "verified"])
    for e in events:
        writer.writerow([e["id"], e["ts"], e["amount"], e["currency"], e["source"],
                         e["description"] or "", e["payment_reference"] or "",
                         e["verified"]])
    activity.info("monetisation", f"revenue CSV exported ({len(events)} rows)")
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=nexus_revenue.csv"})
