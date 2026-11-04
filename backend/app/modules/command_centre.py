"""Command Centre — health, system status, logs, tasks, stats, approvals, AI endpoint."""
import platform
import shutil
import sys
import time

import psutil
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from .. import activity, approvals, config, db, ollama_client, process
from ..security import ApprovalRequired, NexusError, clamp, redact

router = APIRouter(prefix="/api", tags=["command"])

_PROCESS = psutil.Process()
_START = time.time()


# ---------------------------------------------------------------- health ----
@router.get("/health")
def health():
    ol = ollama_client.health()
    return {
        "status": "ok",
        "name": config.APP_NAME,
        "version": config.VERSION,
        "ollama": ol,
        "db": {"size": db.db_size(), "path": str(config.DB_PATH)},
        "frontend_built": config.frontend_built(),
        "uptime_s": int(time.time() - _START),
    }


# ------------------------------------------------------------- system -------
def _ffmpeg_version() -> str | None:
    if not config.ffmpeg_path():
        return None
    try:
        out = process.run(["ffmpeg", "-version"], timeout=15)
        first = (out["stdout"] or out["stderr"]).strip().splitlines()[0]
        if "version" in first:
            return first.split("version", 1)[1].strip().split(" ")[0].strip() or first[:60]
        return first[:60]
    except NexusError:
        return None


def _ollama_version() -> str | None:
    try:
        import httpx
        r = httpx.get(f"{config.OLLAMA_URL}/api/version", timeout=2.0)
        if r.status_code == 200:
            return r.json().get("version")
    except Exception:
        pass
    return None


@router.get("/system/status")
def system_status():
    mem = psutil.virtual_memory()
    try:
        disk = psutil.disk_usage(str(config.ROOT))
        disk_pct, disk_free = disk.percent, disk.free
    except OSError:
        disk_pct, disk_free = None, None
    return {
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python": sys.version.split()[0],
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "cpu_cores": psutil.cpu_count(logical=True),
        "ram": {"total_gb": round(mem.total / 2**30, 1),
                "used_pct": mem.percent,
                "available_gb": round(mem.available / 2**30, 1)},
        "disk": {"used_pct": disk_pct, "free_gb": round(disk_free / 2**30, 1) if disk_free else None},
        "tools": {
            "ffmpeg": _ffmpeg_version(),
            "node": shutil.which("node") is not None,
            "git": shutil.which("git") is not None,
            "gh": shutil.which("gh") is not None,
            "ollama": _ollama_version(),
            "ollama_running": ollama_client.health()["available"],
        },
        "ai_models": ollama_client.health()["models"],
        "frontend_built": config.frontend_built(),
        "db_size": db.db_size(),
        "uptime_s": int(time.time() - _START),
        "port": config.PORT,
    }


# ------------------------------------------------------------- logs/tasks ---
@router.get("/logs")
def get_logs(limit: int = Query(100, le=500), level: str | None = None,
             q: str | None = None):
    return activity.logs(limit=clamp(limit, 1, 500, 100), level=level, q=q)


@router.get("/tasks")
def get_tasks(limit: int = Query(50, le=500)):
    return activity.tasks(limit=clamp(limit, 1, 500, 50))


# --------------------------------------------------------------- stats ------
@router.get("/stats")
def stats():
    pending = db.one("SELECT COUNT(*) c FROM approvals WHERE status='pending'")["c"]
    planned = db.one("SELECT COUNT(*) c FROM content_calendar "
                     "WHERE status IN ('draft','planned')")["c"]
    verified = db.one("SELECT COALESCE(SUM(amount),0) s FROM revenue_events "
                      "WHERE verified=1")["s"]
    unverified = db.one("SELECT COALESCE(SUM(amount),0) s FROM revenue_events "
                        "WHERE verified=0")["s"]
    jobs = db.one("SELECT COUNT(*) c FROM job_listings")["c"]
    leads = db.one("SELECT COUNT(*) c FROM freelance_leads")["c"]
    today = db.one("SELECT COUNT(*) c FROM tasks WHERE ts >= date('now')")["c"]
    ai_today = db.one("SELECT COUNT(*) c FROM ai_calls WHERE ts >= date('now')")["c"]
    runs = db.one("SELECT COUNT(*) c FROM automation_runs WHERE ts >= date('now')")["c"]
    return {
        "approvals_pending": pending,
        "calendar_planned": planned,
        "revenue_verified_total": verified,
        "revenue_unverified_total": unverified,
        "jobs_discovered": jobs,
        "freelance_leads": leads,
        "tasks_today": today,
        "ai_calls_today": ai_today,
        "automation_runs_today": runs,
    }


# ----------------------------------------------------------- approvals ------
class ApprovalCreate(BaseModel):
    kind: str = Field(min_length=3, max_length=80)
    title: str = Field(min_length=3, max_length=200)
    payload: dict = Field(default_factory=dict)


class Decision(BaseModel):
    reason: str | None = None
    actor: str = "owner"


@router.get("/approvals")
def list_approvals(status: str | None = None, limit: int = Query(100, le=500)):
    return approvals.list_approvals(status=status, limit=clamp(limit, 1, 500, 100))


@router.post("/approvals", status_code=201)
def create_approval(body: ApprovalCreate):
    try:
        row = approvals.create(body.kind, body.title, body.payload)
    except ValueError as exc:
        raise NexusError(str(exc), code="unknown_approval_kind", status=400)
    return {"approval": row, "code": "pending"}


@router.post("/approvals/{approval_id}/approve")
def approve(approval_id: int, body: Decision | None = None):
    try:
        row = approvals.decide(approval_id, "approved",
                               reason=(body.reason if body else None),
                               actor=(body.actor if body else "owner"))
    except KeyError as exc:
        raise NexusError(str(exc), code="not_found", status=404)
    return {"approval": row, "code": "approved",
            "hint": "retry the original request to execute it"}


@router.post("/approvals/{approval_id}/reject")
def reject(approval_id: int, body: Decision | None = None):
    try:
        row = approvals.decide(approval_id, "rejected",
                               reason=(body.reason if body else "rejected by owner"),
                               actor=(body.actor if body else "owner"))
    except KeyError as exc:
        raise NexusError(str(exc), code="not_found", status=404)
    return {"approval": row, "code": "rejected"}


# ------------------------------------------------------------------ ai ------
class AiRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    module: str = Field(default="general", max_length=40)
    system: str | None = Field(default=None, max_length=2000)
    max_tokens: int | None = None


@router.post("/ai/generate")
def ai_generate(body: AiRequest):
    from .. import ai_fallback
    result = ollama_client.generate(
        body.prompt, module=body.module, system=body.system,
        max_tokens=body.max_tokens,
        fallback=lambda: ai_fallback.general(body.prompt))
    if not result["text"]:
        raise NexusError("AI produced no output and no fallback was available",
                         code="ai_unavailable", status=503)
    return result
