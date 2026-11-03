# TASKS.md — NEXUS AI implementation checklist

Priority: P0 = blocking core, P1 = major feature, P2 = polish. Checked = done & verified.

## Phase 1 — Documentation
- [x] P0 `NEXUS_MASTER_SPEC.md`
- [x] P0 `PROJECT_STATE.md`
- [x] P0 `TASKS.md`
- [x] P0 `SECURITY.md`

## Phase 2 — GitHub
- [ ] P0 Verify `gh auth status`
- [ ] P0 Create/reuse private repo `shahid0219/nexus-ai`
- [ ] P0 `git init` + `.gitignore` (credentials, data, node_modules, venv, dist)
- [ ] P0 Commit + push docs; verify with `gh repo view`

## Phase 3 — Backend core
- [ ] P0 `requirements.txt`, `backend/app/config.py`
- [ ] P0 `db.py` full schema (all tables, WAL, seeds)
- [ ] P0 `approvals.py` gate + CRUD
- [ ] P0 `activity.py` logs + task history
- [ ] P0 `process.py` subprocess allowlist (ffmpeg/ffprobe/ollama only)
- [ ] P0 `security.py` secret redaction + input guards
- [ ] P0 `main.py` FastAPI shell, `/api/health`, static SPA hosting, lifespan scheduler
- [ ] P0 `routers.py` module wiring

## Phase 4 — Command Centre dashboard
- [ ] P0 Vite + React scaffold, design system CSS (dark, responsive, sidebar/topbar)
- [ ] P0 Dashboard page: system status, metrics, quick actions
- [ ] P0 Approvals page: queue + approve/reject
- [ ] P0 Logs page + Tasks history page
- [ ] P1 Mobile drawer / responsive breakpoints

## Phase 5 — Local AI
- [ ] P0 `ollama_client.py`: health, generate, model policy, 4GB-VRAM defaults
- [ ] P0 Deterministic fallback generator (tagged, never presented as Ollama)
- [ ] P0 `ai_calls` logging + `POST /api/ai/generate`

## Phase 6 — Content & video production
- [ ] P1 Voiceover: `pyttsx3` → WAV (+ honest failure if SAPI missing)
- [ ] P1 Subtitles: script → SRT with cue timing
- [ ] P1 Video: FFmpeg render (scenes + drawtext + audio) → MP4
- [ ] P1 Thumbnail: Pillow 1280×720 PNG
- [ ] P1 Pipeline endpoint orchestrating script→voice→subs→video→thumb

## Phase 7 — Studios
- [ ] P1 Instagram: profile analysis, niche research, reels ideas, captions, calendar
- [ ] P1 Instagram: approval-gated publish + Graph analytics (`requires_auth` honest state)
- [ ] P1 YouTube: topics, long script, Shorts script
- [ ] P1 YouTube: OAuth status/start/callback, approval-gated upload, analytics
- [ ] P1 LinkedIn: profile improve, branding, job discovery (RemoteOK/Remotive), matching
- [ ] P1 LinkedIn: truthful CV + cover letter (no-invention guard), applications + gated submit

## Phase 8 — Intelligence, monetisation, automation, accounts
- [ ] P1 Content Intelligence: trends (HN Algolia/Reddit), audience research, multi-platform generation
- [ ] P1 Monetisation: products, freelance leads, affiliates, sponsorships, verified revenue + CSV export
- [ ] P1 Automation: 5 jobs, scheduler thread, manual run, retries, reports
- [ ] P1 Account Centre: GitHub via `gh`, Meta token, Google OAuth config, LinkedIn status

## Phase 9 — Packaging & docs
- [ ] P0 `start_nexus.bat` (deps check, frontend build if needed, uvicorn start)
- [ ] P0 `stop_nexus.bat`
- [ ] P0 `README.md`, `ARCHITECTURE.md`, `CHANGELOG.md`
- [ ] P0 Real test run → `TEST_REPORT.md`

## Phase 10 — Ship
- [ ] P0 `pytest` green; `npm run build` green; smoke `/api/health`
- [ ] P0 Commit all source, push, verify `gh repo view shahid0219/nexus-ai`
- [ ] P0 Update `PROJECT_STATE.md` + this checklist

## Backlog (P2)
- [ ] P2 Optional `ollama pull` helper in start script
- [ ] P2 CSV import for sponsorships/applications
- [ ] P2 Keyboard shortcuts + command palette in dashboard
