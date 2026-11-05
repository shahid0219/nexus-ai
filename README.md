# NEXUS AI

Local-first autonomous digital growth platform. One dashboard for content creation,
video production, career management, research, monetisation tracking and scheduled
automation — running entirely on your own machine.

- **Stack:** Python 3.10 · FastAPI · SQLite (stdlib) · React 18 + Vite · Ollama (optional)
- **Network:** binds `127.0.0.1:8777` only. Never `0.0.0.0`.
- **Cost:** £0. No paid APIs, no cloud inference, no subscriptions, no telemetry.
- **Safety:** every publish / send / delete / financial action requires an explicit approval record.

---

## Quick start (Windows)

```bat
start_nexus.bat
```

The script installs missing Python dependencies, builds the dashboard on first run,
starts Ollama if it is installed, then serves <http://127.0.0.1:8777>.

```bat
stop_nexus.bat
```

Stops the server on port 8777. Ollama is left running (it is a shared system service).

### Manual start

```powershell
python -m pip install -r requirements.txt
cd frontend; npm install; npm run build; cd ..
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8777
```

### Optional local AI

Without Ollama, NEXUS still works: every AI feature falls back to a deterministic
template engine and labels the response `generated_by: "fallback"`. Nothing is
presented as AI when it was not.

```powershell
ollama serve
ollama pull qwen2.5-coder:3b   # ~1.8 GB, fits a 4 GB GPU
```

Model selection is size-aware: NEXUS prefers `qwen2.5-coder:3b`, `qwen2.5:3b`,
`gemma3:1b`, `ministral-3:3b`, `qwen3.5:4b`, `llama3.2:3b`, `llama3.2:1b`,
`phi3:mini`, `gemma2:2b`, and **refuses to load anything above
`NEXUS_AI_MAX_MODEL_GB` (default 5.5 GB)** so a small GPU is never asked to swap.
NEXUS never downloads a model on its own — `ollama pull` is always your command.

The **AI Settings** page shows the active provider, the selected model, every
installed model, and a hint telling you exactly what to fix when local AI is
unavailable.

Remote providers (Groq / OpenRouter / Google / DeepSeek) can be added with your own
key on the **AI Settings** page. DeepSeek has no free API tier — its chat website is
not an API and NEXUS never scrapes it.

### Docker

```bash
docker build -t nexus-ai .
docker run --rm -p 8777:8777 \
  -v nexus-data:/app/data \
  -e OLLAMA_URL=http://host.docker.internal:11434 \
  --add-host=host.docker.internal:host-gateway \
  nexus-ai
```

Inside a container `localhost` is the container, not your PC. `OLLAMA_URL` must point
at `host.docker.internal` to reach Ollama on the Windows host.

See [DEPLOYMENT.md](DEPLOYMENT.md) for volumes, Ollama networking, configuration
variables and the security posture.

### Project website

The landing page lives in [`site/`](site) and is published to
<https://shahid0219.github.io/nexus-ai/> by GitHub Pages on every push that touches
`site/`. It is a static project site — GitHub Pages does **not** host the Python
backend.

---

## What is actually implemented

Status is honest by design. `requires_auth` responses mean the code path exists but
needs **your** credentials; nothing is mocked to look functional.

| Area | Status | Notes |
|---|---|---|
| Command Centre (health, system, stats, logs, tasks) | **implemented** | live psutil metrics, real DB counts |
| Approval gate | **implemented** | 409 + `approval_id`; approve then retry executes |
| Approvals UI (queue, approve, reject, reason) | **implemented** | |
| Local AI + labelled offline fallback | **implemented** | `ollama` or `fallback` on every response |
| Instagram: profile analysis, niche research, reels, captions | **implemented** | AI-generated, grounded in your input |
| Instagram: content calendar | **implemented** | create/list; delete is approval-gated |
| Instagram: publish | **requires_approval + awaiting_authentication** | needs Meta token + public `media_url` |
| Instagram: analytics | **awaiting_authentication** | returns `requires_auth`, never invents metrics |
| YouTube: topics, scripts (short/long) | **implemented** | |
| YouTube: voiceover (SAPI/`pyttsx3`) | **implemented** | honest failure if SAPI is unavailable |
| YouTube: SRT subtitles | **implemented** | real cue timing from script sentences |
| YouTube: FFmpeg MP4 render | **implemented** | drawtext scenes + optional audio |
| YouTube: 1280×720 thumbnail | **implemented** | Pillow, wrapped title text |
| YouTube: OAuth (loopback + manual code) | **implemented** | needs your Google OAuth client |
| YouTube: upload | **requires_approval + awaiting_authentication** | resumable upload, default `private` |
| YouTube: analytics | **awaiting_authentication** | honest `requires_auth` state |
| LinkedIn: profile improve, branding ideas | **implemented** | |
| LinkedIn: job discovery | **implemented** | RemoteOK + Remotive public feeds, attributed + cached |
| LinkedIn: job match | **implemented** | transparent skill-overlap scoring |
| LinkedIn: truthful CV + cover letter | **implemented** | invention guard; missing facts render `[not provided]` |
| LinkedIn: applications + submit | **implemented (manual)** | submit → `ready_for_manual_submission`, never auto-sent |
| Content Intelligence: trends | **implemented** | HN Algolia + public Reddit JSON, clustered, cached |
| Content Intelligence: audience research | **implemented** | always tagged as hypothesis |
| Content Intelligence: multi-platform generation | **implemented** | enforces per-platform character limits |
| Monetisation: products, leads, affiliates, sponsorships | **implemented** | date-stamped affiliate directory |
| Monetisation: revenue | **implemented** | `verified=1` only with a payment reference |
| Monetisation: CSV export | **implemented** | |
| Automation: 5 scheduled jobs + retries + reports | **implemented** | scheduler thread, 8 s feed deadline, exponential backoff |
| Account Centre | **implemented** | GitHub via `gh`, Meta token, Google OAuth, LinkedIn status |

**Deliberately not implemented** (would require bypassing protections or fabricating data):
LinkedIn automation/scraping, OTP or CAPTCHA bypass, invented analytics, invented
qualifications, unreferenced revenue marked as verified.

---

## Project layout

```
nexus-ai/
├── start_nexus.bat / stop_nexus.bat
├── NEXUS_MASTER_SPEC.md      full design + API contract
├── PROJECT_STATE.md          resume-here state log
├── TASKS.md                  prioritised checklist
├── SECURITY.md               threat model + rules
├── ARCHITECTURE.md           how the pieces fit
├── CHANGELOG.md
├── TEST_REPORT.md            real, reproducible results
├── pytest.ini
├── requirements.txt
├── backend/
│   ├── app/
│   │   ├── config.py  db.py  security.py  approvals.py  process.py
│   │   ├── activity.py  ollama_client.py  ai_fallback.py  ai_router.py
│   │   ├── credentials.py  routers.py  main.py
│   │   └── modules/
│   │       ├── command_centre.py  instagram.py  youtube.py  linkedin.py
│   │       ├── content.py  monetisation.py  automation.py  accounts.py
│   │       └── github.py
│   └── tests/  conftest.py  test_api.py  test_ai_router.py  test_github.py
│                test_meta_oauth.py  test_tools.py  test_deployment.py
│                test_fallback_regression.py
├── frontend/
│   ├── index.html  vite.config.js  package.json
│   └── src/
│       ├── main.jsx  App.jsx  api.js  ui.jsx  styles.css
│       └── pages/  Dashboard, Approvals, Instagram, YouTube, LinkedIn,
│                   Content, Monetisation, Automation, Accounts, Logs,
│                   Settings (AI), GitHubPage
├── site/                     static project site published to GitHub Pages
│   ├── index.html
│   └── assets/               site.css, site.js, favicon.svg, screenshots/
├── .github/workflows/        ci.yml (tests/build/docker), pages.yml (Pages)
├── Dockerfile  .dockerignore  DEPLOYMENT.md
└── data/                     gitignored runtime state
    ├── nexus.db              SQLite (WAL)
    ├── credentials.json      owner-only, never returned by the API
    ├── artifacts/            audio, SRT, MP4, PNG
    └── reports/              generated markdown reports
```

---

## Running with no API keys

NEXUS needs **no paid subscription, no API credit and no API key**. The order of
resolution for every AI feature is:

1. **Ollama** — a local model on your own machine. Free, offline, no key.
2. **A free-tier provider** — only if *you* added a key on the AI Settings page.
3. **Deterministic templates** — always available, always labelled
   `generated_by: "fallback"`.

Nothing else is required. With no Ollama and no keys the entire application still
runs: content planning, video rendering, thumbnails, CV building, job discovery,
monetisation tracking, scheduling and persistence all work.

Every AI response carries the provider and model that produced it, so the UI can
never imply a model ran when it did not.

### Connecting Ollama when NEXUS runs in Docker (Windows)

Ollama binds `127.0.0.1` by default, which a container cannot reach. Docker Desktop
on Windows already exposes the host as `host.docker.internal`, so pass that:

```powershell
docker run --rm -p 8777:8777 `
  -v nexus-data:/app/data `
  -e OLLAMA_URL=http://host.docker.internal:11434 `
  --add-host=host.docker.internal:host-gateway `
  nexus-ai
```

Verify from inside the container:

```powershell
docker exec <container> curl -s http://host.docker.internal:11434/api/tags
```

If that fails, allow Ollama to listen beyond loopback **only if you accept the LAN
exposure**, then restart it:

```powershell
# current user, persistent
[Environment]::SetEnvironmentVariable('OLLAMA_HOST', '0.0.0.0:11434', 'User')
# restart the Ollama app / `ollama serve`, then verify the bind:
netstat -ano | Select-String ':11434'
```

Do **not** expose `11434` through your router or a public tunnel: there is no
authentication on that port. If you set `OLLAMA_HOST=0.0.0.0`, create a Windows
Firewall rule restricted to the Docker subnet rather than allowing all profiles:

```powershell
New-NetFirewallRule -DisplayName "Ollama (Docker subnet only)" -Direction Inbound `
  -Protocol TCP -LocalPort 11434 -RemoteAddress 172.17.0.0/16 -Action Allow
```

With Ollama left on its default `127.0.0.1` bind, Docker Desktop's host proxy is the
only path in — which is the safer configuration and the one verified in
`TEST_REPORT.md`.

---

## Tests

```powershell
python -m pytest -q
```

**119 passed, 1 skipped.** The skip is the Windows SAPI voiceover test, which cannot
run on this Python build. One real Ollama generation test is separate and only runs
when a model is installed. See `TEST_REPORT.md` for the recorded runs, what each
test proves, and the full API surface.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `NEXUS_PORT` | `8777` | HTTP port |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | local inference endpoint |
| `NEXUS_AI_TOKENS` | `1024` | max generated tokens |
| `NEXUS_AI_TIMEOUT` | `90` | seconds per generation |

Credentials are entered in **Account Centre** and stored in `data/credentials.json`
(owner-only, gitignored). The API exposes only `present: true/false` — never the values.

---

## Documentation map

| File | Read it for |
|---|---|
| `NEXUS_MASTER_SPEC.md` | full feature spec, data model, API contract, rules |
| `ARCHITECTURE.md` | request flow, approval gate, scheduler, security boundaries |
| `SECURITY.md` | threat model, egress allowlist, incident response |
| `PROJECT_STATE.md` | current phase, environment quirks, resume notes |
| `TASKS.md` | what is done and what is left |
| `CHANGELOG.md` | version history |
| `TEST_REPORT.md` | verified test output |

## Licence

Personal project. Use at your own risk; no warranty.
