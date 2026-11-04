"""Command Centre — health, system status, logs, tasks, stats, approvals, AI endpoint."""
import platform
import shutil
import sys
import time

import psutil
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from .. import activity, ai_router, approvals, config, db, ollama_client, process
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
    ol = ollama_client.health()
    ai = ai_router.status()
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
            "ollama_running": ol["available"],
        },
        "ai_models": ol["models"],
        "ai_provider": {"active": ai["active"], "active_label": ai["active_label"],
                        "order": ai["order"]},
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
    result = ai_router.generate(
        body.prompt, module=body.module, system=body.system,
        max_tokens=body.max_tokens,
        fallback=lambda: ai_fallback.general(body.prompt))
    if not result["text"]:
        raise NexusError("AI produced no output and no fallback was available",
                         code="ai_unavailable", status=503)
    return result


# ------------------------------------------------------------ ai router -----
@router.get("/ai/status")
def ai_status():
    return ai_router.status()


@router.post("/ai/test")
def ai_test():
    return ai_router.test_all()


class AiOrderIn(BaseModel):
    order: list[str] = Field(min_length=1, max_length=12)


@router.post("/ai/order")
def ai_order(body: AiOrderIn):
    return {"order": ai_router.set_order(body.order),
            "active": ai_router.status()["active"]}


class AiModelIn(BaseModel):
    provider: str = Field(min_length=2, max_length=40)
    model: str = Field(default="", max_length=120)


@router.post("/ai/model")
def ai_model(body: AiModelIn):
    if body.provider not in ai_router.PROVIDERS:
        raise NexusError(f"unknown provider: {body.provider}", code="unknown_provider",
                         status=404)
    return {"override": ai_router.set_model_override(body.provider, body.model),
            "status": ai_router.status()}


class AiProviderKeyIn(BaseModel):
    provider: str = Field(min_length=2, max_length=40)
    api_key: str = Field(min_length=8, max_length=400)


@router.post("/ai/provider/credentials")
def ai_provider_credentials(body: AiProviderKeyIn):
    """Store a remote provider key. The key is never echoed back."""
    from .. import credentials
    provider = body.provider.lower().strip()
    spec = ai_router.PROVIDERS.get(provider)
    if not spec or spec.kind != "remote":
        raise NexusError(f"{provider} is not a remote provider", code="invalid_provider",
                         status=400)
    view = credentials.set_provider(provider, {"api_key": body.api_key})
    activity.info("ai", f"{provider} API key stored locally")
    return {"code": "stored", "provider": provider,
            "present": view.get("present"), "has_token": view.get("has_token"),
            "note": "Key stored in data/credentials.json (gitignored) and never returned."}


@router.delete("/ai/provider/{provider}/credentials")
def ai_provider_delete(provider: str):
    from .. import credentials
    provider = provider.lower().strip()
    if provider not in ai_router.PROVIDERS:
        raise NexusError(f"unknown provider: {provider}", code="unknown_provider",
                         status=404)
    try:
        approvals.require_approved(
            f"account.delete.{provider}",
            f"Delete stored {provider} AI credentials", {"provider": provider})
    except ApprovalRequired as exc:
        return {"code": "approval_required", "approval_id": exc.approval_id,
                "kind": exc.kind,
                "message": "Deleting credentials requires owner approval. Approve, then retry."}
    credentials.delete_provider(provider)
    activity.info("ai", f"{provider} AI credentials deleted")
    return {"code": "deleted", "provider": provider}


@router.post("/ai/stream")
def ai_stream(body: AiRequest):
    """Server-sent events. Each line is `data: <json>`; ends with a done event."""
    from fastapi.responses import StreamingResponse

    def events():
        import json as _json
        try:
            for chunk in ai_router.stream(body.prompt, module=body.module,
                                          system=body.system,
                                          max_tokens=body.max_tokens):
                yield f"data: {_json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as exc:  # never leak a stack trace to the browser
            yield ("data: " + _json.dumps({"error": redact(str(exc)[:200])}) + "\n\n")
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
