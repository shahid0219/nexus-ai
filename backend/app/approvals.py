"""Approval gate — every publish/message/apply/delete/financial action passes here.

Flow (SECURITY.md §2): module calls require_approved(); if no approved record matches
the (kind, payload) hash, a pending row is created and ApprovalRequired is raised
(HTTP 409). The owner approves in the dashboard; the client retries the request and it
then executes. Rejections store a reason. All decisions are audited.
"""
import hashlib

from . import db
from .security import ApprovalRequired, now_iso

# Every kind that must pass the gate. Callers are asserted against this set so a
# typo cannot silently skip the approval requirement.
GATED_KINDS = {
    "publish.instagram",     # instagram.py — publish a post/reel
    "upload.youtube",        # youtube.py    — upload a video
    "apply.linkedin",        # linkedin.py   — hand an application off for submission
    "delete.data",           # instagram.py  — delete a calendar entry
    "revenue.record",        # monetisation.py — record money in
}
GATED_PREFIXES = ("account.delete.",)   # accounts.py — delete stored credentials


def payload_hash(kind: str, payload: dict) -> str:
    canonical = db.dumps({"kind": kind, "payload": payload or {}})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def find_pending(kind: str, payload_hash_: str) -> dict | None:
    return db.one(
        "SELECT * FROM approvals WHERE kind=? AND payload_hash=? AND status='pending' "
        "ORDER BY id DESC LIMIT 1", (kind, payload_hash_))


def find_approved(kind: str, payload_hash_: str) -> dict | None:
    return db.one(
        "SELECT * FROM approvals WHERE kind=? AND payload_hash=? AND status='approved' "
        "AND used_ts IS NULL ORDER BY id DESC LIMIT 1", (kind, payload_hash_))


def _assert_gated(kind: str) -> None:
    if kind in GATED_KINDS or kind.startswith(GATED_PREFIXES):
        return
    raise ValueError(f"approval kind '{kind}' is not declared in approvals.GATED_KINDS")


def consume(approval_id: int) -> None:
    """Mark an approval as used — one approval authorises exactly one action."""
    db.execute("UPDATE approvals SET used_ts=? WHERE id=?", (now_iso(), approval_id))


def create(kind: str, title: str, payload: dict) -> dict:
    _assert_gated(kind)
    h = payload_hash(kind, payload)
    existing = find_pending(kind, h)
    if existing:
        return existing
    aid = db.execute(
        "INSERT INTO approvals(ts,kind,title,payload,payload_hash,status) VALUES(?,?,?,?,?,'pending')",
        (now_iso(), kind, title, db.dumps(payload or {}), h))
    row = db.one("SELECT * FROM approvals WHERE id=?", (aid,))
    from . import activity
    activity.info("approvals", f"approval requested: {kind}", {"title": title, "id": aid})
    return row


def require_approved(kind: str, title: str, payload: dict) -> dict:
    """Return the approved record (consuming it), or create a pending one and raise 409.

    Approvals are single-use: once returned here the record is marked used, so a stale
    approval can never authorise a second identical action.
    """
    _assert_gated(kind)
    h = payload_hash(kind, payload)
    approved = find_approved(kind, h)
    if approved:
        consume(approved["id"])
        return approved
    row = find_pending(kind, h) or create(kind, title, payload)
    raise ApprovalRequired(row["id"], kind, title)


def decide(approval_id: int, status: str, reason: str | None = None,
           actor: str = "owner") -> dict:
    if status not in ("approved", "rejected"):
        raise ValueError("status must be approved or rejected")
    row = db.one("SELECT * FROM approvals WHERE id=?", (approval_id,))
    if not row:
        raise KeyError(f"approval {approval_id} not found")
    if row["status"] != "pending":
        return row  # idempotent
    db.execute(
        "UPDATE approvals SET status=?, decided_ts=?, decided_by=?, reason=? WHERE id=?",
        (status, now_iso(), actor, reason, approval_id))
    from . import activity
    activity.info("approvals", f"{status}: {row['kind']}",
                  {"id": approval_id, "reason": reason})
    return db.one("SELECT * FROM approvals WHERE id=?", (approval_id,))


def list_approvals(status: str | None = None, limit: int = 100) -> list[dict]:
    if status:
        rows = db.query(
            "SELECT * FROM approvals WHERE status=? ORDER BY id DESC LIMIT ?",
            (status, limit))
    else:
        rows = db.query("SELECT * FROM approvals ORDER BY id DESC LIMIT ?", (limit,))
    return rows
