# TASKS.md — NEXUS AI implementation checklist

Priority: P0 = blocking core, P1 = major feature, P2 = polish. Checked = done & verified.## Phase 1 — Documentation
- [x] P0 `NEXUS_MASTER_SPEC.md`
- [x] P0 `PROJECT_STATE.md`
- [x] P0 `TASKS.md`
- [x] P0 `SECURITY.md`

## Phase 2 — GitHub
- [x] P0 Verify `gh auth status`
- [x] P0 Create/reuse private repo `shahid0219/nexus-ai`
- [x] P0 `git init` + `.gitignore` (credentials, data, node_modules, venv, dist)
- [x] P0 Commit + push docs; verify with `gh repo view`

## Phase 3 — Backend core
- [x] P0 `requirements.txt`, `backend/app/config.py`
- [x] P0 `db.py` full schema (24 tables, WAL, seeds, additive migrations)
- [x] P0 `approvals.py` gate + CRUD (payload hash, single-use, kind allowlist)
- [x] P0 `activity.py` logs + task history
- [x] P0 `process.py` subprocess allowlist (ffmpeg/ffprobe/gh)
- [x] P0 `security.py` secret redaction + input guards
- [x] P0 `main.py` FastAPI shell, `/api/health`, static SPA hosting, lifespan scheduler
- [x] P0 `routers.py` module wiring

## Phase 4 — Command Centre dashboard
- [x] P0 Vite + React scaffold, design system CSS (dark, responsive, sidebar/topbar)
- [x] P0 Dashboard page: system status, metrics, quick actions
- [x] P0 Approvals page: queue + approve/reject
- [x] P0 Logs page + Tasks history page
- [x] P1 Mobile drawer / responsive breakpoints

## Phase 5 — Local AI
- [x] P0 `ollama_client.py`: health, generate, model policy, 4GB-VRAM defaults
- [x] P0 Deterministic fallback generator (tagged, never presented as Ollama)
- [x] P0 `ai_calls` logging + `POST /api/ai/generate`

## Phase 6 — Content & video production
- [x] P1 Voiceover: `pyttsx3` → WAV (+ honest failure if SAPI missing)
- [x] P1 Subtitles: script → SRT with cue timing
- [x] P1 Video: FFmpeg render (scenes + drawtext + audio) → MP4
- [x] P1 Thumbnail: Pillow 1280×720 PNG
- [x] P1 Pipeline endpoints orchestrating script → voice → subs → video → thumb

## Phase 7 — Studios
- [x] P1 Instagram: profile analysis, niche research, reels ideas, captions, calendar
- [x] P1 Instagram: approval-gated publish + Graph analytics (`requires_auth` honest state)
- [x] P1 YouTube: topics, long script, Shorts script
- [x] P1 YouTube: OAuth status/start/callback, approval-gated upload, analytics
- [x] P1 LinkedIn: profile improve, branding, job discovery (RemoteOK/Remotive), matching
- [x] P1 LinkedIn: truthful CV + cover letter (no-invention guard), applications + gated submit

## Phase 8 — Intelligence, monetisation, automation, accounts
- [x] P1 Content Intelligence: trends (HN Algolia/Reddit), audience research, multi-platform generation
- [x] P1 Monetisation: products, freelance leads, affiliates, sponsorships, verified revenue + CSV export
- [x] P1 Automation: 5 jobs, scheduler thread, manual run, retries, reports
- [x] P1 Account Centre: GitHub via `gh`, Meta token, Google OAuth config, LinkedIn status

## Phase 9 — Packaging & docs
- [x] P0 `start_nexus.bat` (deps check, frontend build if needed, uvicorn start)
- [x] P0 `stop_nexus.bat`
- [x] P0 `README.md`, `ARCHITECTURE.md`, `CHANGELOG.md`
- [x] P0 Real test run → `TEST_REPORT.md`

## Phase 10 — Ship
- [x] P0 `pytest` green (54 passed, 1 environment skip); `npm run build` green; live smoke test
- [x] P0 Push all source, verify `gh api repos/shahid0219/nexus-ai`
- [x] P0 Update `PROJECT_STATE.md` + this checklist

## Phase 11 — Remediation & activation (2026-11-05)
- [x] P0 AI provider router used by all modules (registry, order, health)
- [x] P0 Per-request failover: quota/auth/404/network classified, cooldowns persisted
- [x] P0 Size-aware Ollama model selection (never loads a model that cannot fit)
- [x] P0 Ollama started + verified with real inference (`qwen2.5-coder:3b`)
- [x] P0 Truthful metadata on every generation (provider, model, tokens, attempts, ts)
- [x] P0 SSE streaming endpoint with cancellation-safe final event
- [x] P0 Test-all-providers action that never consumes generation quota
- [x] P0 AI Settings page (priority, keys, health, live generate)
- [x] P0 GitHub status endpoint + dashboard page
- [x] P0 Secret scanner (10 patterns + forbidden paths) blocking commit and push
- [x] P0 Safe commit endpoint with explicit path list and staged-diff rescan
- [x] P0 Remote verification (local HEAD vs origin HEAD) endpoint
- [x] P0 Public profile preview; applying changes needs `github.profile.update` approval
- [x] P0 Meta OAuth: configure, start, callback, long-lived token, identity verify
- [x] P0 Instagram Connection tab with permission/account-type states
- [x] P0 Dashboard shows the active AI provider
- [x] P0 45 new tests (19 router, 15 github, 12 meta oauth) → 99 passing
- [x] P0 Real FFmpeg render validated with ffprobe
- [x] P0 Scheduler restart recovery verified against persisted state
- [x] P0 Docs updated (TEST_REPORT, CHANGELOG, PROJECT_STATE, TASKS)
- [ ] P1 Owner: create Meta app credentials to run the live Instagram flow
- [ ] P1 Owner: create a Google OAuth client to run the live YouTube flow
- [ ] P1 Owner approval: apply the public GitHub profile changes
- [ ] P2 `pyttsx3` install to unskip the voiceover test

## Backlog (P2)
- [x] P2 Optional `ollama pull` helper in start script
- [ ] P2 CSV import for sponsorships/applications
- [ ] P2 Keyboard shortcuts + command palette in dashboard
