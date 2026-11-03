# NEXUS AI — Master Specification

**Version:** 1.0.0
**Owner:** shahid0219
**Repo:** `shahid0219/nexus-ai` (private)
**Type:** Local-first autonomous digital growth platform
**Runtime:** Windows 10 · Ryzen 7 6800H · RTX 3050 4GB · Python 3.10 · Node.js 24 · Ollama · FFmpeg

---

## 1. Vision

NEXUS AI is a single local application that runs the entire digital-growth loop from one machine:

> research → strategy → content → video → publishing (with approval) → analytics → monetisation → reporting

Everything that *can* run locally *does* run locally: the database (SQLite), the AI (Ollama),
voiceovers (Windows SAPI), video assembly (FFmpeg), thumbnails (Pillow), scheduling (in-process
scheduler). External platforms are contacted **only** through official APIs with credentials the
owner supplies, and **only** after an explicit approval record exists.

---

## 2. Hard engineering rules

| # | Rule | Enforcement point |
|---|------|-------------------|
| R1 | Free / open-source / local-first only; no paid APIs, subscriptions or mandatory cloud | `requirements.txt` contains only FOSS; config rejects paid endpoints |
| R2 | Optimised for 4GB VRAM | Ollama client defaults to small models (`qwen2.5:3b`, `llama3.2:3b`), 1 request at a time, 2048-token cap |
| R3 | Preserve JARVIS and InvoicePilot; never overwrite unrelated projects | All work confined to `C:\Users\Shahid\Desktop\nexus-ai`; nothing else written |
| R4 | Official platform APIs and permitted automation only | Publishing/upload modules refuse to run without stored official credentials |
| R5 | Never bypass OTP, CAPTCHA or platform restrictions | No browser automation, no credential stuffing, no challenge solving anywhere in the codebase |
| R6 | Never fabricate qualifications, analytics, revenue or successful operations | Analytics/revenue endpoints return `requires_auth` / `unverified` unless real data exists; CV generator can only emit facts present in supplied profile JSON |
| R7 | No unrestricted AI shell execution, no arbitrary `shell=True` | `ai` module has **zero** code execution tools; subprocess calls are an explicit argv allowlist (`ffmpeg`, `ffprobe`, `ollama`) in `app/process.py` |
| R8 | Approval required for publishing, messaging, job applications, deletion, financial actions | `require_approval()` in `app/approvals.py`; router tests assert 409 without an approved record |
| R9 | No fake integrations or non-functional buttons | Every UI action maps to a real endpoint; unauthenticated integrations render an honest "Awaiting authentication" state |
| R10 | Never request the user's GitHub token | GitHub integration uses the already-authenticated `gh` CLI only |

---

## 3. System architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  Browser (React SPA, responsive, served by FastAPI)                │
│  Command Centre · Instagram Studio · YouTube Studio ·              │
│  LinkedIn Career Studio · Content Intelligence · Monetisation ·    │
│  Automation · Account Centre · Approvals · Logs                    │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ REST /api/*  (localhost only)
┌──────────────────────────────▼─────────────────────────────────────┐
│  FastAPI backend (uvicorn, 127.0.0.1:8777)                         │
│  ┌─────────────┐ ┌──────────────┐ ┌────────────┐ ┌─────────────┐  │
│  │ approvals   │ │ scheduler    │ │ ai client  │ │ process     │  │
│  │ gate        │ │ (threaded)   │ │ (Ollama)   │ │ allowlist   │  │
│  └─────────────┘ └──────────────┘ └────────────┘ └─────────────┘  │
│  modules: command · instagram · youtube · linkedin · content ·    │
│           monetisation · automation · accounts · ai               │
└───────┬──────────────────┬──────────────────┬──────────────────────┘
        │                  │                  │
┌───────▼──────┐  ┌────────▼───────┐  ┌───────▼───────────────────┐
│ SQLite       │  │ Ollama (local) │  │ Official platform APIs    │
│ data/nexus.db│  │ 127.0.0.1:11434│  │ Meta Graph · Google/YouTube│
│ (WAL mode)   │  │ 4GB-VRAM tuned │  │ GitHub (gh CLI) · remote  │
└──────────────┘  └────────────────┘  │ job feeds (RemoteOK/      │
                                     │ Remotive, public JSON)    │
                                     └───────────────────────────┘
```

### 3.1 Layout

```
nexus-ai/
  NEXUS_MASTER_SPEC.md      PROJECT_STATE.md     TASKS.md      SECURITY.md
  README.md  ARCHITECTURE.md  CHANGELOG.md  TEST_REPORT.md
  start_nexus.bat  stop_nexus.bat
  requirements.txt
  backend/
    app/
      main.py               # FastAPI app, static SPA hosting, lifespan scheduler
      config.py             # paths, ports, model policy, allowlists
      db.py                 # SQLite schema + helpers (WAL, foreign keys)
      security.py           # redaction, approval decorators, input guards
      approvals.py          # approval gate: create/approve/reject/enforce
      process.py            # argv-allowlisted subprocess runner (ffmpeg/ffprobe/ollama)
      ollama_client.py      # local LLM: health, generate, offline fallback engine
      activity.py           # structured logs + task history
      modules/
        command_centre.py   # system status, metrics, endpoints for dashboard
        instagram.py        # profile analysis, niches, reels, captions, calendar,
                            #   approval-gated publishing, Graph-API analytics
        youtube.py          # topics, scripts, shorts, voiceover, subtitles,
                            #   FFmpeg render, thumbnails, OAuth, approval-gated upload
        linkedin.py         # profile, branding, job discovery (public feeds),
                            #   matching, truthful CV, cover letters, applications
        content.py          # trends, audience research, platform content generation
        monetisation.py     # products, freelance leads, affiliate research,
                            #   sponsorships, verified revenue
        automation.py       # daily jobs, retries, reports, job definitions
        accounts.py         # GitHub (gh CLI), Meta, Google/YouTube, LinkedIn status
      routers.py            # wires all module routers
    tests/                  # pytest suite (API + gate + pipeline tests)
  frontend/
    package.json  vite.config.js  index.html
    src/  main.jsx  App.jsx  api.js  styles.css
          pages/ (Dashboard, Approvals, Instagram, YouTube, LinkedIn,
                  Content, Monetisation, Automation, Accounts, Logs)
  data/                     # nexus.db, credentials.json (gitignored), artifacts
  scripts/                  # helpers (build frontend, seed, smoke test)
```

### 3.2 Data model (SQLite, WAL)

`settings, activity_log, tasks, approvals, ai_calls, content_calendar, posts, media_assets,
scripts, videos, subtitles, job_listings, job_applications, niche_research, trends_cache,
audience_research, digital_products, freelance_leads, affiliate_programs, sponsorship_opportunities,
revenue_events, automation_jobs, automation_runs, accounts, calendar_entries, reports`

Key invariants:
- `revenue_events.verified INTEGER` — `1` only when a payment reference string is stored.
- `approvals.status ∈ {pending, approved, rejected}` — side-effecting modules call `require_approval(kind, payload)` first.
- `accounts` stores **references only** (path/keyring id/scopes); tokens live in gitignored `data/credentials.json` with owner-only ACLs.
- Every AI call logged in `ai_calls` (module, model, tokens, latency, fallback used).

---

## 4. Feature specification

### 4.1 Command Centre (dashboard)
- Premium responsive shell: sidebar + topbar, dark theme, mobile drawer.
- Live system status: CPU/RAM/disk, Python/Node/FFmpeg/Ollama versions, Ollama model availability, DB size.
- Task history table (every module run: name, status, duration, detail).
- Activity log stream with level filter and search.
- Approval centre: pending requests with payload preview, Approve / Reject (records actor + timestamp).
- Automation overview: next runs, last results, manual "Run now".

### 4.2 Instagram Studio
- **Profile analysis** — paste bio/posts JSON or connect Meta Graph API token; returns structured SWOT-style breakdown + improvement actions (AI-generated, labelled as such).
- **Niche research** — local AI synthesis over user-provided context + optional free public data; output includes confidence + "hypothesis, not measured data" tag.
- **Reels ideas / captions** — batch generation, hook/body/CTA structure, hashtag sets.
- **Content calendar** — week/month grid, create/edit/delete entries, each entry has status `draft → planned → approved → published`.
- **Authorised publishing** — POST creates an *approval request*; actual Graph API publish happens only with (a) stored Meta token, (b) approved record. No token → honest `requires_auth`.
- **Analytics** — real metrics only when token present; otherwise `{"requires_auth": true}` with zero invented numbers.

### 4.3 YouTube Studio
- **Topic research** — free public signals (HN Algolia, YouTube suggest endpoint via oEmbed-free paths are not used; research combines local AI + user context) with dated sources.
- **Scripts** — long-form (intro/hook/sections/CTA) and Shorts (≤60s, beat-by-beat).
- **Local voiceover** — Windows SAPI via `pyttsx3` → WAV; falls back to silent track if SAPI unavailable (never fake speech).
- **Subtitles** — SRT generated from the script with timed cues (user-editable); optional burn-in via FFmpeg.
- **Video assembly** — FFmpeg renders 1080p MP4: background + drawtext scenes + audio track.
- **Thumbnails** — Pillow renders 1280×720 PNG with title text, brand palette, safe margins.
- **OAuth uploads** — Google OAuth 2.0 authorization-code flow (device-friendly copy/paste of the code), resumable upload REST. Requires owner's Google client secret file; until then status = `awaiting_authentication`.
- **Upload** — approval-gated; never auto-uploads.
- **Analytics** — YouTube Data API `statistics` when token present; else `requires_auth`.

### 4.4 LinkedIn Career Studio
- **Profile improvement** — analyse pasted profile text → headline, about, experience bullets (only rephrased facts from input).
- **Developer branding** — post ideas, article outlines, comment templates grounded in supplied facts.
- **Remote job discovery** — official-permitted public JSON feeds (RemoteOK, Remotive) with cache + attribution; LinkedIn itself is not scraped.
- **Job matching** — score = skill overlap (token set) between profile skills and listing skills; transparent breakdown.
- **Truthful CV generation** — hard rule: output contains ONLY facts present in the supplied profile JSON; missing facts become `[not provided]`. A guard test asserts no invented employers/dates/degrees.
- **Cover letters** — same truthfulness constraint + job description grounding.
- **Application tracking** — pipeline statuses; "Submit application" always creates an approval request; actual submission only via permitted integration (none enabled by default → marked `draft_requires_approval`).

### 4.5 Content Intelligence
- **Global trends** — pulls free public feeds (Hacker News Algolia, Reddit public JSON where permitted) with timestamps; AI clusters them into themes; each cluster cites its sources. No fabricated trend scores.
- **Audience research** — persona hypotheses from niche input, explicitly tagged `hypothesis`.
- **Platform generation** — one topic → platform-tuned variants (Instagram caption, YouTube title+desc, LinkedIn post, X thread) with length limits enforced.

### 4.6 Monetisation
- **Digital products** — idea registry with validation checklist and build status (integrates conceptually with the existing `ai_business` pipeline; never overwrites it).
- **Freelance leads** — aggregated from the same permitted job feeds filtered to freelance/gig tags; deduplicated; each lead has source + fetched-at.
- **Affiliate research** — local curated directory of well-known program criteria (dated, sourced) + AI fit analysis; explicitly not a live commission feed.
- **Sponsorship opportunities** — manual/CSV import + AI outreach draft generation (draft only; sending requires approval).
- **Verified revenue tracking** — add revenue with `payment_reference`; without a reference the row is `verified=0` and the dashboard excludes it from "verified totals". Export CSV.

### 4.7 Automation
- Jobs: `daily_research`, `content_preparation`, `video_production`, `job_discovery`, `weekly_report`.
- Each job = idempotent Python function with structured result rows in `automation_runs`.
- In-process scheduler thread (interval + daily time), start/stop with the app; manual `Run now`.
- Retries: exponential backoff, max 3, recorded per attempt.
- Reports: markdown + JSON summaries in `data/reports/` and rendered in the dashboard.

### 4.8 Account Centre
- **GitHub** — detects `gh auth status`; shows account + scopes (token never displayed). Repo helpers: ensure private repo, status, push verification.
- **Meta (Instagram/Facebook)** — add/remove Graph API token (stored in `data/credentials.json`), shows token scopes and expiry; publish rights verified by a harmless `me` call.
- **Google/YouTube** — upload OAuth client config import (client id/secret file), token status, revoke.
- **LinkedIn** — documented as "no general official posting API"; enables *permitted* profile/feeds features only. Never automates LinkedIn itself.

---

## 5. API contract (localhost:8777)

All routes under `/api`. JSON in/out. Errors: `{"detail": "...", "code": "..."}`.

```
GET  /api/health                 → {status, version, ollama:{available,models}, db}
GET  /api/system/status          → versions, resources, service checks
GET  /api/logs?limit&level&q     → activity log rows
GET  /api/tasks?limit            → task history
GET  /api/approvals?status       → approval queue
POST /api/approvals              → {kind, title, payload} → pending
POST /api/approvals/{id}/approve → executes gated action if any
POST /api/approvals/{id}/reject  → {reason}
POST /api/ai/generate            → {prompt, module, system, max_tokens}

POST /api/instagram/profile/analyze
POST /api/instagram/niche/research
POST /api/instagram/reels/ideas
POST /api/instagram/captions
GET|POST|DELETE /api/instagram/calendar
POST /api/instagram/publish      → approval-gated (token required to actually publish)
GET  /api/instagram/analytics    → requires_auth unless token stored

POST /api/youtube/topics
POST /api/youtube/script
POST /api/youtube/shorts
POST /api/youtube/voiceover      → {text} → WAV path (SAPI)
POST /api/youtube/subtitles      → {text, cues} → SRT path
POST /api/youtube/render         → {script, ...} → MP4 path (ffmpeg)
POST /api/youtube/thumbnail      → {title} → PNG path (Pillow)
GET  /api/youtube/oauth/status | /start | POST /callback {code}
POST /api/youtube/upload         → approval-gated
GET  /api/youtube/analytics      → requires_auth unless token stored

POST /api/linkedin/profile/improve
POST /api/linkedin/branding
GET  /api/linkedin/jobs?skills=&remote=     → public feed results + sources
POST /api/linkedin/jobs/match               → {profile_skills, job_id}
POST /api/linkedin/cv                       → truthful generation
POST /api/linkedin/cover-letter
GET|POST /api/linkedin/applications
POST /api/linkedin/applications/{id}/submit → approval-gated

GET  /api/content/trends
POST /api/content/audience
POST /api/content/generate       → {topic, platforms[]}

GET  /api/monetisation/products|leads|affiliates|sponsorships|revenue
POST /api/monetisation/*         → create rows (revenue needs reference to verify)
GET  /api/monetisation/revenue/export

GET  /api/automation/jobs
POST /api/automation/run         → {job} manual trigger
GET  /api/automation/runs?limit
GET  /api/automation/reports

GET  /api/accounts
POST /api/accounts/{provider}/configure   → stores secret ref (never echoed)
DELETE /api/accounts/{provider}
```

---

## 6. Implementation plan (10 phases)

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 1 | Environment inspection, 4 master docs | ✅ done in this file set |
| 2 | GitHub config: `gh auth status`, private repo, `.gitignore`, first commit | see `PROJECT_STATE.md` |
| 3 | Backend core: config, DB schema, approvals, logging, process allowlist, FastAPI shell | |
| 4 | Dashboard: React SPA, Command Centre, approvals, logs | |
| 5 | Local AI: Ollama client + deterministic offline fallback + AI logging | |
| 6 | Content & video: voiceover, SRT, FFmpeg render, thumbnails | |
| 7 | Instagram / YouTube / LinkedIn studios | |
| 8 | Scheduler, approvals wiring, monetisation, accounts | |
| 9 | start/stop scripts, README/ARCHITECTURE/CHANGELOG, real test run | |
| 10 | Commit + push + verify `shahid0219/nexus-ai` | |

Progress, blockers and resumed context live in `PROJECT_STATE.md` — that file is the source of truth
for continuing work without re-reading this conversation.

---

## 7. Testing strategy

- **pytest** (`backend/tests`): approvals gate (side effects blocked until approved), truthfulness
  guard for CV generation, revenue verification invariant, module endpoints return honest
  `requires_auth` states, scheduler job registry, SRT/ffmpeg/thumbnail pipeline smoke tests.
- **Frontend build**: `npm run build` must succeed (type/JSX validity).
- **Smoke**: `GET /api/health` and `GET /api/system/status` on the running server.
- Results recorded in `TEST_REPORT.md` with real command output.

---

## 8. Honest status taxonomy

Every feature in the UI and docs carries one of:
- `implemented` — fully working locally, tested.
- `awaiting_authentication` — code complete; needs owner's official credentials/token.
- `requires_approval` — code complete; will act only after owner approval.
- `planned` — not yet built (must not appear as a clickable no-op).

No other status may be shown. Nothing may be described as "published", "uploaded", "earned" or
"analysed live" unless a real API response says so.
