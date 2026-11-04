# CHANGELOG.md — NEXUS AI

All notable changes to this project. Format loosely follows Keep a Changelog.
This is a personal local-first project; versions are milestones, not releases.

## [1.0.0] — 2026-11-04

First complete, working build. Everything listed below is implemented and covered
by the test suite unless explicitly marked otherwise.

### Added — core
- FastAPI application (`backend/app/main.py`) bound to `127.0.0.1:8777`, with SPA
  static hosting, CORS for the Vite dev origin, and lifespan-managed scheduler.
- SQLite persistence (stdlib `sqlite3`, WAL, foreign keys) with 24 application
  tables and idempotent schema creation plus additive migrations.
- Activity log and task history with secret redaction on every write.
- Domain error model: `ApprovalRequired` → HTTP 409 with `approval_id`,
  `NexusError` → structured `{code, detail}`.
- Subprocess allowlist (`ffmpeg`, `ffprobe`, `gh`) executed as argv lists with
  `shell=False`; anything else raises `subprocess_not_allowed`.
- Input guards: filename sanitisation, numeric clamping, redaction.

### Added — safety
- Human approval gate for publish, upload, apply, delete and financial actions.
  Approvals are payload-hashed, **single-use**, and kinds must be declared in
  `approvals.GATED_KINDS` or the call raises.
- Every publish/send path returns `requires_auth` instead of pretending to work
  when credentials are absent.
- Revenue is `verified: 1` only when a payment reference is supplied.
- CV and cover-letter generators emit only user-supplied facts; gaps render
  `[not provided]`. LinkedIn submission produces a manual hand-off, never an
  automated send.

### Added — local AI
- Ollama client with health probing, small-model preference list for 4 GB VRAM,
  a serialising lock, and a 90 s timeout.
- Deterministic fallback engine (general, captions, reels, script, profile
  analysis, niche research, topics, audience, platform content, cover letter).
- Every AI response is labelled `generated_by: ollama|fallback` and rendered as a
  badge in the UI.

### Added — studios
- **Instagram:** profile analysis, niche research, reel ideas, captions, content
  calendar (create/list/gated delete), gated publish via Meta Graph API,
  analytics with an honest `requires_auth` state.
- **YouTube:** topic research, short/long scripts, Windows SAPI voiceover, SRT
  subtitle generation with real cue timing, FFmpeg MP4 render (drawtext scenes +
  optional audio), Pillow 1280×720 thumbnails, Google OAuth (loopback on 8778
  plus manual authorization-code fallback), gated resumable upload, analytics.
- **LinkedIn:** profile improvement, developer branding, job discovery from
  RemoteOK and Remotive public feeds (attributed and cached), transparent skill
  matching, truthful CV, cover letter, application tracking with gated manual
  hand-off.

### Added — intelligence, money, automation
- **Content Intelligence:** trend clustering from Hacker News Algolia and public
  Reddit JSON with cache fallback, hypothesis-tagged audience research,
  per-platform generation with enforced character limits
  (Instagram 2200, YouTube 5000, LinkedIn 3000, X 280).
- **Monetisation:** digital products, freelance leads, a date-stamped affiliate
  directory, sponsorship tracking with local-only outreach drafts, revenue
  ledger with verification invariant, CSV export.
- **Automation:** five jobs (`daily_research`, `content_preparation`,
  `video_production`, `job_discovery`, `weekly_report`), 30 s scheduler tick,
  manual run, three attempts with exponential backoff, run history and markdown
  reports built from the real database.
- **Account Centre:** GitHub status via the system `gh` CLI (token never read),
  Meta token entry, Google OAuth client configuration, LinkedIn status; the API
  exposes credential presence only, never values.

### Added — dashboard
- React 18 + Vite 5 SPA, HashRouter, hand-written CSS design system, fully
  offline (no CDN, no fonts, no UI or chart libraries).
- Pages: Dashboard, Approvals, Instagram, YouTube, LinkedIn, Content,
  Monetisation, Automation, Accounts, Logs & Tasks.
- Every control calls a real endpoint; loading, empty, error,
  `approval_required` and `awaiting_authentication` states each look different.

### Added — packaging & docs
- `start_nexus.bat` (dependency check, first-run frontend build, optional Ollama
  start, port check, browser launch) and `stop_nexus.bat`.
- `README.md`, `ARCHITECTURE.md`, `SECURITY.md`, `NEXUS_MASTER_SPEC.md`,
  `PROJECT_STATE.md`, `TASKS.md`, `TEST_REPORT.md`.
- `pytest.ini` and a 32-case test suite (31 pass, 1 environment skip).

### Fixed during development
- Relative-import bug: modules used `from . import activity` while living in
  `app.modules`, breaking every import. All modules now use `from .. import …`.
- `youtube.render` read settings from `config` instead of `db`.
- `accounts` router paths were double-prefixed (`/api/accounts/api/accounts`).
- `ffmpeg -version` parsing returned an empty string due to leading whitespace.
- `security.now_iso` was accidentally dropped during a redaction refactor.
- `Bearer <token>` values were only partially redacted.
- `/api/automation/runs` returned HTTP 500 whenever a run existed: an `int` was
  passed where the DB helper expected a params tuple.
- Job and trend feeds could stall a request for 30 s when an upstream host was
  unreachable; both now fetch concurrently with short timeouts and fall back to
  cache (or an honest `network_error` 502 when no cache exists).

### Known limitations (unchanged, by design)
- Instagram and YouTube analytics stay `requires_auth` until real owner
  credentials are configured — no synthetic metrics are ever produced.
- Voiceover requires Windows SAPI (`pyttsx3`); without it the endpoint returns a
  structured `tts_unavailable` error.
- Ollama is optional; the fallback engine keeps every feature usable offline.
