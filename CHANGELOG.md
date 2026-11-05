# CHANGELOG.md — NEXUS AI

All notable changes to this project. Format loosely follows Keep a Changelog.
This is a personal local-first project; versions are milestones, not releases.

## [1.2.0] — 2026-11-05

Deployment hardening. The Docker image was built and run for real; three issues
only appeared once the app ran outside the developer's Windows checkout.

### Added
- `Dockerfile` — two-stage build (Node 20 → React bundle, `python:3.10-slim`
  runtime). Serves API and dashboard from one origin, runs as uid 10001,
  declares a `/api/health` `HEALTHCHECK`, and persists `/app/data` as a volume.
- `.dockerignore` — excludes git history, `data/`, `*.db`, credentials, and
  `node_modules` from the build context.
- `DEPLOYMENT.md` — Windows, Docker, bare-metal, configuration, and the security
  posture, including what is deliberately *not* deployed.
- `backend/tests/test_deployment.py` — 6 tests for the fixes below.

### Fixed
- **`/api/github/status` returned 503 in any deployment without git.** The
  endpoint now reports `available: false` with an explanation instead of failing,
  and the GitHub page renders a notice. GitHub tooling also now requires the
  workspace to be a git checkout, not just a `git` binary.
- **Video rendering required hardcoded Windows font paths.**
  `C:/Windows/Fonts/arialbd.ttf` does not exist in a Linux image, so render
  failed with `no TTF font found`. Fonts are now discovered across Windows,
  Linux, macOS and a bundled `tools/fonts` directory; the image installs
  `fonts-dejavu-core` and the error message names the fix.
- `Dockerfile` installs `git` and `ca-certificates` so repository features work
  when a checkout is mounted.

### Verified in the running container
- `Up (healthy)`; `/api/health` reports `frontend_built: true`.
- 16 GET endpoints → 0 failures.
- `POST /api/youtube/render` → MP4 validated by `ffprobe` at exactly
  `duration=4.000000`; thumbnail pipeline used the Debian font.
- Data and artifacts survived `docker restart`.
- Process runs as `uid=10001(nexus)`, not root.

**Tests: 119 passed, 1 skipped. `pyflakes`: 0 warnings.**

## [1.1.1] — 2026-11-05

Bug-fix pass following a deliberate defect hunt. Two defects were silently
degrading behaviour while HTTP responses still looked healthy.

### Fixed
- **All Instagram/content AI fallbacks raised `NameError`.** The handlers
  imported `json` inside the function body *after* the fallback lambda that used
  it, making `json` an unbound local. Every offline generation logged
  `fallback_error:NameError` and the primary fallback never ran (a second code
  path masked it in the response). `json` is now imported once at module scope.
  Affected: `instagram.profile`, `instagram.niche`, `instagram.reels`,
  `instagram.captions`, `content.audience`.
- **FFmpeg/ffprobe reported missing when installed but absent from PATH.** The
  machine's user PATH is truncated, so `shutil.which` failed and video render
  returned `tool_missing`. `config._find_tool()` now falls back to known install
  locations, including WinGet versioned package folders; `process.resolve()`
  uses the same lookup so the subprocess allowlist and the API agree.
- Removed 19 unused imports/locals across 9 backend modules (`pyflakes` clean).
- Removed 7 unused React imports across 5 pages.

### Added
- `backend/tests/test_fallback_regression.py` — 6 tests pinning the fallback fix
  and asserting no `fallback_error%` status can ever be written.
- `backend/tests/test_tools.py` — 7 tests for tool discovery, `process.resolve`
  parity, and that no shell is ever allowlisted.

**Tests: 113 passed, 1 skipped. `pyflakes`: 0 warnings.**

## [1.1.0] — 2026-11-05

Remediation & activation session: real AI provider routing, GitHub tooling,
Meta OAuth, and a Settings dashboard. 99 tests passing.

### Added — AI provider router
- One `ai_router` module now serves **every** AI feature (previously the
  Ollama client was called per module). Provider chain, in priority order:
  DeepSeek → Groq → OpenRouter → Google Gemini → **Ollama (local)** →
  deterministic templates. Only DeepSeek-classified paid keys would ever run a
  paid call; without stored credentials each provider is skipped honestly.
- Failover policy per request: model-not-found/auth/quota errors are
  classified distinctly, cool a provider down (quota 900 s, auth 1800 s,
  404 3600 s, network 120 s), and automatically move to the next healthy
  provider. Cooldown state is persisted in a new `ai_provider_state` table.
- Truthful metadata on every generation: `provider`, `provider_label`, `model`,
  `fallback`, `latency_ms`, `tokens_in/out`, `ts`, plus a per-attempt trace.
- Ollama model selection is now **size-aware**: files larger than
  `NEXUS_AI_MAX_MODEL_GB` (default 5.5 GB) can never be selected on a 4 GB card.
- `/api/ai/status`, `/api/ai/test` (lists models, never burns quota),
  `/api/ai/order`, `/api/ai/model`, `/api/ai/stream` (SSE), and
  `POST/DELETE /api/ai/provider/credentials` for owner-supplied keys — the key is
  stored locally in `data/credentials.json` and never echoed back.

### Added — GitHub
- New `github` module + dashboard page. Repository status (remote, branch, dirty
  count, ahead/behind, last commit), a **10-pattern secret scanner** that blocks
  any commit or push until clean, a `commit` endpoint that refuses protected
  paths (credentials, `.env`, node_modules, dist, caches), a push endpoint, and
  a remote verification endpoint comparing local vs `origin` head.
- Public-profile preparation: preview endpoint derives technologies only from
  real public repos; applying any change requires an
  `github.profile.update` approval (now in `GATED_KINDS`).

### Added — Meta/Instagram OAuth
- Official Facebook OAuth dialog + manual code exchange (matches the YouTube
  flow), long-lived token exchange, identity/permission verification against
  `/me`, `/me/accounts` and `/me/permissions`, auto-detection of the linked
  Instagram professional account, and honest
  `blocked_by_permission` / missing-professional-account states.
- Instagram Studio gained a **Connection** tab: app-id/secret storage (never
  returned by the API), authorisation flow, verification display.

### Added — dashboard
- New **AI Settings** page: active provider + model, provider priority with
  ↑/↓ reordering, per-provider health/latency/last error, key management,
  a "Test all providers" action, and a live generate box with attempt trace.
- New **GitHub** page: connection card, secret scan, safe commit/push form,
  remote verification, and profile preview.
- Dashboard shows the active AI provider and links to settings.

### Fixed
- Cover letters produced by a model could drop the supplied company or
  applicant name; the CV/cover-letter truthfulness guard now **rejects and
  replaces** any model draft that misses supplied facts (regression-tested via
  the live Ollama path).
- `credentials.public_view` now reports `has_api_key` for AI providers without
  leaking the key.

### Verified live (this session)
- Ollama started and serving: `qwen2.5-coder:3b` answered `NEXUS_LOCAL_OK` /
  `NEXUS_API_OK` through both the module and the HTTP API.
- Streaming endpoint: 2 delta chunks + done event over 447 ms.
- FFmpeg render produced a real 4.0 s MP4 validated by ffprobe.
- Scheduler restart semantics verified against persisted `last_run_ts`.
- Secret scan over the full tree: clean.

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
- Job and trend feeds could stall a request for 30–35 s when an upstream host
  was unreachable; both now fetch concurrently under a hard 8 s deadline,
  shut the pool down without waiting, and fall back to cache (or an honest
  `network_error` 502 when no cache exists).

### Known limitations (unchanged, by design)
- Instagram and YouTube analytics stay `requires_auth` until real owner
  credentials are configured — no synthetic metrics are ever produced.
- Voiceover requires Windows SAPI (`pyttsx3`); without it the endpoint returns a
  structured `tts_unavailable` error.
- Ollama is optional; the fallback engine keeps every feature usable offline.
