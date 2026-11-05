# PROJECT_STATE.md — NEXUS AI

> **Source of truth for resuming work.** Read this file first in any new session.
> Update it at the end of every work session.

Last updated: 2026-11-05 (session 4, complete)

---

## Current phase

**DONE — zero-key AI verified end to end, public website live, CI + Pages
automated. 124 tests pass, 1 skips.**

- Repository: <https://github.com/shahid0219/nexus-ai> (public)
- Website: <https://shahid0219.github.io/nexus-ai/> (GitHub Pages, `site/`)
- Local app: `docker compose up` → <http://127.0.0.1:8777>

The application is functional: 82 API routes, 25 tables, 12 dashboard pages, real
local inference through Ollama (**no API key**), GitHub tooling, a Meta OAuth
flow, and a production Docker image.

## Session 4 summary (2026-11-05)

### Zero-API-key AI
- [x] Verified real generation through NEXUS from inside Docker:
      `generated_by=ollama`, `model=qwen2.5-coder:3b`, `status=ok`, 682 ms.
- [x] Confirmed the root cause of "AI needs a key": none — the container was
      pointing at `127.0.0.1`, which is the container itself. Setting
      `OLLAMA_URL=http://host.docker.internal:11434` fixed it.
- [x] **Bug**: `/api/ai/status` always returned `models: []` for Ollama because it
      echoed the hardcoded spec instead of the installed models. Now returns the
      real list plus a `hint` explaining exactly how to fix an unavailable model.
- [x] **Bug**: a saved model override naming a deleted model broke every
      generation. Now honoured only while installed and within the size policy.
- [x] `docker-compose.yml` with the correct `extra_hosts` and `OLLAMA_URL`.
- [x] 5 **real** Ollama integration tests (`test_ollama_live.py`) — they skip
      honestly when no model is present and assert a model actually responded.

### Website + automation
- [x] `site/` — polished responsive landing page, six real screenshots captured
      from the running container, no fake stats or testimonials.
- [x] `.github/workflows/ci.yml` — backend tests + pyflakes, frontend build,
      integrity/secret scan, Docker build and container smoke test.
- [x] `.github/workflows/pages.yml` — official Pages upload/deploy.
- [x] Dockerfile gains a `fonts-dejavu-core` TTF so rendering works on Linux.

## Session 3 summary (2026-11-05)

- [x] Found and fixed a **silent** defect: every Instagram/content AI fallback
      raised `NameError` (function-local `import json` shadowing) and logged
      `fallback_error:NameError` while HTTP 200 masked it. 6 regression tests.
- [x] Found and fixed FFmpeg/ffprobe discovery: the machine's PATH is truncated,
      so the API reported `tool_missing` while the launcher worked. 7 tests.
- [x] Removed 19 unused backend imports/locals and 7 unused React imports;
      `pyflakes` and the frontend static check are both at zero.
- [x] **Repository made public**, after a full secret + history audit (clean).
- [x] Profile README repo `shahid0219/shahid0219` created and pushed; bio still
      needs the `user` OAuth scope (`gh auth refresh -s user`).
- [x] `Dockerfile` + `.dockerignore` + `DEPLOYMENT.md`; image built and run.
- [x] Fixed two deployment-only bugs: GitHub status 503 without git; hardcoded
      Windows font paths breaking video render on Linux. 6 tests.
- [x] Container verified: healthy, 16 endpoints 0 failures, real 4.000s MP4,
      data survives restart, runs as uid 10001.

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
| Ollama | **working** — real generation verified in Docker | none |
| DeepSeek API | not configured (paid) | no free API exists; owner key optional |
| Instagram/Meta | awaiting_configuration | owner must create a Meta app + professional account |
| Google/YouTube | awaiting_configuration | owner must create an OAuth client |
| GitHub | connected via `gh` | none |
| Docker deployment | **working** (`docker compose up`) | none (local/self-hosted) |
| GitHub Pages site | **deployed** | none |
| GitHub Actions | **configured** | none |

## Remaining

1. Owner action: `gh auth refresh -h github.com -s user`, then set a bio and
   display name (the current token cannot edit the profile).
2. Owner action: create Meta app credentials to exercise the Instagram flow.
3. Owner action: create a Google OAuth client to exercise the YouTube flow.
4. Optional: `python -m pip install pyttsx3` to enable the voiceover test.
5. Optional: push the built image to a registry if you want to run it on
   another machine (`docker tag` + `docker push`).
6. Optional: enable Pages once in **Settings → Pages → Source: GitHub Actions**
   if the first `pages.yml` run reports "Pages is not enabled".

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
