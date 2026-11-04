"""NEXUS AI — FastAPI entry point.

Run:  uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8777
Serves the React SPA (frontend/dist) when built, plus the whole /api surface.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import activity, config, db, security
from .approvals import ApprovalRequired
from .modules.automation import scheduler
from .routers import register

DEV_ORIGINS = [f"http://127.0.0.1:{config.DEV_PORT}",
               f"http://localhost:{config.DEV_PORT}"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    activity.info("core", f"{config.APP_NAME} v{config.VERSION} starting",
                  {"port": config.PORT, "data": str(config.DATA_DIR)})
    if not scheduler.is_alive():
        scheduler.start()
    yield
    scheduler.stop()
    activity.info("core", "shutdown complete")


app = FastAPI(title=config.APP_NAME, version=config.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApprovalRequired)
async def approval_required_handler(request: Request, exc: ApprovalRequired):
    return JSONResponse(
        status_code=409,
        content={"code": "approval_required", "approval_id": exc.approval_id,
                 "kind": exc.kind, "title": exc.title,
                 "detail": "This action requires owner approval. Approve it in the "
                           "Approval Centre, then retry."})


@app.exception_handler(security.NexusError)
async def nexus_error_handler(request: Request, exc: security.NexusError):
    return JSONResponse(status_code=exc.status,
                        content={"code": exc.code, "detail": str(exc)})


register(app)

# --- static SPA ------------------------------------------------------------
if config.frontend_built():
    assets = config.FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        target = config.FRONTEND_DIST / path
        if path and target.is_file() and str(target.resolve()).startswith(
                str(config.FRONTEND_DIST.resolve())):
            return FileResponse(target)
        return FileResponse(config.FRONTEND_DIST / "index.html")
else:
    @app.get("/", include_in_schema=False)
    async def not_built():
        return HTMLResponse(
            "<html><body style='font-family:Segoe UI,sans-serif;background:#0f1420;"
            "color:#e6e9f2;display:flex;align-items:center;justify-content:center;"
            "height:100vh'><div style='max-width:520px;text-align:center'>"
            "<h1 style='color:#9fb4ff'>NEXUS AI</h1>"
            "<p>The API is running on port "
            f"{config.PORT}, but the dashboard is not built yet.</p>"
            "<p>Run <code>start_nexus.bat</code> from the project root, or build "
            "with <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build"
            "</code>.</p>"
            "<p><a style='color:#63b3ff' href='/api/health'>/api/health</a></p>"
            "</div></body></html>")
