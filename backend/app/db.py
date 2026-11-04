"""SQLite layer — schema, connections, query helpers. WAL, foreign keys on."""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(
  key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS activity_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
  level TEXT NOT NULL, module TEXT NOT NULL, message TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS tasks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, module TEXT NOT NULL,
  name TEXT NOT NULL, status TEXT NOT NULL, duration_ms INTEGER, detail TEXT);
CREATE TABLE IF NOT EXISTS approvals(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL,
  title TEXT NOT NULL, payload TEXT NOT NULL, payload_hash TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', decided_ts TEXT, decided_by TEXT, reason TEXT,
  used_ts TEXT);
CREATE TABLE IF NOT EXISTS ai_calls(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, module TEXT NOT NULL,
  model TEXT, generated_by TEXT NOT NULL, latency_ms INTEGER, prompt_chars INTEGER,
  status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS content_calendar(
  id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, platform TEXT NOT NULL,
  title TEXT NOT NULL, brief TEXT, status TEXT NOT NULL DEFAULT 'draft', created_ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS posts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT NOT NULL, content TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft', approval_id INTEGER, created_ts TEXT NOT NULL,
  published_ts TEXT, remote_id TEXT);
CREATE TABLE IF NOT EXISTS media_assets(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, path TEXT NOT NULL,
  meta TEXT, created_ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scripts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, type TEXT NOT NULL,
  content TEXT NOT NULL, created_ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS videos(
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, path TEXT,
  status TEXT NOT NULL DEFAULT 'planned', meta TEXT, created_ts TEXT NOT NULL,
  remote_id TEXT);
CREATE TABLE IF NOT EXISTS job_listings(
  id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, external_id TEXT NOT NULL,
  title TEXT NOT NULL, company TEXT, location TEXT, url TEXT, tags TEXT,
  salary TEXT, fetched_at TEXT NOT NULL, raw TEXT,
  UNIQUE(source, external_id));
CREATE TABLE IF NOT EXISTS job_applications(
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER, role TEXT NOT NULL,
  company TEXT, status TEXT NOT NULL DEFAULT 'draft', cover_letter TEXT,
  created_ts TEXT NOT NULL, updated_ts TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS niche_research(
  id INTEGER PRIMARY KEY AUTOINCREMENT, niche TEXT NOT NULL, result TEXT NOT NULL,
  generated_by TEXT NOT NULL, created_ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trends_cache(
  id INTEGER PRIMARY KEY AUTOINCREMENT, cluster_key TEXT NOT NULL, title TEXT NOT NULL,
  keywords TEXT, sources TEXT NOT NULL, fetched_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audience_research(
  id INTEGER PRIMARY KEY AUTOINCREMENT, niche TEXT NOT NULL, result TEXT NOT NULL,
  generated_by TEXT NOT NULL, created_ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS digital_products(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'idea',
  idea TEXT, checklist TEXT, created_ts TEXT NOT NULL, updated_ts TEXT);
CREATE TABLE IF NOT EXISTS freelance_leads(
  id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, title TEXT NOT NULL,
  client TEXT, url TEXT, tags TEXT, fetched_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new');
CREATE TABLE IF NOT EXISTS affiliate_programs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT,
  terms TEXT NOT NULL, source_url TEXT, verified_on TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS sponsorship_opportunities(
  id INTEGER PRIMARY KEY AUTOINCREMENT, brand TEXT NOT NULL, niche TEXT, contact TEXT,
  url TEXT, status TEXT NOT NULL DEFAULT 'researched', notes TEXT, created_ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS revenue_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, amount REAL NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD', source TEXT NOT NULL, description TEXT,
  payment_reference TEXT, verified INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS automation_jobs(
  name TEXT PRIMARY KEY, description TEXT NOT NULL, interval_minutes INTEGER,
  daily_time TEXT, enabled INTEGER NOT NULL DEFAULT 1,
  last_run_ts TEXT, last_status TEXT);
CREATE TABLE IF NOT EXISTS automation_runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT NOT NULL, ts TEXT NOT NULL,
  status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 1, detail TEXT);
CREATE TABLE IF NOT EXISTS reports(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL,
  path TEXT NOT NULL, summary TEXT);
CREATE TABLE IF NOT EXISTS ai_provider_state(
  provider TEXT PRIMARY KEY, cooldown_until REAL NOT NULL DEFAULT 0,
  last_error TEXT, last_error_class TEXT, last_ok_ts TEXT, last_latency_ms INTEGER);
CREATE TABLE IF NOT EXISTS oauth_states(
  provider TEXT PRIMARY KEY, state TEXT NOT NULL, created_ts TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', detail TEXT);
"""

DEFAULT_SETTINGS = {
    "niche": "",
    "content_topics": "",
    "auto_render": "0",
    "video_width": "1280",
    "video_height": "720",
}

DEFAULT_AUTOMATION_JOBS = [
    ("daily_research", "Fetch public trends and store clusters", 1440, None),
    ("content_preparation", "Draft calendar entries and captions for the next days", 720, None),
    ("video_production", "Prepare script, subtitles and thumbnail for the next reel", 1440, None),
    ("job_discovery", "Refresh remote job leads from permitted public feeds", 360, None),
    ("weekly_report", "Aggregate the week into a markdown report", 10080, None),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        for name, desc, interval, daily in DEFAULT_AUTOMATION_JOBS:
            conn.execute(
                "INSERT OR IGNORE INTO automation_jobs(name,description,interval_minutes,daily_time)"
                " VALUES(?,?,?,?)", (name, desc, interval, daily))
        _migrate(conn)


def _migrate(conn) -> None:
    """Additive migrations for databases created by earlier versions."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(approvals)")}
    if "used_ts" not in cols:
        conn.execute("ALTER TABLE approvals ADD COLUMN used_ts TEXT")


def query(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]


def one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    with connect() as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
        return dict(row) if row else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with connect() as conn:
        cur = conn.execute(sql, tuple(params))
        return int(cur.lastrowid or 0)


def get_setting(key: str, default: str = "") -> str:
    row = one("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    execute("INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def db_size() -> int:
    try:
        return config.DB_PATH.stat().st_size
    except OSError:
        return 0
