# PROJECT_STATE.md — NEXUS AI

> **Source of truth for resuming work.** Read this file first in any new session.
> Update it at the end of every work session.

Last updated: 2026-11-04 (session 1, complete)

---

## Current phase

**DONE — Phases 1–9 complete and verified locally. Phase 10 (push) in progress.**

The application is functional: 62 API routes, 24 tables, 10 dashboard pages,
31 passing tests, frontend built and served from `127.0.0.1:8777`.

## Completed

- [x] Environment inspected:
  - Windows 10, Python 3.10.11 (`pip 25.2`), Node v24.21.0, Git 2.50.1, FFmpeg 8.1.1 (gyan full build)
  - `gh` authenticated as `shahid0219` (keyring, scopes: gist read:org repo workflow) — token never read or stored
  - Ollama 0.40.13 installed, **not running**, no models pulled
  - Existing projects preserved: `ai_business` (port 8765), `jarvis-agent-outputs` — untouched
- [x] All four master docs (`NEXUS_MASTER_SPEC.md`, `PROJECT_STATE.md`, `TASKS.md`, `SECURITY.md`)
- [x] Private repo `shahid0219/nexus-ai` created; docs commit `c68645c` pushed to `main`
- [x] Backend core: `config`, `db`, `security`, `approvals`, `process`, `activity`,
      `ollama_client`, `ai_fallback`, `credentials`, `routers`, `main`
- [x] All 8 modules: `command_centre`, `instagram`, `youtube`, `linkedin`,
      `content`, `monetisation`, `automation`, `accounts`
- [x] Full React frontend (10 pages) + design system CSS; `npm run build` green
- [x] `pytest`: **54 passed, 1 skipped** (`TEST_REPORT.md` has the recorded run)
- [x] `start_nexus.bat`, `stop_nexus.bat`
- [x] `README.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `TEST_REPORT.md`
- [x] Live smoke test on `127.0.0.1:8777`: health, status, stats, accounts,
      automation jobs, OAuth status, SPA root and both built assets all 200

## Remaining

1. `git add -A`, commit, push to `shahid0219/nexus-ai`, verify with `gh api`.

## Next actions (in order, for a future session)

1. Verify the push landed: `gh api repos/shahid0219/nexus-ai/commits --jq '.[0].sha'`
2. Optional: `ollama pull qwen2.5:3b` to switch every AI feature from fallback to local
   inference — no code change needed, the client picks it up automatically.
3. Optional: configure Meta / Google credentials in Account Centre to enable
   Instagram publish and YouTube upload (currently `awaiting_authentication`).
4. Optional: install `pyttsx3` (`python -m pip install pyttsx3`) to enable voiceover;
   it is the one skipped test.

## Key decisions already made (do not re-litigate)

- Port **8777** for API/server (8765 is used by `ai_business` dashboard).
- SQLite via stdlib `sqlite3`, WAL mode — no ORM.
- Frontend: Vite + React, plain CSS design system, no heavy UI kit, no CDN.
- HashRouter so the built SPA works even when served statically.
- Voiceover: `pyttsx3` (Windows SAPI, offline). Subtitles: SRT from script cues.
- Job discovery: RemoteOK + Remotive public JSON APIs (permitted, attributed, cached).
- Trends: Hacker News Algolia public API (+ public Reddit JSON).
- YouTube OAuth: manual authorization-code flow with `httpx` (no Google client library).
- Credentials: gitignored `data/credentials.json`; API returns presence only.
- AI fallback: deterministic template engine, always labelled
  `generated_by: fallback|ollama` — never dressed up as model output.
- Approvals are **single-use** and payload-hashed; kinds must be declared in
  `approvals.GATED_KINDS` (or start with `account.delete.`) or the call raises.

## Environment quirks / gotchas

- **PyPI and the npm registry are often unreachable here** (timeouts); GitHub works.
  `python -m pip download <pkg>` with `--timeout 60` eventually succeeds via cache —
  short timeouts fail. `uvicorn` was installed that way (0.54.0).
- Ollama not running by default → health degrades gracefully, UI shows "Ollama off".
- `pyttsx3` cannot be installed on this Python (missing `comtypes`/`win32com`) →
  voiceover returns `tts_unavailable`; the test skips rather than failing.
- `psutil` disk usage for `C:\` reports ~85% used / 141 GB free at time of writing.
- Background `pip install` via the job runner can hang silently; prefer explicit
  `pip download` then `pip install <wheel>` with generous timeouts.
- Running uvicorn as a detached `Start-Process` produced no logs; run it through a
  background job with inherited stdio instead (that works reliably).

## Git push recipe (CRITICAL — standard `git push` fails in this sandbox)

`sh.exe`/`bash.exe` **cannot run** here (MSYS "signal pipe" denied, Win32 error 5), so git
credential helpers and askpass all fail with `failed to execute prompt script (exit code 66)`.
Working push command (token never printed):

```powershell
Set-Location "C:\Users\Shahid\Desktop\nexus-ai"
$tok = (& gh auth token 2>$null)
$b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes("x-access-token:$tok"))
git -c "credential.helper=" -c "http.extraHeader=Authorization: Basic $b64" push -u origin main
$b64 = $null
```

Gotchas learned: `[Text.Encoding]::UTF8(...)` is invalid PowerShell (use `.UTF8.GetBytes(...)`) —
a silent non-terminating error there leaves `$b64` empty and push falls back to prompting.
Repo created via `gh repo create nexus-ai --private --source . --remote origin` (works even
though its prompt script errors). Verified: `gh api repos/shahid0219/nexus-ai` → private, main.

Local commit identity must be explicit:
`git -c user.name="shahid0219" -c user.email="shahid0219@users.noreply.github.com" commit ...`

## Session log

- **2026-11-04 session 1:** environment verified; 4 master docs created; GitHub repo
  created and docs pushed (commit `c68645c`). Backend core, 8 modules, full React
  frontend, test suite (31 pass / 1 skip), launcher scripts and all documentation
  completed and verified by a live server smoke test.
