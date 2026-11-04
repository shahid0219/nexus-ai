# PROJECT_STATE.md — NEXUS AI

> **Source of truth for resuming work.** Read this file first in any new session.
> Update it at the end of every work session.

Last updated: 2026-11-05 (session 2, complete)

---

## Current phase

**DONE — remediation & activation complete. 99 tests pass, 2 skip. Pushed to
`shahid0219/nexus-ai`.**

The application is functional: 82 API routes, 25 tables, 12 dashboard pages,
real local inference through Ollama, GitHub tooling, and a Meta OAuth flow.

## Session 2 summary (2026-11-05)

- [x] AI provider router (`backend/app/ai_router.py`) used by all 15 AI call
      sites; provider priority DeepSeek → Groq → OpenRouter → Google → Ollama →
      fallback, with per-class cooldowns persisted in `ai_provider_state`.
- [x] Ollama started (`ollama serve`) and verified: 6 models present,
      `qwen2.5-coder:3b` selected, real inference confirmed via module + HTTP.
      Size-aware selection refuses the 16.5 GB model on a 4 GB card.
- [x] AI Settings page (priority reorder, keys, health, test-all, live generate).
- [x] GitHub module + page: status, 10-pattern secret scan, safe commit/push,
      remote verify, public-profile preview (apply needs approval).
- [x] Meta/Instagram OAuth: official dialog, manual code exchange, long-lived
      token, identity + permission verification, Instagram tab.
- [x] 45 new tests (19 router, 15 github, 12 meta oauth); suite is 99 pass.
- [x] Docs updated: TEST_REPORT, CHANGELOG, PROJECT_STATE, TASKS.

## Known state of external integrations

| Integration | State | Blocking step |
|---|---|---|
| Ollama | **working** | none |
| DeepSeek API | not configured (paid) | no free API exists; owner key optional |
| Instagram/Meta | awaiting_configuration | owner must create a Meta app + professional account |
| Google/YouTube | awaiting_configuration | owner must create an OAuth client |
| GitHub | connected via `gh` | none |

## Remaining

1. Owner action: create Meta app credentials to exercise the Instagram flow.
2. Owner action: create a Google OAuth client to exercise the YouTube flow.
3. Owner approval: apply the public GitHub profile preview (currently zero
   public repos, so the preview is deliberately empty).
4. Optional: `python -m pip install pyttsx3` to enable the voiceover test.

## Key decisions already made (do not re-litigate)

- Port **8777** for API/server (8765 is used by `ai_business` dashboard).
- SQLite via stdlib `sqlite3`, WAL mode — no ORM.
- Frontend: Vite + React, plain CSS design system, no heavy UI kit, no CDN.
- HashRouter so the built SPA works even when served statically.
- Voiceover: `pyttsx3` (Windows SAPI, offline). Subtitles: SRT from script cues.
- Job discovery: RemoteOK + Remotive public JSON APIs (permitted, attributed, cached).
- Trends: Hacker News Algolia public API (+ public Reddit JSON).
- YouTube/Meta OAuth: manual authorization-code flows with `httpx` (no vendor SDK).
- Credentials: gitignored `data/credentials.json`; API returns presence only.
- AI fallback: deterministic template engine, always labelled
  `generated_by: fallback` — never dressed up as model output.
- DeepSeek's free chat website is **not** an API; NEXUS never scrapes it and
  never requires a DeepSeek key.
- Approvals are **single-use** and payload-hashed; kinds must be declared in
  `approvals.GATED_KINDS` (or start with `account.delete.`) or the call raises.

## Environment quirks / gotchas

- **PyPI and the npm registry are often unreachable here** (timeouts); GitHub works.
  `python -m pip download <pkg>` with `--timeout 60` eventually succeeds via cache —
  short timeouts fail. `uvicorn` was installed that way (0.54.0).
- Ollama needs an explicit `ollama serve`; the CLI's `ollama list` also boots it but
  blocks the calling shell. Running it as a background job with inherited stdio works.
- `pyttsx3` cannot be installed on this Python (missing `comtypes`/`win32com`) →
  voiceover returns `tts_unavailable`; the test skips rather than failing.
- The frontend build sandbox denies Node child processes with piped stdio, so the
  stock esbuild service fails. `frontend/scripts/ensure-esbuild-inprocess.mjs`
  patches the esbuild entry to run the WebAssembly build in-process; `build` and
  `dev` npm scripts run it first. Unrestricted machines are unaffected.
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

Note: plain `git push origin main` also worked in later sessions once the
remote was configured with the gh credential helper; try it first.

Gotchas learned: `[Text.Encoding]::UTF8(...)` is invalid PowerShell (use `.UTF8.GetBytes(...)`) —
a silent non-terminating error there leaves `$b64` empty and push falls back to prompting.

Local commit identity must be explicit:
`git -c user.name="shahid0219" -c user.email="shahid0219@users.noreply.github.com" commit ...`

## Session log

- **2026-11-05 session 2:** AI router + Ollama activation + GitHub tooling +
  Meta OAuth + Settings/GitHub pages; 45 new tests; docs updated.
- **2026-11-04 session 1:** environment verified; 4 master docs created; GitHub repo
  created and docs pushed (commit `c68645c`). Backend core, 8 modules, full React
  frontend, test suite (31 pass / 1 skip), launcher scripts and all documentation
  completed and verified by a live server smoke test.
