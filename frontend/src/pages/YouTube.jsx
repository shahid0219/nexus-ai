import React, { useState } from 'react'
import {
  api } from '../api.js'
import {
  AiMeta, Badge, Btn, Card, ErrorMsg, Field, Input, Notice, Result, Select, TextArea, useLoad,
} from '../ui.jsx'

export default function YouTube() {
  const [niche, setNiche] = useState('')
  const [topic, setTopic] = useState('')
  const [type, setType] = useState('short')
  const [script, setScript] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [flash, setFlash] = useState(null)
  const [out, setOut] = useState(null)
  const [media, setMedia] = useState({})
  const [render, setRender] = useState({ title: 'NEXUS short', scenes: 'Hook line\nSecond beat\nCall to action' })
  const [code, setCode] = useState('')
  const oauth = useLoad(() => api.get('/api/youtube/oauth/status'), [])
  const analytics = useLoad(() => api.get('/api/youtube/analytics'), [])

  const run = async (path, body, label) => {
    setBusy(true); setErr(null); setFlash(null)
    try {
      const d = await api.post(path, body)
      setOut(d)
      if (d?.code === 'approval_required') setFlash(`Approval requested (#${d.approval_id}). Approve it in Approvals, then retry.`)
      else if (d?.requires_auth) setFlash(d.message || 'Platform authentication required.')
      else if (d?.path) setFlash(`${label} written to ${d.path}`)
      else if (d?.code) setFlash(d.message || d.code)
      return d
    } catch (e) {
      if (e.code === 'approval_required') setFlash(`Approval requested (#${e.approval_id}). Approve it, then retry.`)
      else setErr(e)
    } finally { setBusy(false) }
  }

  const startAuth = async () => {
    setBusy(true); setErr(null)
    try {
      const d = await api.get('/api/youtube/oauth/start')
      setOut(d)
      setFlash('Open the authorisation URL, approve access, then paste the code below if the loopback page does not complete it.')
      window.open(d.auth_url, '_blank', 'noopener')
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const submitCode = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post('/api/youtube/oauth/callback', { code })
      setFlash('OAuth token stored locally.')
      setCode('')
      oauth.reload()
      analytics.reload()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const scenes = render.scenes.split(/\n{2,}/).map((s) => s.trim()).filter(Boolean)

  return (
    <div className="stack">
      <div className="page-head">
        <h2>YouTube Studio</h2>
        <p>Research, scripts, local voiceover, subtitles, FFmpeg rendering, thumbnails and approval-gated uploads.</p>
      </div>

      {flash && <Notice tone="info" onDismiss={() => setFlash(null)}>{flash}</Notice>}
      {err && <ErrorMsg error={err} />}

      <div className="grid grid-2">
        <Card title="Topic research">
          <Field label="Niche">
            <Input value={niche} onChange={(e) => setNiche(e.target.value)} placeholder="e.g. local-first AI" />
          </Field>
          <Btn busy={busy} onClick={() => run('/api/youtube/topics', { niche, count: 6 }, 'topics')}>Find topics</Btn>
        </Card>
        <Card title="Script generator">
          <Field label="Topic"><Input value={topic} onChange={(e) => setTopic(e.target.value)} /></Field>
          <Field label="Format">
            <Select value={type} onChange={(e) => setType(e.target.value)} options={[{ value: 'short', label: 'Short (≤60s)' }, { value: 'long', label: 'Long form' }]} />
          </Field>
          <Btn busy={busy} onClick={async () => {
            const d = await run('/api/youtube/script', { topic, type }, 'script')
            if (d?.script) setScript(d.script)
          }}>Write script</Btn>
        </Card>
      </div>

      <Card title="Production pipeline" actions={<span className="dim">all local · no cloud</span>}>
        <Field label="Script text (edit freely)">
          <TextArea rows={6} value={script} onChange={(e) => setScript(e.target.value)} placeholder="Paste or generate a script…" />
        </Field>
        <div className="row">
          <Btn busy={busy} onClick={async () => {
            const d = await run('/api/youtube/voiceover', { text: script }, 'voiceover')
            if (d?.path) setMedia((m) => ({ ...m, audio: d.path }))
          }} disabled={!script.trim()}>Generate voiceover</Btn>
          <Btn variant="ghost" busy={busy} onClick={async () => {
            const d = await run('/api/youtube/subtitles', { text: script }, 'subtitles')
            if (d?.path) setMedia((m) => ({ ...m, srt: d.path }))
          }} disabled={!script.trim()}>Build subtitles</Btn>
          <Btn variant="ghost" busy={busy} onClick={() => run('/api/youtube/thumbnail', { title: render.title }, 'thumbnail')}>Make thumbnail</Btn>
        </div>
        {media.audio && <p className="dim mono">audio: {media.audio}</p>}
        {media.srt && <p className="dim mono">srt: {media.srt}</p>}

        <div className="grid grid-2 mt">
          <Field label="Video title"><Input value={render.title} onChange={(e) => setRender({ ...render, title: e.target.value })} /></Field>
          <Field label="Audio path (auto-filled after voiceover)">
            <Input value={render.audio || media.audio || ''} onChange={(e) => setRender({ ...render, audio: e.target.value })} placeholder="leave blank for silent video" />
          </Field>
        </div>
        <Field label="Scenes (blank line between scenes)" hint={`${scenes.length} scene(s) detected`}>
          <TextArea rows={5} value={render.scenes} onChange={(e) => setRender({ ...render, scenes: e.target.value })} />
        </Field>
        <Btn busy={busy} onClick={async () => {
          const d = await run('/api/youtube/render', {
            title: render.title,
            scenes: scenes.map((t) => ({ text: t, seconds: 4 })),
            audio_path: render.audio || media.audio || null,
          }, 'video')
          if (d?.path) setMedia((m) => ({ ...m, video: d.path }))
        }}>Render MP4</Btn>
        {media.video && <p className="dim mono">video: {media.video}</p>}
        {out && <div className="mt"><AiMeta data={out} /></div>}
      </Card>

      <div className="grid grid-2">
        <Card title="Google / YouTube OAuth" actions={<Btn variant="ghost" busy={oauth.loading} onClick={oauth.reload}>Refresh</Btn>}>
          {oauth.error && <ErrorMsg error={oauth.error} onRetry={oauth.reload} />}
          {oauth.data && (
            <>
              <dl className="kv">
                <dt>Status</dt><dd><Badge tone={oauth.data.authorized ? 'ok' : 'warn'}>{oauth.data.status}</Badge></dd>
                <dt>Client</dt><dd>{oauth.data.client_configured ? 'configured' : 'missing'}</dd>
                <dt>Expires</dt><dd>{oauth.data.expires_at || '—'}</dd>
                <dt>Redirect</dt><dd>{oauth.data.redirect_uri}</dd>
              </dl>
              <div className="row mt">
                <Btn busy={busy} onClick={startAuth} disabled={!oauth.data.client_configured}>Start authorisation</Btn>
              </div>
              <Field label="Authorization code (manual fallback)">
                <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="paste code from redirect URL" />
              </Field>
              <Btn variant="ghost" busy={busy} onClick={submitCode} disabled={!code.trim()}>Submit code</Btn>
            </>
          )}
        </Card>
        <Card title="Upload (approval-gated)" actions={<Btn variant="ghost" busy={analytics.loading} onClick={analytics.reload}>Analytics</Btn>}>
          <Field label="Video path"><Input value={render.path || media.video || ''} onChange={(e) => setRender({ ...render, path: e.target.value })} placeholder="C:\\...\\video.mp4" /></Field>
          <Field label="Title"><Input value={render.title} onChange={(e) => setRender({ ...render, title: e.target.value })} /></Field>
          <Btn busy={busy} onClick={() => run('/api/youtube/upload', { video_path: render.path || media.video || '', title: render.title, privacy: 'private' }, 'upload')}>Request upload</Btn>
          <div className="mt">
            {analytics.error && <ErrorMsg error={analytics.error} />}
            {analytics.data && (analytics.data.requires_auth
              ? <Notice tone="warn" title="Awaiting authentication">{analytics.data.message}</Notice>
              : <Result data={analytics.data} />)}
          </div>
        </Card>
      </div>
    </div>
  )
}
