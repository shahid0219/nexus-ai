"""Structured activity log + task history (redacted before persistence)."""
import time

from . import db
from .security import now_iso, redact


def log(level: str, module: str, message: str, detail=None) -> None:
    level = level if level in ("debug", "info", "warn", "error") else "info"
    detail_txt = db.dumps(detail) if isinstance(detail, (dict, list)) else (str(detail) if detail else None)
    db.execute(
        "INSERT INTO activity_log(ts,level,module,message,detail) VALUES(?,?,?,?,?)",
        (now_iso(), level, module, redact(message), redact(detail_txt)),
    )


def info(module: str, message: str, detail=None) -> None:
    log("info", module, message, detail)


def warn(module: str, message: str, detail=None) -> None:
    log("warn", module, message, detail)


def error(module: str, message: str, detail=None) -> None:
    log("error", module, message, detail)


def logs(limit: int = 100, level: str | None = None, q: str | None = None) -> list[dict]:
    sql = "SELECT * FROM activity_log"
    clauses, params = [], []
    if level:
        clauses.append("level=?")
        params.append(level)
    if q:
        clauses.append("(message LIKE ? OR module LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, params)


class TaskTimer:
    """Context manager recording a task row with duration and status."""

    def __init__(self, module: str, name: str, detail: str | None = None):
        self.module = module
        self.name = name
        self.detail = detail
        self.started = 0.0

    def __enter__(self):
        self.started = time.time()
        info(self.module, f"started: {self.name}")
        return self

    def __exit__(self, exc_type, exc, tb):
        duration_ms = int((time.time() - self.started) * 1000)
        if exc is None:
            db.execute(
                "INSERT INTO tasks(ts,module,name,status,duration_ms,detail) VALUES(?,?,?,?,?,?)",
                (now_iso(), self.module, self.name, "ok", duration_ms, self.detail))
            info(self.module, f"finished: {self.name} ({duration_ms} ms)")
        else:
            db.execute(
                "INSERT INTO tasks(ts,module,name,status,duration_ms,detail) VALUES(?,?,?,?,?,?)",
                (now_iso(), self.module, self.name, "failed", duration_ms,
                 redact(f"{exc.__class__.__name__}: {exc}")))
            error(self.module, f"failed: {self.name}", str(exc))
        return False  # never swallow


def tasks(limit: int = 50) -> list[dict]:
    return db.query("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,))
