# Deploying NEXUS AI

NEXUS is a **local-first** application. There is no hosted service to sign up for and
no paid tier. "Deployment" means running it on a machine you control — your laptop, a
home server, or a container on your own hardware.

Everything below was executed on the development machine (Windows 10, Docker 28.4.0)
unless marked otherwise.

---

## 1. Windows desktop (the primary target)

```bat
cd C:\path\to\nexus-ai
start_nexus.bat
```

Open <http://127.0.0.1:8777>. Stop with `stop_nexus.bat`.

`start_nexus.bat` is self-healing:

| Step | Behaviour |
|---|---|
| Python | resolves `python` from PATH, else from the default per-user install locations |
| Dependencies | installs `requirements.txt` only if an import check fails |
| Frontend | builds `frontend/dist` on first run only |
| FFmpeg | uses PATH, else the WinGet / hermes / `tools\ffmpeg` locations |
| Ollama | starts `ollama serve` if it is installed but not listening, then reports model state |
| Port | refuses to start if 8777 is already in use |

Nothing is downloaded without being reported on screen.

## 2. Docker (any OS)

```bash
docker build -t nexus-ai .
docker run --rm -p 8777:8777 -v nexus-data:/app/data nexus-ai
```

Then open <http://127.0.0.1:8777>.

The image is a two-stage build: Node 20 compiles the React dashboard, and a
`python:3.10-slim` runtime serves the API **and** the built dashboard from the same
origin on port 8777. It installs FFmpeg for the video pipeline, runs as an unprivileged
user (uid 10001), and declares a `HEALTHCHECK` against `/api/health`.

### Persistence

`/app/data` is a volume. It holds:

| Path | Contents |
|---|---|
| `data/nexus.db` | SQLite database (all application state) |
| `data/credentials.json` | local credential store — **gitignored, never baked into the image** |
| `data/artifacts/` | rendered MP4s, thumbnails, audio, subtitles |
| `data/reports/` | generated markdown reports |

Lose the volume and you lose the data; the image itself is stateless.

### Talking to Ollama on the host

Ollama is a separate service and is deliberately not bundled (it needs its own model
files and GPU access). **Inside a container `localhost` is the container, not your PC**,
so `OLLAMA_URL` must name the host.

```bash
# Windows / macOS (Docker Desktop already maps host.docker.internal)
docker run --rm -p 8777:8777 -v nexus-data:/app/data \
  -e OLLAMA_URL=http://host.docker.internal:11434 nexus-ai

# Linux
docker run --rm -p 8777:8777 -v nexus-data:/app/data \
  --add-host=host.docker.internal:host-gateway \
  -e OLLAMA_URL=http://host.docker.internal:11434 nexus-ai
```

Or use the bundled compose file, which sets all of this for you:

```bash
docker compose up --build
```

#### Verified on Windows

This exact configuration was tested end to end:

```text
container -> http://host.docker.internal:11434/api/tags
            -> 6 models listed
container -> POST /api/ai/generate
            -> generated_by=ollama, model=qwen2.5-coder:3b, text="NEXUS_DOCKER_REAL"
```

Ollama was left on its default **`127.0.0.1:11434`** bind. Docker Desktop's host proxy
is the only path in, so port 11434 is never exposed to the LAN. That is the safer
setup and the one to prefer.

#### If `host.docker.internal` does not resolve

On some Linux/Docker versions the name only exists when you add it explicitly. The
`--add-host=host.docker.internal:host-gateway` flag (already in the command and compose
file above) is the fix.

#### If you still must widen Ollama's bind

Only do this if the proxy route genuinely fails, and understand the trade-off: there
is **no authentication** on port 11434.

```powershell
# 1. Bind Ollama to all interfaces (persistent for the current user)
[Environment]::SetEnvironmentVariable('OLLAMA_HOST', '0.0.0.0:11434', 'User')

# 2. Restart Ollama so it picks the change up
Stop-Process -Name ollama -ErrorAction SilentlyContinue
ollama serve

# 3. Confirm what it is actually listening on
netstat -ano | Select-String ':11434'
```

Then restrict the firewall to the Docker subnet instead of opening the port:

```powershell
New-NetFirewallRule -DisplayName "Ollama (Docker subnet only)" `
  -Direction Inbound -Protocol TCP -LocalPort 11434 `
  -RemoteAddress 172.17.0.0/16 -Action Allow
```

Never port-forward `11434` on your router and never expose it through a public tunnel.
To undo the bind change:

```powershell
[Environment]::SetEnvironmentVariable('OLLAMA_HOST', $null, 'User')
```

If Ollama is unreachable the app does not fail: `/api/ai/status` reports it honestly,
shows a hint telling you what to fix, and generation falls back to the labelled
deterministic templates.

### Health and logs

```bash
docker logs -f <container>
curl http://127.0.0.1:8777/api/health
curl http://127.0.0.1:8777/api/ai/status
```

## 3. Bare-metal Linux / macOS

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
(cd frontend && npm install && npm run build)
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8777
```

For a systemd unit, point `WorkingDirectory` at the checkout, run the command above, and
set `Restart=on-failure`.

## 4. Configuration

All settings are environment variables with safe defaults:

| Variable | Default | Purpose |
|---|---|---|
| `NEXUS_PORT` | `8777` | HTTP port (8765 is used by another local project) |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | local model server |
| `NEXUS_AI_TOKENS` | `1024` | generation token cap |
| `NEXUS_AI_TIMEOUT` | `90` | seconds per provider call |
| `NEXUS_AI_MAX_MODEL_GB` | `5.5` | refuse to load larger local models |
| `NEXUS_AI_RETRIES` | `1` | transient retries per provider |
| `NEXUS_AI_BACKOFF` | `1.5` | exponential backoff base (seconds) |

Provider API keys (optional) are stored through the AI Settings page and written to
`data/credentials.json`. They are never returned by the API and never enter the image.

## 5. Security posture

- Binds **127.0.0.1** by default; only the container sets `0.0.0.0`.
- No authentication layer is included. **If you expose this beyond localhost, put it
  behind a reverse proxy with authentication** — it holds credentials and can publish.
- Credentials are stored in a gitignored file with restrictive permissions.
- Publishing, uploading, deleting, spending and messaging all require explicit approval
  recorded in the Approval Centre.
- The subprocess allowlist is `ffmpeg`, `ffprobe`, `gh`, `git` only — no shell.

## 6. Project website (GitHub Pages)

`site/` is a static project site published to <https://shahid0219.github.io/nexus-ai/>
by `.github/workflows/pages.yml` on every push that changes `site/`. It uses the
official `actions/upload-pages-artifact` and `actions/deploy-pages` actions with the
minimum permissions (`pages: write`, `id-token: write`).

**GitHub Pages hosts the marketing page only. It does not run the Python backend.**
The application is local-first software you run on your own hardware.

Pages must be set to **Settings → Pages → Source: GitHub Actions** once. This is
already configured on this repository; a fresh fork needs the one-time switch.

To preview the site locally:

```bash
python -m http.server 8899 --directory site
# http://127.0.0.1:8899
```

## 7. Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request:

| Job | What it proves |
|---|---|
| Backend tests | `pyflakes` is clean; the full pytest suite passes (no model or key needed) |
| Frontend build | `npm ci` + production build; `dist/index.html` and hashed assets exist |
| Repository integrity | the project secret scanner finds nothing; no `data/`, `*.db`, `.env`, `node_modules` or `dist` is tracked; the site's markers and assets exist |
| Docker image build | the image builds, the container starts, `/api/health` answers and the `HEALTHCHECK` reports healthy |

The workflow needs no repository secrets — that is the point of a zero-key design.

## 8. What is *not* deployed for you

- **No public hosting of the application.** Only the static page is published. There
  is no Render/Railway/Vercel deployment by design: this project is local-first.
- **No platform credentials.** Instagram and YouTube stay `awaiting_configuration` until
  you create your own Meta app and Google OAuth client.
- **No bundled model weights.** Pull them yourself: `ollama pull qwen2.5-coder:3b`.
