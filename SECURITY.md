# SECURITY.md — NEXUS AI security rules

These rules are binding for every contributor and every future session on this repository.

## 1. Secrets and credentials

1. **Never** commit tokens, cookies, OAuth client secrets, API keys, session ids or passwords.
   `.gitignore` excludes `data/credentials.json`, `.env`, `*.pem`, `data/nexus.db*`.
2. GitHub access uses the machine's existing `gh` CLI authentication only. NEXUS never asks for,
   reads, logs or stores the GitHub token. `gh auth status` output is parsed for *account name and
   scopes* only; the token line is discarded.
3. Platform tokens (Meta, Google/YouTube, LinkedIn) are supplied by the owner and stored in
   `data/credentials.json`, created with owner-only permissions. The API never returns secret
   values — only `{provider, scopes, expires_at, present: true}`.
4. All log output passes through `security.redact()`, which masks anything matching token/key/
   Bearer/password/secret patterns before persistence or display.

## 2. Approval gate (irreversible or public actions)

The following **always** require an `approvals` row with `status='approved'` before execution:

- publishing/posting anything (Instagram, YouTube, any platform)
- sending messages or outreach
- submitting job applications
- deleting data (rows, files, accounts)
- any action that records or moves money (revenue entries marked verified, payouts)

Flow: module → `approvals.require_approval(kind, title, payload)` → creates `pending` row and
raises `ApprovalRequired` (HTTP 409) → owner approves in the dashboard → module re-runs and,
only with an approved row **and** valid stored credentials, performs the real side effect.
Rejection stores a reason; approval records actor + timestamp for audit.

## 3. No restriction bypass (hard prohibition)

- Never solve, skip or weaken CAPTCHA, OTP, 2FA or any verification challenge.
- Never rotate identities, spoof headers/devices, or imitate a human to defeat anti-bot systems.
- Never scrape LinkedIn, Instagram or YouTube HTML against their terms. Only official APIs and
  explicitly public JSON endpoints that permit programmatic access (RemoteOK, Remotive,
  Hacker News Algolia) are used, with caching and attribution.
- No headless-browser automation of protected platforms anywhere in this codebase.

## 4. AI safety

- The AI layer has **no** shell, file-write or network-execution tools. It returns text only.
- Subprocess execution is impossible except through `process.run()`, which accepts an explicit
  argv allowlist: `ffmpeg`, `ffprobe`, `ollama`. No `shell=True` anywhere; no string command
  interpolation into a shell.
- AI outputs are labelled (`generated_by: ollama|fallback`) and logged in `ai_calls`.
- Facts cannot be invented: CV/cover-letter generators emit only facts present in supplied
  profile data; missing items render `[not provided]`. Analytics/revenue endpoints return real
  API data only — `requires_auth` / `verified=0` otherwise. No fabricated metrics anywhere.

## 5. Data and privacy

- All data stays local: SQLite at `data/nexus.db`. No telemetry, no external analytics, no
  cloud sync.
- Personal data (profile text, CVs, job history) is never sent to third-party AI services;
  inference runs through local Ollama or the local fallback engine only.
- `redact()` runs on every log line and every API response containing account fields.
- Deletion of personal data requires an approval record (see §2).

## 6. Network egress allowlist

Allowed outbound destinations:

| Destination | Purpose |
|---|---|
| `127.0.0.1:11434` | Ollama local inference |
| `graph.facebook.com` / `instagram.com` (Graph API) | Meta publishing/analytics with owner token |
| `googleapis.com` / `oauth2.googleapis.com` / `accounts.google.com` | YouTube OAuth + upload + analytics |
| `api.remotive.com`, `remoteok.com` | permitted public job feeds |
| `hn.algolia.com` | public trends feed |
| `reddit.com/*.json` (public read) | optional public trends |
| `api.github.com` (via `gh` CLI) | repository operations |
| `github.com` | git push over HTTPS using `gh` credential helper |

Everything else is out of scope; no proxying, no tunneling, no arbitrary URL fetching from AI output.

## 7. Input handling

- All request bodies are validated with Pydantic models (types, lengths, enums).
- File uploads (if any) are size-capped and written only under `data/uploads/` with sanitised
  names (no path traversal; `os.path.basename` + allowlist of extensions).
- Rendered dashboard content is React-escaped; no `dangerouslySetInnerHTML` with model output.

## 8. Operational security

- Server binds `127.0.0.1` only — never `0.0.0.0`.
- No auto-start of publishing jobs; scheduler runs research/content-prep only, and every
  side-effecting step inside them still hits the approval gate.
- `stop_nexus.bat` terminates only processes listening on the NEXUS port and started by the
  start script (PID file), never arbitrary PIDs.
- Dependencies pinned in `requirements.txt`; only well-known FOSS packages.

## 9. Incident response

If a credential is suspected leaked: revoke it at the provider immediately, delete
`data/credentials.json`, run `git log --all -- data/credentials.json` to confirm it was never
committed, and rotate. GitHub token concerns are handled with `gh auth refresh` / GitHub's
credential rotation — the token is never handled by NEXUS code.
