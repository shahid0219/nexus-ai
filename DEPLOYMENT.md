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
files and GPU access). From a container:

```bash
# Windows / macOS
docker run --rm -p 8777:8777 -v nexus-data:/app/data \
  -e OLLAMA_URL=http://host.docker.internal:11434 nexus-ai

# Linux
docker run --rm -p 8777:8777 -v nexus-data:/app/data \
  --add-host=host.docker.internal:host-gateway \
  -e OLLAMA_URL=http://host.docker.internal:11434 nexus-ai
```

If Ollama is unreachable the app does not fail: `/api/ai/status` reports it honestly and
generation falls back to the labelled deterministic templates.

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

## 6. What is *not* deployed for you

- **No public hosting.** There is no Render/Railway/Vercel deployment in this repo, by
  design: those are third-party services, and this project is local-first.
- **No platform credentials.** Instagram and YouTube stay `awaiting_configuration` until
  you create your own Meta app and Google OAuth client.
- **No bundled model weights.** Pull them yourself: `ollama pull qwen2.5-coder:3b`.
