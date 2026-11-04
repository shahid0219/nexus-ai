# ARCHITECTURE.md — NEXUS AI

## 1. Shape of the system

```
┌────────────────────────────────────────────────────────────────┐
│  Browser  ──  React SPA (HashRouter) served by FastAPI /        │
│               same origin, no CORS needed in production        │
└───────────────┬────────────────────────────────────────────────┘
                │  /api/*  (JSON)
┌───────────────▼────────────────────────────────────────────────┐
│  FastAPI  (backend/app/main.py)  ── 127.0.0.1:8777             │
│                                                                │
│  modules/  command_centre · instagram · youtube · linkedin     │
│            content · monetisation · automation · accounts      │
│                                                                │
│  core:  db (SQLite/WAL) · approvals · activity · security      │
│         process (allowlist) · ollama_client · credentials      │
└──────┬───────────────┬───────────────────┬─────────────────────┘
       │               │                   │
   SQLite          Ollama            Public feeds / official APIs
   data/nexus.db   127.0.0.1:11434   HN, Reddit, RemoteOK, Remotive,
                                     Meta Graph, Google OAuth/YouTube
```

One process. No message queue, no worker, no container. A background scheduler
thread lives inside the FastAPI lifespan.

## 2. Request flow

1. The SPA calls `/api/...` with `fetch`.
2. FastAPI validates the body with Pydantic.
3. The module does its work through a small set of shared helpers:
   - `activity.TaskTimer` — records a row in `tasks` and an `activity_log` entry.
   - `db.query/one/execute` — parameterised SQL only.
   - `ollama_client.generate` — local inference or the labelled fallback.
   - `process.run` — allowlisted subprocess (`ffmpeg`, `ffprobe`, `gh`), argv lists, `shell=False`.
4. Side-effecting actions call `approvals.require_approved(...)` first.
5. Errors are domain exceptions:
   - `ApprovalRequired` → HTTP **409** `{code: "approval_required", approval_id}`
   - `NexusError` → HTTP 4xx/5xx `{code, detail}`
6. Responses pass through `security.redact()` before anything is logged.

## 3. The approval gate

This is the central safety mechanism.

```
caller ──► require_approved(kind, title, payload)
              │
              ├─ exact same payload already approved, unused? ──► continue
              │
              └─ otherwise: INSERT approvals(status='pending')
                            └──► raise ApprovalRequired(approval_id)
                                     └──► 409 to the client
```

The client then calls `POST /api/approvals/{id}/approve`, and **retries the original
request**. The retry consumes the approval (single use, bound to a hash of the payload),
so an approval for £50 cannot authorise a £5000 transfer.

Gated kinds (declared in `approvals.GATED_KINDS`; an undeclared kind raises):

| Kind | Used by | Effect |
|---|---|---|
| `publish.instagram` | Instagram publish | Graph API post/reel |
| `upload.youtube` | YouTube upload | resumable video upload |
| `apply.linkedin` | LinkedIn submit | marks `ready_for_manual_submission` |
| `delete.data` | calendar delete | removes a DB row |
| `revenue.record` | revenue entry | records a financial event |
| `account.delete.*` | Account Centre | deletes stored credentials |

Nothing in the automation scheduler bypasses this: jobs prepare drafts, they do not publish.

## 4. Scheduler

`automation.Scheduler` is a daemon thread started by the FastAPI lifespan and stopped
on shutdown.

- Ticks every 30 s.
- A job is due when `now - last_run_ts >= interval_minutes`.
- On first start, `last_run_ts` is stamped so nothing fires immediately.
- `run_job` retries up to 3 times with exponential backoff; every attempt is recorded
  in `automation_runs`.
- Jobs: `daily_research`, `content_preparation`, `video_production`, `job_discovery`,
  `weekly_report`.
- Only one scheduler thread is created per process (idempotent start).

## 5. Local AI layer

```
generate(prompt)
   │
   ├─ health() says Ollama up?  ──yes──► POST /api/generate (lock held, 90 s timeout)
   │                                          │
   │                                          └─► {text, generated_by: "ollama", model}
   │
   └─ no ──► ai_fallback.<skill>(...) ──► {text, generated_by: "fallback"}
```

- `_ai_lock` serialises requests so a 4 GB GPU never gets two concurrent models.
- `_pick_model()` picks the first of the preferred small models actually pulled.
- The fallback is deterministic and useful, not a stub — it produces structured
  captions, reel beats, scripts, niche maps, CV sections and cover letters.
- **Every** AI response carries `generated_by`, and the UI renders a badge. A fallback
  is never dressed up as model output.

## 6. Media pipeline (all local)

```
script ──► pyttsx3 (SAPI) ──► data/artifacts/*.wav
       ──► cue splitter    ──► data/artifacts/*.srt
       ──► ffmpeg drawtext ──► data/artifacts/*.mp4
       ──► pillow          ──► data/artifacts/*.png
```

- Subprocesses are argv lists executed by `process.run`, never shell strings.
- Missing `ffmpeg` or SAPI produces a structured error (`tool_missing`,
  `tts_unavailable`), never a fake success.

## 7. Data model (28 tables)

| Group | Tables |
|---|---|
| Core | `settings`, `activity_log`, `tasks`, `approvals`, `ai_calls` |
| Content | `content_calendar`, `posts`, `media_assets`, `scripts`, `videos` |
| Career | `job_listings`, `job_applications` |
| Research | `niche_research`, `trends_cache`, `audience_research` |
| Money | `digital_products`, `freelance_leads`, `affiliate_programs`, `sponsorship_opportunities`, `revenue_events` |
| Ops | `automation_jobs`, `automation_runs`, `reports`, `oauth_states` |

WAL mode, foreign keys on, no ORM. Schema lives in `db.SCHEMA` and is created idempotently.

## 8. Frontend

- React 18, Vite 5, `react-router-dom` with **HashRouter** (works when the SPA is served
  from `/` without server-side routing rules).
- No UI library, no chart library, no external fonts or CDNs — the whole dashboard
  is one hand-written CSS design system (`styles.css`) so it works fully offline.
- `api.js` normalises every fetch: non-2xx becomes an `ApiError` carrying `status`,
  `code`, `approval_id` and `requires_auth`.
- `ui.jsx` provides the primitives: `Card`, `Badge`, `Btn`, `Field`, `Notice`,
  `ErrorMsg`, `Spinner`, `Tabs`, `AiMeta`, `useLoad`.
- Every control calls a real endpoint. Loading, empty, error, `approval_required`
  and `awaiting_authentication` states each have a distinct visual treatment.

## 9. Trust boundaries

| Boundary | Control |
|---|---|
| Network ingress | loopback bind only; CORS limited to the Vite dev origin |
| Network egress | allowlist of hosts in `config.ALLOWED_HOSTS` |
| Subprocess | allowlist `{ffmpeg, ffprobe, gh}`; argv only |
| Filesystem | user filenames sanitised; artifact paths must resolve inside `data/` |
| Secrets | `data/credentials.json` (gitignored); API returns presence only; `redact()` on all log text |
| Actions | approval gate before publish/send/delete/financial |
| AI | cannot execute commands or write files; output is text only |

## 10. Why these choices

- **SQLite over Postgres** — single user, single machine; zero-install and trivially backed up.
- **No ORM** — the schema is small and explicit; SQL is easier to audit.
- **HashRouter** — the app is often opened as a static build; no rewrite rules needed.
- **Manual OAuth code fallback** — the loopback listener needs a free port and a browser
  on the same machine; the manual path makes it usable when that fails.
- **Deterministic fallback** — a local-first tool that breaks without a GPU is not
  local-first. Labelling keeps it honest.
