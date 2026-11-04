# TEST_REPORT.md — NEXUS AI

**Run date:** 2026-11-04
**Command:** `python -m pytest -q` (from project root)
**Result:** **31 passed, 1 skipped** in 77.12 s

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
