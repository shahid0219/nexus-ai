import React, { useState } from 'react'
import {
  api } from '../api.js'
import {
  AiMeta, Badge, Btn, Card, ErrorMsg, Field, Input, Notice, Spinner, useLoad,
} from '../ui.jsx'

const PLATFORMS = [
  { id: 'instagram', label: 'Instagram' },
  { id: 'youtube', label: 'YouTube' },
  { id: 'linkedin', label: 'LinkedIn' },
  { id: 'x', label: 'X / Twitter' },
]

export default function Content() {
  const [niche, setNiche] = useState('')
  const [topic, setTopic] = useState('')
  const [plats, setPlats] = useState(['instagram', 'linkedin'])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [res, setRes] = useState(null)
  const trends = useLoad(() => api.get('/api/content/trends'), [])

  const toggle = (id) => setPlats((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))

  const gen = async () => {
    setBusy(true); setErr(null)
    try { setRes(await api.post('/api/content/generate', { topic, platforms: plats })) }
    catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const audience = async () => {
    setBusy(true); setErr(null)
    try { setRes(await api.post('/api/content/audience', { niche })) }
    catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h2>Content Intelligence</h2>
        <p>Real public trend feeds, hypothesis-labelled audience research, platform-tuned generation.</p>
      </div>

      {err && <ErrorMsg error={err} />}

      <Card title="Global trends" actions={<Btn variant="ghost" busy={trends.loading} onClick={trends.reload}>Refresh</Btn>}>
        {trends.loading && !trends.data && <Spinner label="Fetching public feeds…" />}
        {trends.error && <ErrorMsg error={trends.error} onRetry={trends.reload} />}
        {trends.data?.stale && <Notice tone="warn">Live feeds unreachable — cached clusters shown.</Notice>}
        {trends.data?.sources && (
          <div className="row">
            {trends.data.sources.map((s) => (
              <Badge key={s.name} tone={s.ok ? 'ok' : 'err'}>{s.name} {s.ok ? s.count : 'offline'}</Badge>
            ))}
            <span className="dim">fetched {trends.data.fetched_at}</span>
          </div>
        )}
        {trends.data?.clusters?.map((c, i) => (
          <div key={i} className="card mt">
            <div className="card-body">
              <div className="row">
                <strong>{c.title}</strong>
                <Badge tone="info">cluster</Badge>
                {c.fetched_at && <span className="dim">fetched {c.fetched_at}</span>}
              </div>
              <p className="dim">{(c.keywords || []).join(' · ')}</p>
              {(c.items || []).map((it, k) => (
                <div key={k} className="log-row">
                  <span className="log-msg">
                    <a href={it.url} target="_blank" rel="noreferrer">{it.title || 'untitled'}</a>
                    <span className="dim"> — {it.source}{it.score != null ? ` · score ${it.score}` : ''}</span>
                  </span>
                  <span className="log-meta">{it.published_at || it.ts || ''}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
        {trends.data?.synthesis && <div className="mt"><AiMeta data={trends.data} /><pre className="result">{trends.data.synthesis}</pre></div>}
      </Card>

      <div className="grid grid-2">
        <Card title="Audience research (hypothesis)">
          <Field label="Niche"><Input value={niche} onChange={(e) => setNiche(e.target.value)} /></Field>
          <Btn busy={busy} onClick={audience} disabled={!niche.trim()}>Research audience</Btn>
        </Card>
        <Card title="Platform generation">
          <Field label="Topic"><Input value={topic} onChange={(e) => setTopic(e.target.value)} /></Field>
          <div className="row">
            {PLATFORMS.map((pl) => (
              <button key={pl.id} className={`btn btn-sm ${plats.includes(pl.id) ? 'btn-primary' : 'btn-ghost'}`} onClick={() => toggle(pl.id)}>{pl.label}</button>
            ))}
          </div>
          <Btn className="mt" busy={busy} onClick={gen} disabled={!topic.trim() || plats.length === 0}>Generate</Btn>
        </Card>
      </div>

      {res && (
        <Card title="Result">
          <div className="row">
            <AiMeta data={res} />
            {res.tag && <Badge tone="warn">{res.tag}</Badge>}
          </div>
          <ResultBlock data={res} />
        </Card>
      )}
    </div>
  )
}

function ResultBlock({ data }) {
  if (!data) return null
  if (data.results) {
    const meta = data.meta || {}
    return (
      <div className="stack mt">
        {Object.entries(data.results).map(([k, v]) => {
          const m = meta[k] || {}
          return (
            <div key={k} className="card">
              <div className="card-body">
                <div className="row">
                  <Badge tone="accent">{k}</Badge>
                  {m.generated_by && (
                    <Badge tone={m.generated_by === 'fallback' ? 'warn' : 'ok'}>{m.generated_by}</Badge>
                  )}
                  <span className="dim">
                    {typeof v === 'string' ? v.length : 0} chars
                    {m.limit ? ` / ${m.limit} limit` : ''}
                  </span>
                </div>
                <pre className="result">{typeof v === 'string' ? v : JSON.stringify(v, null, 2)}</pre>
              </div>
            </div>
          )
        })}
      </div>
    )
  }
  return <pre className="result mt">{JSON.stringify(data.result || data, null, 2)}</pre>
}
