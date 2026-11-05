"""YouTube Studio — topics, scripts, local voiceover, subtitles, FFmpeg render,
thumbnails, Google OAuth (loopback), approval-gated upload, honest analytics."""
import json
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import activity, ai_fallback, ai_router, approvals, config, credentials, db, process
from ..security import ApprovalRequired, NexusError, clamp, now_iso, sanitize_filename

router = APIRouter(prefix="/api/youtube", tags=["youtube"])

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
YOUTUBE_SCOPE = ("https://www.googleapis.com/auth/youtube.upload "
                 "https://www.googleapis.com/auth/youtube.readonly")
LOOPBACK_PORT = 8778
LOOPBACK_REDIRECT = f"http://127.0.0.1:{LOOPBACK_PORT}/oauth2/callback"

# Font candidates across Windows, Linux, macOS and the container image. The first
# one that exists wins; NDEX ships a font in tools/fonts for slim deployments.
_font_candidates = [
    # bundled (added to the Docker image and usable on any host)
    config.ROOT / "tools" / "fonts" / "DejaVuSans-Bold.ttf",
    config.ROOT / "tools" / "fonts" / "DejaVuSans.ttf",
    # Windows
    Path("C:/Windows/Fonts/arialbd.ttf"), Path("C:/Windows/Fonts/arial.ttf"),
    Path("C:/Windows/Fonts/segoeuib.ttf"), Path("C:/Windows/Fonts/segoeui.ttf"),
    # Linux (Debian/Ubuntu font packages)
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    # macOS
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    Path("/System/Library/Fonts/Helvetica.ttc"),
]


def _font_path() -> Path | None:
    for f in _font_candidates:
        try:
            if f.is_file():
                return f
        except OSError:
            continue
    return None


# ------------------------------------------------------------ topics/script ---
class TopicIn(BaseModel):
    niche: str = Field(min_length=2, max_length=120)
    count: int = Field(default=8, ge=1, le=12)


@router.post("/topics")
def topics(body: TopicIn):
    result = ai_router.generate(
        f"Suggest {body.count} YouTube video topics for: {body.niche}",
        module="youtube.topics",
        fallback=lambda: json.dumps(ai_fallback.topics(body.niche, body.count),
                                    ensure_ascii=False))
    items = None
    if result["generated_by"] == "fallback":
        try:
            items = json.loads(result["text"])
        except (ValueError, TypeError):
            items = ai_fallback.topics(body.niche, body.count)
    return {"topics": items, "text": result["text"] or None,
            "generated_by": result["generated_by"]}


class ScriptIn(BaseModel):
    topic: str = Field(min_length=2, max_length=300)
    type: str = Field(default="short", pattern="^(short|long)$")
    notes: str | None = Field(default=None, max_length=3000)


@router.post("/script")
def script(body: ScriptIn):
    result = ai_router.generate(
        f"Write a YouTube {'Short (<=60s)' if body.type == 'short' else 'long-form'} "
        f"script about: {body.topic}. Notes: {body.notes or 'none'}",
        module="youtube.script",
        fallback=lambda: ai_fallback.script(body.topic, body.type))
    text = result["text"] or ai_fallback.script(body.topic, body.type)
    sid = db.execute("INSERT INTO scripts(topic,type,content,created_ts) VALUES(?,?,?,?)",
                     (body.topic, body.type, text, now_iso()))
    return {"id": sid, "script": text, "generated_by": result["generated_by"]}


# -------------------------------------------------------------- voiceover ----
_tts_lock = threading.Lock()


class VoiceIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    rate: int = Field(default=175, ge=80, le=300)
    name: str | None = Field(default=None, max_length=80)


@router.post("/voiceover")
def voiceover(body: VoiceIn):
    """Offline TTS via Windows SAPI (pyttsx3). No cloud, no paid API."""
    out = config.ARTIFACTS_DIR / f"voiceover_{int(time.time())}_{sanitize_filename(body.name or 'nexus')}.wav"
    try:
        import pyttsx3
    except Exception as exc:
        raise NexusError(f"pyttsx3 unavailable: {exc}", code="tts_unavailable", status=503)
    try:
        with _tts_lock:
            engine = pyttsx3.init()
            engine.setProperty("rate", clamp(body.rate, 80, 300, 175))
            engine.save_to_file(body.text, str(out))
            engine.runAndWait()
            engine.stop()
    except Exception as exc:
        raise NexusError(f"Windows SAPI speech synthesis failed: {exc}",
                         code="tts_failed", status=500)
    if not out.exists() or out.stat().st_size < 100:
        raise NexusError("voiceover produced no audio (SAPI returned nothing)",
                         code="tts_failed", status=500)
    db.execute("INSERT INTO media_assets(kind,path,meta,created_ts) VALUES(?,?,?,?)",
               ("voiceover", str(out), db.dumps({"chars": len(body.text)}), now_iso()))
    activity.info("youtube", "voiceover generated", {"path": out.name,
                                                     "bytes": out.stat().st_size})
    return {"path": str(out), "bytes": out.stat().st_size, "engine": "windows_sapi",
            "generated_by": "local"}


# -------------------------------------------------------------- subtitles ----
def _ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_srt(cues: list[dict]) -> str:
    parts = []
    for i, c in enumerate(cues, 1):
        parts.append(f"{i}\n{_ts(float(c['start']))} --> {_ts(float(c['end']))}\n"
                     f"{str(c['text']).strip()}\n")
    return "\n".join(parts)


def build_cues(text: str, words_per_second: float = 2.4, max_words: int = 12) -> list[dict]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    cues, t = [], 0.0
    for sent in sentences:
        words = sent.split()
        chunks = [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words)] or [sent]
        for ch in chunks:
            dur = max(1.4, len(ch.split()) / max(words_per_second, 0.5))
            cues.append({"start": round(t, 3), "end": round(t + dur, 3), "text": ch})
            t += dur
    return cues


class SubtitlesIn(BaseModel):
    text: str | None = Field(default=None, max_length=30000)
    cues: list[dict] | None = None
    name: str | None = Field(default=None, max_length=80)


@router.post("/subtitles")
def subtitles(body: SubtitlesIn):
    if body.cues:
        cues = [{"start": c.get("start", 0), "end": c.get("end", 0),
                 "text": c.get("text", "")} for c in body.cues[:500]]
    elif body.text:
        cues = build_cues(body.text)
    else:
        raise NexusError("provide text or cues", code="invalid_input")
    if not cues:
        raise NexusError("no cues produced", code="invalid_input")
    srt = format_srt(cues)
    out = config.ARTIFACTS_DIR / f"subtitles_{int(time.time())}_{sanitize_filename(body.name or 'nexus')}.srt"
    out.write_text(srt, encoding="utf-8-sig")  # BOM keeps Windows players happy
    db.execute("INSERT INTO media_assets(kind,path,meta,created_ts) VALUES(?,?,?,?)",
               ("subtitles", str(out), db.dumps({"cues": len(cues)}), now_iso()))
    return {"path": str(out), "srt": srt, "cue_count": len(cues), "generated_by": "local"}


# ----------------------------------------------------------------- render ----
def _esc_path(p: str) -> str:
    return p.replace("\\", "/").replace(":", "\\:")


def _fontfile() -> str:
    found = _font_path()
    if found:
        return _esc_path(str(found))
    raise NexusError(
        "no TTF font found for rendering — install a font package "
        "(e.g. fonts-dejavu-core on Debian/Ubuntu) or place a .ttf in tools/fonts",
        code="tool_missing", status=503)


class Scene(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    seconds: float = Field(default=4.0, ge=1.0, le=60.0)


class RenderIn(BaseModel):
    title: str = Field(default="NEXUS", max_length=120)
    scenes: list[Scene] = Field(min_length=1, max_length=40)
    audio_path: str | None = Field(default=None, max_length=500)
    width: int | None = None
    height: int | None = None


@router.post("/render")
def render(body: RenderIn):
    """Assemble an MP4 locally: colour background + per-scene drawtext + optional audio."""
    if not config.ffmpeg_path():
        raise NexusError("ffmpeg not found on PATH", code="tool_missing", status=503)
    width = clamp(body.width or db.get_setting("video_width", "1280"), 320, 1920, 1280)
    height = clamp(body.height or db.get_setting("video_height", "720"), 240, 1080, 720)
    if width % 2 or height % 2:
        width, height = width - width % 2, height - height % 2

    stamp = int(time.time())
    text_files = []
    total = 0.0
    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    for i, scene in enumerate(body.scenes):
        sf = config.ARTIFACTS_DIR / f"scene_{stamp}_{i}.txt"
        sf.write_text(scene.text.strip(), encoding="utf-8")
        text_files.append((sf, total, total + scene.seconds))
        total += scene.seconds
    if total <= 0:
        raise NexusError("total duration must be positive", code="invalid_input")

    audio = None
    if body.audio_path:
        ap = Path(body.audio_path)
        if not ap.is_absolute():
            ap = config.ARTIFACTS_DIR / ap.name
        if not ap.exists():
            raise NexusError(f"audio not found: {body.audio_path}", code="not_found", status=404)
        audio = ap

    font = _fontfile()
    fontsize = max(24, height // 14)
    title_size = max(18, height // 30)
    filters = []
    for sf, start, end in text_files:
        filters.append(
            f"drawtext=fontfile='{font}':textfile='{_esc_path(str(sf))}'"
            f":fontsize={fontsize}:fontcolor=white:borderw=2:bordercolor=black@0.55"
            f":x=(w-text_w)/2:y=(h-text_h)/2"
            f":enable='between(t,{start:.3f},{end:.3f})'")
    filters.append(
        f"drawtext=fontfile='{font}':text='{sanitize_filename(body.title)[:60]}'"
        f":fontsize={title_size}:fontcolor=0x9fb4ff:x=(w-text_w)/2:y={height - title_size - 24}"
        f":box=1:boxcolor=black@0.35:boxborderw=8")

    out = config.ARTIFACTS_DIR / f"video_{stamp}_{sanitize_filename(body.title)}.mp4"
    args = ["ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c=0x0f1420:s={width}x{height}:d={total:.3f}:r=30"]
    if audio:
        args += ["-i", str(audio)]
    args += ["-vf", ",".join(filters), "-c:v", "libx264", "-preset", "veryfast",
             "-pix_fmt", "yuv420p"]
    if audio:
        args += ["-c:a", "aac", "-shortest"]
    else:
        args += ["-an"]
    args += ["-movflags", "+faststart", str(out)]

    res = process.run(args, timeout=600, cwd=str(config.ARTIFACTS_DIR))
    if res["returncode"] != 0 or not out.exists():
        raise NexusError(f"ffmpeg failed: {res['stderr'][-600:]}",
                         code="render_failed", status=500)
    meta = {"width": width, "height": height, "duration_s": round(total, 2),
            "scenes": len(body.scenes), "audio": bool(audio)}
    db.execute("INSERT INTO videos(title,path,status,meta,created_ts) VALUES(?,?,?, ?,?)",
               (body.title, str(out), "rendered", db.dumps(meta), now_iso()))
    db.execute("INSERT INTO media_assets(kind,path,meta,created_ts) VALUES(?,?,?,?)",
               ("video", str(out), db.dumps(meta), now_iso()))
    activity.info("youtube", "video rendered", {"file": out.name, **meta})
    return {"path": str(out), "bytes": out.stat().st_size, "generated_by": "local", **meta}


# -------------------------------------------------------------- thumbnail ----
class ThumbIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    subtitle: str | None = Field(default=None, max_length=160)


@router.post("/thumbnail")
def thumbnail(body: ThumbIn):
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1280, 720
    img = Image.new("RGB", (W, H))
    px = img.load()
    top, bottom = (16, 24, 48), (74, 38, 120)
    for y in range(H):
        t = y / H
        for x_row in range(W):  # vertical gradient
            pass
        row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        px[0, y] = row
    img = img.resize((W, H))
    # cheap horizontal variation: re-paint columns from the resized row
    draw = ImageDraw.Draw(img)

    def font(sz: int):
        found = _font_path()
        if found:
            try:
                return ImageFont.truetype(str(found), sz)
            except OSError:
                pass
        return ImageFont.load_default()

    def wrap(text: str, fnt, max_w: int) -> list[str]:
        words, lines, cur = text.split(), [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if draw.textlength(trial, font=fnt) <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines[:5]

    accent = (255, 196, 64)
    draw.rectangle([0, 0, W, 14], fill=accent)
    title_font = font(78)
    lines = wrap(body.title, title_font, W - 160)
    y = (H - len(lines) * 92) // 2 + 10
    for line in lines:
        x = (W - draw.textlength(line, font=title_font)) // 2
        draw.text((x + 4, y + 4), line, font=title_font, fill=(0, 0, 0))
        draw.text((x, y), line, font=title_font, fill=(255, 255, 255))
        y += 92
    if body.subtitle:
        sub_font = font(40)
        sub = wrap(body.subtitle, sub_font, W - 200)[0]
        sx = (W - draw.textlength(sub, font=sub_font)) // 2
        draw.text((sx, y + 18), sub, font=sub_font, fill=accent)
    badge_font = font(30)
    badge = "NEXUS AI"
    bx, by = W - draw.textlength(badge, font=badge_font) - 36, H - 56
    draw.rounded_rectangle([bx - 14, by - 10, W - 22, H - 18], radius=10, fill=(0, 0, 0, 180))
    draw.text((bx, by), badge, font=badge_font, fill=(255, 255, 255))

    out = config.ARTIFACTS_DIR / f"thumb_{int(time.time())}_{sanitize_filename(body.title)}.png"
    img.save(out, "PNG")
    db.execute("INSERT INTO media_assets(kind,path,meta,created_ts) VALUES(?,?,?,?)",
               ("thumbnail", str(out), db.dumps({"title": body.title}), now_iso()))
    activity.info("youtube", "thumbnail rendered", {"file": out.name})
    return {"path": str(out), "width": W, "height": H, "generated_by": "local"}


# ------------------------------------------------------------------ OAuth ----
def _google_client() -> tuple[str, str]:
    c = credentials.get_provider("google")
    cid, csec = c.get("client_id"), c.get("client_secret")
    if not cid or not csec:
        raise NexusError("Google OAuth client not configured (client_id/client_secret). "
                         "Import it in Account Centre.", code="awaiting_authentication",
                         status=401)
    return cid, csec


def _exchange_code(code: str) -> dict:
    cid, csec = _google_client()
    try:
        r = httpx.post(GOOGLE_TOKEN, timeout=30, data={
            "code": code, "client_id": cid, "client_secret": csec,
            "redirect_uri": LOOPBACK_REDIRECT, "grant_type": "authorization_code"})
    except httpx.HTTPError as exc:
        raise NexusError(f"token exchange unreachable: {exc}", code="network_error",
                         status=502)
    data = r.json()
    if r.status_code != 200 or "access_token" not in data:
        raise NexusError(data.get("error_description") or data.get("error") or
                         "token exchange failed", code="oauth_failed", status=502)
    expires_at = (datetime.now(timezone.utc) + timedelta(
        seconds=int(data.get("expires_in", 3500)))).isoformat(timespec="seconds")
    creds_entry = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_at": expires_at,
        "scope": data.get("scope", YOUTUBE_SCOPE),
        "token_type": data.get("token_type", "Bearer"),
    }
    credentials.set_provider("google", creds_entry, config_={"client_id": cid,
                                                             "client_secret": csec})
    db.execute("INSERT INTO oauth_states(provider,state,created_ts,status,detail) "
               "VALUES('google',?,?,'authorized','token stored') "
               "ON CONFLICT(provider) DO UPDATE SET status='authorized', detail='token stored'",
               ("manual", now_iso()))
    activity.info("youtube", "Google OAuth token stored")
    return credentials.public_view("google")


def _google_token() -> str:
    c = credentials.get_provider("google")
    token = c.get("access_token")
    if not token:
        raise NexusError("Google token missing — authorise in YouTube Studio",
                         code="awaiting_authentication", status=401)
    exp = c.get("expires_at")
    if exp:
        try:
            if datetime.fromisoformat(exp) < datetime.now(timezone.utc) - timedelta(minutes=2):
                refresh = c.get("refresh_token")
                if not refresh:
                    raise NexusError("Google token expired and no refresh token present",
                                     code="awaiting_authentication", status=401)
                cid, csec = _google_client()
                r = httpx.post(GOOGLE_TOKEN, timeout=30, data={
                    "grant_type": "refresh_token", "refresh_token": refresh,
                    "client_id": cid, "client_secret": csec})
                data = r.json()
                if "access_token" not in data:
                    raise NexusError("token refresh failed", code="oauth_failed", status=502)
                expires_at = (datetime.now(timezone.utc) + timedelta(
                    seconds=int(data.get("expires_in", 3500)))).isoformat(timespec="seconds")
                credentials.set_provider("google", {"access_token": data["access_token"],
                                                    "expires_at": expires_at})
                token = data["access_token"]
        except ValueError:
            pass
    return token


@router.get("/oauth/status")
def oauth_status():
    c = credentials.get_provider("google")
    return {
        "client_configured": bool(c.get("client_id") and c.get("client_secret")),
        "authorized": bool(c.get("access_token")),
        "expires_at": c.get("expires_at"),
        "scope": c.get("scope"),
        "redirect_uri": LOOPBACK_REDIRECT,
        "status": ("connected" if c.get("access_token")
                   else ("awaiting_authentication" if c.get("client_id")
                         else "awaiting_configuration")),
    }


def _auth_url(state: str) -> str:
    cid, _ = _google_client()
    return (f"{GOOGLE_AUTH}?client_id={cid}"
            f"&redirect_uri={LOOPBACK_REDIRECT}"
            f"&response_type=code&access_type=offline&prompt=consent"
            f"&scope={YOUTUBE_SCOPE.replace(' ', '%20')}&state={state}")


def _start_loopback(state: str) -> bool:
    """Serve the OAuth redirect on loopback and exchange the code automatically."""
    result = {"code": None}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            result["code"] = (q.get("code") or [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body><h3>NEXUS AI: authorisation received.</h3>"
                             b"<p>You can close this tab and return to the dashboard.</p>"
                             b"</body></html>")

        def log_message(self, *args):
            pass

    def runner():
        try:
            srv = HTTPServer(("127.0.0.1", LOOPBACK_PORT), Handler)
            srv.timeout = 300
            srv.handle_request()
            srv.server_close()
            if result["code"]:
                _exchange_code(result["code"])
        except Exception as exc:
            activity.warn("youtube", f"loopback listener ended: {exc.__class__.__name__}")

    threading.Thread(target=runner, daemon=True).start()
    return True


@router.get("/oauth/start")
def oauth_start():
    cid, _ = _google_client()
    state = uuid.uuid4().hex
    db.execute("INSERT INTO oauth_states(provider,state,created_ts,status) "
               "VALUES('google',?,?,'pending') "
               "ON CONFLICT(provider) DO UPDATE SET state=excluded.state, "
               "created_ts=excluded.created_ts, status='pending'", (state, now_iso()))
    started = False
    try:
        started = _start_loopback(state)
    except Exception:
        started = False
    return {
        "auth_url": _auth_url(state),
        "state": state,
        "loopback": LOOPBACK_REDIRECT if started else None,
        "manual": "If the loopback page does not appear, open auth_url, approve access, "
                  "copy the 'code' parameter from the redirect URL and submit it via "
                  "/api/youtube/oauth/callback.",
    }


class CallbackIn(BaseModel):
    code: str = Field(min_length=5, max_length=4000)


@router.post("/oauth/callback")
def oauth_callback(body: CallbackIn):
    return _exchange_code(body.code.strip())


# ----------------------------------------------------------------- upload ----
class UploadIn(BaseModel):
    video_path: str = Field(min_length=5, max_length=500)
    title: str = Field(min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    privacy: str = Field(default="private", pattern="^(private|unlisted|public)$")


def _safe_video_path(p: str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = config.ARTIFACTS_DIR / path.name
    resolved = path.resolve()
    allowed_roots = [config.ARTIFACTS_DIR.resolve(), config.DATA_DIR.resolve()]
    if not any(str(resolved).startswith(str(r)) for r in allowed_roots):
        raise NexusError("video must live under the NEXUS data directory",
                         code="path_not_allowed", status=403)
    if not resolved.exists():
        raise NexusError(f"video not found: {p}", code="not_found", status=404)
    return resolved


@router.post("/upload")
def upload(body: UploadIn):
    if not credentials.has_google_token():
        return {"requires_auth": True, "provider": "google",
                "message": "Google OAuth not authorised yet. Complete OAuth in "
                           "YouTube Studio (Account Centre) first."}
    # Validate the file before creating an approval so approvals only cover real work.
    path = _safe_video_path(body.video_path)
    payload = body.model_dump()
    try:
        record = approvals.require_approved(
            "upload.youtube", f"YouTube upload: {body.title}", payload)
    except ApprovalRequired as exc:
        return {"code": "approval_required", "approval_id": exc.approval_id,
                "kind": exc.kind,
                "message": "Uploading requires owner approval. Approve, then retry."}
    token = _google_token()
    meta = {"snippet": {"title": body.title,
                        "description": body.description or "",
                        "tags": body.tags[:30],
                        "categoryId": "22"},
            "status": {"privacyStatus": body.privacy, "selfDeclaredMadeForKids": False}}
    try:
        r = httpx.post(
            "https://www.googleapis.com/upload/youtube/v3/videos",
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json; charset=UTF-8",
                     "X-Upload-Content-Type": "video/mp4",
                     "X-Upload-Content-Length": str(path.stat().st_size)},
            json=meta, timeout=60)
        if r.status_code not in (200, 201):
            raise NexusError(f"resumable init failed: {r.text[:400]}",
                             code="upload_failed", status=502)
        location = r.headers.get("location")
        if not location:
            raise NexusError("no resumable session location returned",
                             code="upload_failed", status=502)
        total = path.stat().st_size
        chunk = 8 * 1024 * 1024
        with open(path, "rb") as fh:
            start = 0
            while start < total:
                data = fh.read(chunk)
                end = start + len(data) - 1
                pr = httpx.put(location, content=data, timeout=300, headers={
                    "Content-Range": f"bytes {start}-{end}/{total}",
                    "Content-Length": str(len(data))})
                start = end + 1
                if pr.status_code in (200, 201):
                    uploaded = pr.json()
                    vid = db.execute(
                        "INSERT INTO videos(title,path,status,meta,created_ts,remote_id) "
                        "VALUES(?,?, 'published', ?, ?, ?)",
                        (body.title, str(path), db.dumps({"privacy": body.privacy}),
                         now_iso(), uploaded.get("id")))
                    activity.info("youtube", "video uploaded",
                                  {"video_id": uploaded.get("id"), "title": body.title})
                    return {"code": "uploaded", "video_id": uploaded.get("id"),
                            "row_id": vid, "approval_id": record["id"],
                            "privacy": body.privacy}
                if pr.status_code not in (308,):
                    raise NexusError(f"upload chunk failed: {pr.status_code} {pr.text[:300]}",
                                     code="upload_failed", status=502)
        raise NexusError("upload did not complete", code="upload_failed", status=502)
    except httpx.HTTPError as exc:
        raise NexusError(f"Google APIs unreachable: {exc}", code="network_error", status=502)


# --------------------------------------------------------------- analytics ---
@router.get("/analytics")
def analytics():
    if not credentials.has_google_token():
        return {"requires_auth": True, "provider": "google",
                "message": "Analytics require an authorised Google token. "
                           "No numbers are shown without real API data."}
    token = _google_token()
    try:
        r = httpx.get("https://www.googleapis.com/youtube/v3/channels",
                      params={"part": "statistics", "mine": "true"},
                      headers={"Authorization": f"Bearer {token}"}, timeout=30)
        data = r.json()
        if r.status_code != 200 or not data.get("items"):
            raise NexusError("channel statistics unavailable", code="api_error", status=502)
        stats = data["items"][0]["statistics"]
        uploaded = db.query("SELECT remote_id, title FROM videos WHERE remote_id IS NOT NULL "
                            "ORDER BY id DESC LIMIT 10")
        per_video = []
        if uploaded:
            ids = ",".join(v["remote_id"] for v in uploaded)
            rv = httpx.get("https://www.googleapis.com/youtube/v3/videos",
                           params={"part": "statistics", "id": ids},
                           headers={"Authorization": f"Bearer {token}"}, timeout=30)
            if rv.status_code == 200:
                by_id = {v["id"]: v.get("statistics", {}) for v in rv.json().get("items", [])}
                per_video = [{"remote_id": v["remote_id"], "title": v["title"],
                              "statistics": by_id.get(v["remote_id"], {})} for v in uploaded]
        return {"requires_auth": False, "channel_statistics": stats,
                "videos": per_video, "fetched_at": now_iso(),
                "source": "YouTube Data API v3"}
    except httpx.HTTPError as exc:
        raise NexusError(f"Google APIs unreachable: {exc}", code="network_error", status=502)
