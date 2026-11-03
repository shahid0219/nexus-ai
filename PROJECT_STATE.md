# PROJECT_STATE.md — NEXUS AI

> **Source of truth for resuming work.** Read this file first in any new session.
> Update it at the end of every work session.

Last updated: 2026-11-04 (session 1, in progress)

---

## Current phase

**Phase 2 of 10 — GitHub configuration, then backend core.**

## Completed

- [x] Environment inspected:
  - Windows 10, Python 3.10.11 (`pip 25.2`), Node v24.21.0, Git 2.50.1, FFmpeg 8.1.1 (gyan full build)
  - `gh` authenticated as `shahid0219` (keyring, scopes: gist read:org repo workflow) — token never read or stored
  - Ollama 0.40.13 installed, **not currently running**, `ollama list` empty (no models pulled yet)
  - Existing projects on Desktop: `ai_business` (must preserve), `jarvis-agent-outputs` in user profile — untouched
- [x] Project root created: `C:\Users\Shahid\Desktop\nexus-ai`
- [x] `NEXUS_MASTER_SPEC.md` written (architecture, features, API contract, plan)

## In progress

- Writing `PROJECT_STATE.md`, `TASKS.md`, `SECURITY.md`

## Next actions (in order)

1. `gh auth status` verification (done once — re-run and log), `gh repo create shahid0219/nexus-ai --private`
2. `git init`, `.gitignore`, commit docs, push
3. Backend: `backend/app/{config,db,security,approvals,process,ollama_client,activity,main}.py`
4. Modules: `command_centre, instagram, youtube, linkedin, content, monetisation, automation, accounts`
5. Frontend React SPA (Vite) — pages listed in spec §3.1
6. Local AI + content/video pipeline (pyttsx3 voiceover, SRT, FFmpeg render, Pillow thumbnail)
7. Scheduler + approvals + monetisation + accounts
8. `start_nexus.bat`, `stop_nexus.bat`, README/ARCHITECTURE/CHANGELOG/TEST_REPORT
9. `pytest` + `npm run build` + smoke test; fix failures
10. Commit, push, verify with `gh repo view`

## Key decisions already made (do not re-litigate)

- Port **8777** for API/server (8765 is used by `ai_business` dashboard).
- SQLite via stdlib `sqlite3`, WAL mode — no ORM (fewer deps, easier tests).
- Frontend: Vite + React, plain CSS design system, no heavy UI kit.
- Voiceover: `pyttsx3` (Windows SAPI, offline). Subtitles: generated SRT from script cues.
- Job discovery: RemoteOK + Remotive public JSON APIs (permitted, attributed, cached).
- Trends: Hacker News Algolia public API (+ optional Reddit public JSON).
- YouTube OAuth: manual authorization-code flow with `httpx` (no Google client library).
- Credentials: gitignored `data/credentials.json` (owner-only), DB stores refs only.
- AI fallback: deterministic template engine when Ollama is offline, so the app never fabricates "AI" output silently — responses are tagged `generated_by: fallback|ollama`.

## Environment quirks / gotchas

- Ollama service not running by default → health checks must degrade gracefully and the UI must show "Ollama offline".
- No models pulled yet → `start_nexus.bat` offers optional `ollama pull qwen2.5:3b` (user action).
- Windows sandbox: writes confined to `C:\Users\Shahid\Desktop` (workspace) — project lives there.
- `pytest` may need `pip install -r requirements.txt` first (fastapi, uvicorn, httpx, pytest, pyttsx3, pillow).

## Session log

- **2026-11-04 session 1:** environment verified; spec + state files created; continuing build.
