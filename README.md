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
ollama pull qwen2.5:3b      # ~2 GB, fits a 4 GB GPU
```

NEXUS picks the first available model from `qwen2.5:3b`, `llama3.2:3b`,
`llama3.2:1b`, `phi3:mini`, `gemma2:2b`.

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
│   │   ├── activity.py  ollama_client.py  ai_fallback.py  credentials.py
│   │   ├── routers.py  main.py
│   │   └── modules/
│   │       ├── command_centre.py  instagram.py  youtube.py  linkedin.py
│   │       └── content.py  monetisation.py  automation.py  accounts.py
│   └── tests/  conftest.py  test_api.py
├── frontend/
│   ├── index.html  vite.config.js  package.json
│   └── src/
│       ├── main.jsx  App.jsx  api.js  ui.jsx  styles.css
│       └── pages/  Dashboard, Approvals, Instagram, YouTube, LinkedIn,
│                   Content, Monetisation, Automation, Accounts, Logs
└── data/                     gitignored runtime state
    ├── nexus.db              SQLite (WAL)
    ├── credentials.json      owner-only, never returned by the API
    ├── artifacts/            audio, SRT, MP4, PNG
    └── reports/              generated markdown reports
```

---

## Tests

```powershell
python -m pytest -q
```

54 tests pass; 1 skips when Windows SAPI is unavailable and 2 network-dependent
feed tests skip themselves when an upstream is unreachable. See `TEST_REPORT.md`
for the recorded run, what each test proves, and the full API surface.
---

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
