# TEST_REPORT.md — NEXUS AI

**Run date:** 2026-11-05 (session 4 — zero-key AI, website, CI)
**Command:** `python -m pytest backend/tests -q` (from project root)
**Result:** **124 passed, 1 skipped** in 55.93 s
(the one skip is Windows SAPI voiceover, which cannot run on this Python build)
`pyflakes backend/app backend/tests` → **0 warnings**.

---

## Session 4 — real Ollama through Docker (not mocked)

### The claim being tested

"AI needs an API key" was **false**. The container was reading `OLLAMA_URL` as
`http://127.0.0.1:11434`, and inside a container `127.0.0.1` is the container
itself, not the Windows host. No key was ever required.

### Evidence, in order

| Step | Command / observation | Result |
|---|---|---|
| Ollama on host | `ollama serve`, then `/api/tags` | 6 models |
| Host bind | `netstat -ano \| findstr :11434` | `127.0.0.1:11434` only |
| Container → host | `curl http://host.docker.internal:11434/api/tags` | **200**, 6 models |
| Real model call (raw) | `POST /api/generate {"model":"gemma3:1b"}` | `DOCKER_OLLAMA_OK` |
| Real model call (NEXUS) | `POST /api/ai/generate` | `generated_by=ollama`, `model=qwen2.5-coder:3b`, `status=ok`, 4781 ms, text `NEXUS_DOCKER_REAL` |
| Compose deployment | `docker compose up -d --build` | `Up (healthy)` |
| Compose + AI | `POST /api/ai/generate` | `generated_by=ollama`, `qwen2.5-coder:3b`, 682 ms, text `COMPOSE_OK` |
| Model list in status | `GET /api/ai/status` | `installed=6`, `selected=qwen2.5-coder:3b` |

The two NEXUS generation results above are **real model output**, not the
deterministic template engine. They are distinguishable in the response itself:
`generated_by` is `ollama` and `model` names the model.

### Real-integration test file

`backend/tests/test_ollama_live.py` — 5 tests that hit the live server:

1. `test_live_server_reports_installed_models`
2. `test_live_model_selection_respects_size_policy`
3. `test_live_generation_returns_real_text`
4. `test_live_router_generation_uses_ollama`
5. `test_live_status_reflects_reality`

They **skip** when no model is available, with the reason
`no reachable Ollama with a model that fits the size policy`. A skip is therefore
honest; a pass proves a model actually responded.

```
backend/tests/test_ollama_live.py .....  [100%]
5 passed in 59.53s
```

### Bugs found during this verification

**A. `/api/ai/status` always reported `models: []` for Ollama.**
It echoed the hardcoded provider spec (`spec.models`, empty for a local server)
instead of the installed models. The UI therefore could not show what was
available. It now lists real models and exposes `ollama.sizes_gb`.

**B. No guidance when local AI is unavailable.**
`status()` now returns a `hint` naming the exact fix — unreachable server, no
models installed, or no model within `NEXUS_AI_MAX_MODEL_GB`. The AI Settings page
renders it.

**C. A stale model override broke every generation.**
`_pick_model` returned a saved override unconditionally. If that model had been
deleted, every call failed instead of auto-selecting. Overrides are now honoured
only while the model exists and fits the size policy.

### Deployment bugs fixed this session

- Dockerfile gained `fonts-dejavu-core`; without a TTF, `drawtext` rendering fails
  on the slim image.
- Added `docker-compose.yml` wiring `OLLAMA_URL` and `host.docker.internal`
  correctly, with a healthcheck.

### Endpoint and UI audit

- 55 frontend `api.get/post/del` call sites checked against the 82 backend
  routes: **all resolve**.
- No `onClick={() => {}}`, no `href="#"`, no TODO/FIXME/"coming soon" markers.
- 12 pages render; screenshots for the site were captured from the running
  container.

### Website

- `site/index.html` + `assets/` — responsive at 1440 px and at 504 px (headless
  Chrome's minimum width), hamburger nav below 720 px.
- 6 screenshots taken from the live container, so the site shows the real product.
- No fabricated testimonials, statistics, or live-status claims.

---

## Deployment verification (2026-11-05, Docker)

The image was built and run on the development machine; nothing below is
simulated.

```
docker build -t nexus-ai .      -> success
docker run -d -p 8780:8777 ...  -> Up (healthy)
```

| Check | Result |
|---|---|
| `docker ps` health | `Up 16 seconds (healthy)` |
| `/api/health` | 200 — `frontend_built: true`, db at `/app/data/nexus.db` |
| 16 GET endpoints | **0 failures** (health, system, stats, ai, github, accounts, oauth x2, linkedin, content, approvals, activity, schedule, research, monetisation) |
| `POST /api/youtube/render` | 200 — MP4 written, `ffprobe` reports `duration=4.000000` |
| `POST /api/ai/generate` | `generated_by=fallback status=fallback` (no Ollama in container) |
| Restart persistence | `ai_calls_today` and 5 artifact files survived `docker restart` |
| Process user | `uid=10001(nexus)` — not root |
| SPA assets | `/` 200 (393 b shell) and `/assets/index-*.js` 200 (253 KB) |

### Two deployment-only bugs found and fixed

**A. `/api/github/status` → 503 in the container.**
The endpoint called `git` unconditionally. A container without git satisfies
every other feature but lost the whole GitHub page. It now returns
`available: false` with a human-readable note, and `github_status` additionally
requires the workspace to be an actual checkout.

**B. Video render → `no TTF font found`.**
Font paths were hardcoded to `C:/Windows/Fonts/...`. On the Debian image that
path cannot exist. Fonts are now discovered across Windows, Linux, macOS and a
bundled `tools/fonts` directory, the image installs `fonts-dejavu-core`, and the
error text tells the operator how to fix it.

Both are pinned by `backend/tests/test_deployment.py` (6 tests).

---

## Bug-fix pass (2026-11-05, earlier)

A deliberate hunt for real defects found two that were **silently degrading
behaviour while every HTTP response still looked healthy**.

### Bug 1 — every Instagram/content AI fallback raised `NameError`

`backend/app/modules/instagram.py` and `backend/app/modules/content.py` imported
`json` *inside* the request handler, **after** the fallback lambda that used it:

```python
fallback=lambda: json.dumps(ai_fallback.niche_research(body.niche))
import json          # <- makes `json` a local name for the whole function
```

Because the import bound a local variable, the lambda's reference was an
unbound local at call time. Result: **all five** fallback paths
(`instagram.profile`, `instagram.niche`, `instagram.reels`,
`instagram.captions`, `content.audience`) raised `NameError`, and the DB
recorded `fallback_error:NameError` on every offline generation.

The endpoints still returned HTTP 200 because each had a second
`ai_fallback.*` call after the try/except — so the demo looked fine while the
primary fallback never executed and the AI log filled with errors.

**Fix:** `json` is imported once at module scope; the redundant function-local
imports were removed.

**Evidence (before → after):**
```
before: ai_calls.status = 'fallback_error:NameError'   (5 rows)
after : ai_calls.status = 'fallback'
```

**Regression tests:** `backend/tests/test_fallback_regression.py` (6 tests) —
one per handler plus an assertion that no `fallback_error%` row is ever written.

### Bug 2 — FFmpeg reported missing on a machine where it is installed

This profile's user `PATH` is truncated at 1049 characters, so
`shutil.which("ffmpeg")` returned `None` and `/api/youtube/render` failed with
`tool_missing` even though FFmpeg 8.1.1 was present. `start_nexus.bat` worked
(it searched manually) but the API did not — an inconsistency that would hit
any user with a broken PATH.

**Fix:** `config._find_tool()` resolves `ffmpeg`/`ffprobe` from PATH first, then
known install locations, including WinGet's versioned package folders whose name
(`ffmpeg-8.1.1-full_build`) need not match the binary (`ffprobe.exe`).
`process.resolve()` now uses that same lookup, so the allowlist and the API agree.

**Evidence:**
```
config.ffmpeg_path()  -> ...\Gyan.FFmpeg_...\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe
config.ffprobe_path() -> ...\ffmpeg-8.1.1-full_build\bin\ffprobe.exe
render + ffprobe      -> duration=2.000000  rc=0
```

**Regression tests:** `backend/tests/test_tools.py` (7 tests) — fallback lookup,
WinGet nesting, missing-tool behaviour, `process.resolve` parity, and an
assertion that no shell is ever allowlisted.

### Also fixed in this pass

- 19 unused imports/locals removed across 9 backend modules (`pyflakes` clean).
- 7 unused React imports removed (`Approvals`, `Content`, `Monetisation`,
  `Settings`, `YouTube`); frontend rebuilds to 48 modules.
- A throwaway probe exercised **48 endpoints** (29 GET, 17 POST) with the AI
  provider forced offline: **0 failures, 0 unhandled 500s**.

---

## Final verification (2026-11-05, earlier)

**Result:** **100 passed, 1 skipped** in 51.87 s

Environment at time of run:

| Component | Version |
|---|---|
| OS | Windows 10 (AMD64), 16 logical cores |
| Python | 3.10.11 (invoked by absolute path — see note) |
| Node / npm | v24.21.0 / 11.19.0 |
| FFmpeg | 8.1.1-full_build (Gyan/WinGet) |
| Git | 2.50.1.windows.1 |
| Ollama | 0.40.13, **server running**, 6 models installed |
| FastAPI / Starlette | 0.116.1 / 0.47.2 |
| React / Vite | 18.3 / 5.4.21 |

> **Machine note (not a project defect):** this Windows profile's user `PATH`
> is truncated mid-entry at 1049 characters (it ends at
> `...\Programs\Pyth`), so `python` and `ffmpeg` are not resolvable from a
> fresh shell. NEXUS was verified by supplying the absolute interpreter path
> and the WinGet FFmpeg bin directory. `start_nexus.bat` was hardened to
> locate Python and FFmpeg itself, so the launcher works regardless. Repairing
> the system `PATH` is left to the machine owner.

The suite runs against a throwaway SQLite database in `%TEMP%` (see
`backend/tests/conftest.py`) — the real `data/nexus.db` is never touched.
Network tests skip themselves when the public feeds are unreachable, so the
suite is meaningful fully offline.

---

## Final verification (2026-11-05)

### Live endpoint smoke test — 20/20 HTTP 200

`/api/health`, `/api/system/status`, `/api/stats`, `/api/accounts`,
`/api/automation/jobs`, `/api/automation/status`, `/api/ai/status`,
`/api/github/status`, `/api/instagram/oauth/status`, `/api/youtube/oauth/status`,
`/api/linkedin/applications`, `/api/monetisation/revenue`, `/api/approvals`,
`/api/tasks`, `/api/logs`, `/api/instagram/calendar`, `/api/instagram/analytics`,
`/api/content/trends`, `/api/linkedin/jobs`, `/`.

### Live AI (real inference, not simulated)

```
GET  /api/ai/status   -> active: ollama / Ollama (local), model qwen2.5-coder:3b
POST /api/ai/generate -> generated_by=ollama, model=qwen2.5-coder:3b,
                         text="NEXUS_FINAL_OK", fallback=False
POST /api/ai/stream   -> text/event-stream, 2 delta chunks + done event (447 ms)
```

Six models are installed. The 16.5 GB model is refused by the size policy, and
`qwen2.5-coder:3b` (1.8 GB) is selected — appropriate for a 4 GB card.

### Live FFmpeg render (validated, not just "exit 0")

```
POST /api/youtube/render (2 scenes x 2 s)
  -> data/artifacts/video_1793865861_NEXUS_Live_Verify.mp4
ffprobe: format_name=mov,mp4,m4a,3gp,3g2,mj2   duration=4.000000
```

### Scheduler restart recovery

`automation_jobs.last_run_ts` was back-dated in SQLite; `Scheduler._check_due()`
then read the persisted timestamp, ran `weekly_report`, and wrote a new
`automation_runs` row. Recovery works from the database, not memory.

### Frontend build

```
vite v5.4.21 building for production...
✓ 48 modules transformed.
dist/index.html                   0.39 kB │ gzip:  0.27 kB
dist/assets/index-DuWULXd0.css   11.66 kB │ gzip:  3.21 kB
dist/assets/index-DqAJYbVG.js   253.56 kB │ gzip: 76.41 kB
✓ built in 2.71s
```

### API surface

**82 method+path pairs** across 9 modules (was 62 across 8).

### Secret scan

`GET /api/github/secret-scan` — 64 files, clean, findings always redacted.

---

## Verification session 2 — remediation & activation (2026-11-05)

This session added a real AI provider router, GitHub tooling, a Meta OAuth flow
and a Settings UI. Everything below was run on this machine today.

### New suites

| Suite | Tests | Proves |
|---|---|---|
| `backend/tests/test_ai_router.py` | 19 | provider order, 429/quota failover, cooldown skip, auth/404 classification, timeout retries, Ollama selection, oversized-model rejection, redaction, truthful metadata, credential-free connectivity probe |
| `backend/tests/test_github.py` | 15 | forbidden-path refusal, traversal refusal, 10 credential patterns, redacted previews, status parsing, commit blocked by a dirty scan, approval-gated profile apply, preview never writes |
| `backend/tests/test_meta_oauth.py` | 12 | OAuth status states, secret never echoed, official auth URL, long-lived token exchange, provider-error surfacing, permission-gap detection, missing professional-account detection, honest analytics/publish refusal |

### Live AI verification (real, not simulated)

Ollama was started with `ollama serve` on `127.0.0.1:11434`. Six models were
already installed; the 16.5 GB model is correctly refused by the 4 GB-VRAM
policy and `qwen2.5-coder:3b` (1.8 GB) is selected instead.

```
GET  /api/ai/status        -> active: ollama / model qwen2.5-coder:3b
POST /api/ai/generate      -> generated_by=ollama model=qwen2.5-coder:3b
                              text="NEXUS_API_OK"
POST /api/ai/stream        -> text/event-stream, 2 delta chunks,
                              done event provider=ollama model=qwen2.5-coder:3b
```

### Real FFmpeg verification

```
POST /api/youtube/render (2 scenes x 2 s)
  -> data/artifacts/video_1793825762_NEXUS_Render_Test.mp4, 17,304 bytes
ffprobe: format_name=mov,mp4,m4a,3gp,3g2,mj2  duration=4.000000  size=17304
```

A real, playable MP4 with the exact expected duration.

### Scheduler persistence

`automation_jobs.last_run_ts` was back-dated in SQLite and
`Scheduler._check_due()` was called against the reopened database: it read the
persisted timestamp, fired `weekly_report`, and wrote a new `automation_runs`
row. Restart recovery therefore works from persisted state, not memory.

### Secret scan

`GET /api/github/secret-scan` scanned 64 files with a clean result after the npm
cache directory was removed and ignored. Findings are shown redacted.

### Frontend build

```
vite v5.4.21 building for production...
✓ 48 modules transformed.
dist/index.html                   0.39 kB │ gzip:  0.27 kB
dist/assets/index-DuWULXd0.css   11.66 kB │ gzip:  3.21 kB
dist/assets/index-DqAJYbVG.js   253.56 kB │ gzip: 76.41 kB
✓ built in 2.60s
```

### API surface

**82 method+path pairs** across 9 modules (was 62 across 8).

### Known limits after session 2

1. **DeepSeek API is not free.** No key is stored, so it is listed but skipped.
   The free chat website is not an API and is never scraped.
2. **Instagram/Meta and Google/YouTube remain `awaiting_configuration`** — no
   owner app credentials exist yet. The flows are implemented and unit-tested;
   the authenticated paths cannot be exercised without real credentials.
3. **No public GitHub repos yet**, so the profile preview reports an empty
   detected stack rather than inventing one.
4. **Voiceover** still skips: `pyttsx3` will not install on this Python build.

---

## Verification session 1 — original baseline (2026-11-04)

**Command:** `python -m pytest -q` (from project root)
**Result:** **54 passed, 1 skipped** in 80.54 s
(the skip is Windows SAPI voiceover, unavailable on this machine; the two
network-dependent feed tests skip themselves instead of failing when an
upstream is unreachable)

Environment at time of run:

| Component | Version |
|---|---|
| OS | Windows 10 (AMD64), 16 logical cores |
| Python | 3.10.11 |
| Node / npm | v24.21.0 / 11.19.0 |
| FFmpeg | 8.1.1-full_build (gyan.dev) |
| Git | 2.50.1.windows.1 |
| Ollama | 0.40.13 client, **server not running, no models pulled** |
| FastAPI / Starlette | 0.116.1 / 0.47.2 |
| React / Vite | 18.3 / 5.4.21 |

The suite runs against a throwaway SQLite database in `%TEMP%` (see
`backend/tests/conftest.py`) — the real `data/nexus.db` is never touched.
Network tests skip themselves when the public feeds are unreachable, so the
suite is meaningful fully offline.

---

## Results by area

### 1. Core endpoints (4)
| Test | Proves |
|---|---|
| `test_health` | `/api/health` returns status, version, Ollama state and model list |
| `test_system_status` | real psutil CPU/RAM/disk, python version, tool availability |
| `test_stats_shape` | dashboard counters all present |
| `test_logs_endpoint` | activity log rows are shaped and redacted |

*(plus 23 parametrised GET liveness checks — see §10)*

### 2. Honesty guards (6) — no fabricated data, ever
| Test | Proves |
|---|---|
| `test_instagram_analytics_requires_auth` | returns `requires_auth: true` and **no** `metrics` key |
| `test_instagram_publish_requires_auth` | publish refuses without a Meta token instead of faking a post |
| `test_youtube_analytics_requires_auth` | same for YouTube |
| `test_youtube_upload_requires_auth` | upload refuses without Google OAuth |
| `test_youtube_oauth_status` | reports `authorized: false` with an explicit awaiting-state |
| `test_accounts_never_leak_secrets` | the accounts payload contains no `gho_`/`access_token` substrings; LinkedIn is `not_applicable` |

### 3. Approval gate (6)
| Test | Proves |
|---|---|
| `test_calendar_delete_requires_approval_then_works` | DELETE → 409 + `approval_id`; approve; retry → `deleted` |
| `test_revenue_verification_invariant` | money with a payment reference is `verified: true`; without one it stays `verified: false` |
| `test_approval_reject` | rejection records a reason and status |
| `test_approval_is_single_use` | one approval authorises exactly one action; the next attempt demands a fresh one |
| `test_undeclared_approval_kind_rejected` | an empty/typo kind raises instead of silently skipping the gate |
| `test_api_rejects_unknown_approval_kind` | same guard surfaces as HTTP 400 `unknown_approval_kind` |

### 4. Local AI + fallback labelling (2)
| Test | Proves |
|---|---|
| `test_ai_generate_fallback_label` | every response carries `generated_by: ollama|fallback` |
| `test_captions_and_reels` | content generators honour `count` and keep the label |

### 5. Truthful documents (2)
| Test | Proves |
|---|---|
| `test_cv_never_invents_facts` | name/company appear; missing education renders `[not provided]`; **every** year in the output exists in the input profile |
| `test_cover_letter_uses_only_supplied_facts` | only supplied name/company are asserted |

### 6. Media pipeline (4)
| Test | Proves |
|---|---|
| `test_subtitles_srt` | ≥2 cues, valid `-->` timing, file written |
| `test_thumbnail_render` | real 1280×720 PNG > 5 KB |
| `test_ffmpeg_render` | real MP4 produced by FFmpeg drawtext |
| `test_voiceover_or_honest_failure` | **skipped** — Windows SAPI is unavailable in this session; the endpoint returns a structured `tts_unavailable` error rather than a fake file |

### 7. Security helpers (3)
| Test | Proves |
|---|---|
| `test_redact` | tokens, `Bearer` values and `gho_`-style prefixes are masked |
| `test_sanitize_filename` | path traversal and unsafe characters removed |
| `test_process_allowlist` | `process.run(["python", ...])` refuses with `subprocess_not_allowed` |

### 8. Automation (3)
| Test | Proves |
|---|---|
| `test_automation_jobs_registered` | exactly the 5 declared jobs, no drift |
| `test_weekly_report_runs_offline` | the job writes a markdown report built from the real DB, with no invented estimates |
| `test_content_preparation_respects_settings` | the job runs end-to-end offline |

### 9. Live public feeds (2, network-dependent)
| Test | Proves |
|---|---|
| `test_jobs_discovery_endpoint` | RemoteOK/Remotive records carry `source` + `fetched_at` attribution |
| `test_trends_endpoint` | trend clusters and per-source status are returned |

### 10. GET endpoint liveness (23, parametrised)
`test_get_endpoint_never_500s` walks every read-only endpoint the dashboard calls
and asserts no unhandled crash. This caught a real defect during final verification:
the `/api/automation/runs` handler passed an `int` where the DB helper expected a
params tuple, returning HTTP 500 as soon as a run existed. Fixed, and now
regression-guarded.

The two public-feed endpoints (`/api/linkedin/jobs`, `/api/content/trends`) are
allowed to return an honest **502 `network_error`** when their upstreams are
unreachable and no cache exists — the assertion accepts exactly that shape and
nothing else.

### 11. Feed resilience (measured)
Both feed modules fetch concurrently and are hard-capped per source: a socket
timeout of 6 s plus an 8 s deadline on the future. The pool is shut down with
`wait=False, cancel_futures=True`, so a stuck TLS handshake can never block the
HTTP response.

Measured with Reddit unreachable (TLS handshake timeout) and Hacker News healthy:

| Call | Latency | Sources |
|---|---|---|
| `/api/content/trends` #1 | 9.6 s | hackernews ok, reddit ConnectTimeout |
| `/api/content/trends` #2 | 8.3 s | hackernews ok, reddit ConnectTimeout |
| `/api/content/trends` #3 | 6.3 s | hackernews ok, reddit ConnectTimeout |
| `/api/linkedin/jobs` | 0.0 s | cache hit, HTTP 200 |

Before the fix the same conditions took up to 35 s. The endpoint always returns
200 with a per-source `ok` flag rather than failing the whole request.

---

## Frontend build

```
vite v5.4.21 building for production...
✓ 46 modules transformed.
dist/index.html                   0.39 kB │ gzip:  0.27 kB
dist/assets/index-D_rZUkvT.css   10.20 kB │ gzip:  2.93 kB
dist/assets/index-DJEx9PYY.js   220.05 kB │ gzip: 67.29 kB
✓ built in 952ms
```

The bundle is self-contained: no CDN, no external fonts, no chart or UI library.

## Clean-room verification

The repository was cloned fresh from GitHub into an empty temp directory to prove
the repo alone is sufficient:

| Step | Result |
|---|---|
| `git clone` | 55 files, **no `data/` directory** (runtime state correctly untracked) |
| `python -m pytest -q` | **54 passed, 1 skipped** in 55.68 s |
| `python -m uvicorn app.main:app ...` | boots, `frontend_built: false` until built |
| `GET /` before build | correct "dashboard is not built yet" page, not an error |
| `npm install && npm run build` | 66 packages, 46 modules, `dist/index.html` + 2 assets |
| `GET /api/health`, `/api/stats`, `/api/automation/jobs`, `/` | all 200 |

## UI verification (headless Chrome screenshots)

Rendered `http://127.0.0.1:8777` with Chrome `--headless=new` at 1440×1000:

- **Dashboard** — live values (`CPU 48.6%`, `RAM 15.3 GB · 84.8% used`,
  `ffmpeg 8.1.1-full_build`, `ollama ✗`), version/uptime pill in the top bar.
- **Automation** — all 5 jobs with real intervals and last-run timestamps,
  empty states for runs/reports.
- **Account Centre** — GitHub `connected` (as `shahid0219`, token never read),
  Meta `awaiting_configuration`, Google `awaiting_configuration`,
  LinkedIn `not_applicable` with the no-API explanation.

The screenshots confirm the frontend actually mounts and talks to the API —
a green `vite build` alone would not prove that.

## Live smoke test

Server started with
`python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8777`:

| Request | Result |
|---|---|
| `GET /api/health` | 200 — `status: ok`, `frontend_built: true` |
| `GET /api/system/status` | 200 — platform, CPU, RAM, disk, tool probes |
| `GET /api/stats` | 200 |
| `GET /api/accounts` | 200 — no secrets in payload |
| `GET /api/automation/jobs` | 200 — 5 jobs |
| `GET /api/youtube/oauth/status` | 200 — `awaiting_authentication` |
| `GET /` | 200 — SPA root served |
| `GET /assets/index-DJEx9PYY.js` | 200 — 220 KB |
| `GET /assets/index-D_rZUkvT.css` | 200 — 10 KB |

API surface: **62 method+path pairs** across 8 modules.

---

## Known limits (honest, not failures)

1. **Voiceover skipped** — `pyttsx3`/SAPI could not be installed on this machine's
   Python (no `comtypes`/`win32com`). The code path exists and returns a structured
   error; the test skips rather than pretending. Install `pyttsx3` and re-run to cover it.
2. **Ollama offline** — no models pulled and the server was not running. All AI tests
   therefore exercise the deterministic fallback, which is the intended behaviour.
   Their assertions are label-agnostic so they pass either way.
3. **Platform APIs untested live** — Instagram publish, YouTube upload and analytics
   require real owner credentials. They are covered by the honesty tests: the
   unauthenticated behaviour is asserted, and the authenticated paths are
   **awaiting_authentication**, not claimed as working.
