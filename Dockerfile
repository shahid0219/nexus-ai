# NEXUS AI — production image
#
# Multi-stage: build the React dashboard with Node, then run the FastAPI server
# with a slim Python base. The frontend is served from the same origin as the
# API, so one container is the whole application.
#
#   docker build -t nexus-ai .
#   docker run --rm -p 8777:8777 -v nexus-data:/app/data nexus-ai
#
# Ollama is intentionally NOT bundled: it is a separate local service. Point the
# container at the host with -e OLLAMA_URL=http://host.docker.internal:11434

# ---------- stage 1: frontend ----------
FROM node:20-alpine AS frontend
WORKDIR /build
# Install dependencies first so the layer caches across source-only changes.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-fund --no-audit
COPY frontend/ ./
# The esbuild shim is only needed in restricted sandboxes; on a normal Docker
# host native esbuild works, so run vite directly.
RUN ./node_modules/.bin/vite build --outDir dist

# ---------- stage 2: runtime ----------
FROM python:3.10-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NEXUS_PORT=8777

# ffmpeg powers the video pipeline; fonts-dejavu-core provides the TTF that the
# drawtext renderer and Pillow thumbnails need; git+gh let the GitHub page inspect
# the repo when the workspace is mounted; curl is used by the healthcheck.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ffmpeg curl git ca-certificates fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist

# Runtime state (SQLite db, artifacts, credentials) lives on a volume.
RUN mkdir -p /app/data/artifacts /app/data/reports /app/data/uploads
VOLUME ["/app/data"]

# Run as a non-root user that owns the data volume.
RUN useradd --create-home --uid 10001 nexus \
 && chown -R nexus:nexus /app
USER nexus

EXPOSE 8777

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8777/api/health || exit 1

# 0.0.0.0 is required inside a container; the app still only exposes one port.
CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8777"]
