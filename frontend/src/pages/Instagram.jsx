import React, { useMemo, useState } from 'react'
import { api } from '../api.js'
import {
  AiMeta, Badge, Btn, Card, Empty, ErrorMsg, Field, Input, Notice, Result,
  Select, Spinner, Tabs, TextArea, useLoad,
} from '../ui.jsx'

const STATUS_TONE = { draft: 'neutral', planned: 'info', approved: 'accent', published: 'ok' }
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December']
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

function monthMatrix(cursor) {
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1)
  const startPad = (first.getDay() + 6) % 7 // Monday-first
  const days = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate()
  const cells = []
  for (let i = 0; i < startPad; i++) cells.push(null)
  for (let d = 1; d <= days; d++) cells.push(new Date(cursor.getFullYear(), cursor.getMonth(), d))
  while (cells.length % 7 !== 0) cells.push(null)
  return cells
}

export default function Instagram() {
  const [tab, setTab] = useState('create')
  const [profile, setProfile] = useState('')
  const [niche, setNiche] = useState('')
  const [context, setContext] = useState('')
  const [topic, setTopic] = useState('')
  const [tone, setTone] = useState('engaging')
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [flash, setFlash] = useState(null) // {tone, text}
  const [pub, setPub] = useState({ caption: '', media_url: '' })
  const [entry, setEntry] = useState({ date: new Date().toISOString().slice(0, 10), title: '', brief: '' })
  const [cursor, setCursor] = useState(() => new Date())
  const cal = useLoad(() => api.get('/api/instagram/calendar'), [])
  const analytics = useLoad(() => api.get('/api/instagram/analytics'), [])

  const entries = Array.isArray(cal.data) ? cal.data : (cal.data?.entries || [])

  const byDate = useMemo(() => {
    const m = {}
    entries.forEach((e) => { (m[e.date] = m[e.date] || []).push(e) })
    return m
  }, [entries])

  const notice = (text, n = 'info') => setFlash({ text, tone: n })

  const call = async (path, body) => {
    setBusy(true); setErr(null); setFlash(null)
    try {
      const d = await api.post(path, body)
      setOut(d)
      if (d?.requires_auth) notice(d.message || 'Platform authentication required.', 'warn')
      else if (d?.code === 'approval_required') notice(`Approval requested (#${d.approval_id}) — see the Approvals page, approve it, then retry.`, 'info')
      else if (d?.code === 'published') notice('Published via the official Graph API.', 'ok')
      else if (d?.code) notice(d.message || d.code, 'info')
      return d
    } catch (e) {
      if (e.code === 'approval_required') notice(`Approval requested (#${e.approval_id}) — approve it in Approvals, then retry.`, 'info')
      else setErr(e)
    } finally { setBusy(false) }
  }

  const delEntry = async (id) => {
    setBusy(true); setErr(null); setFlash(null)
    try {
      const d = await api.del(`/api/instagram/calendar/${id}`)
      if (d?.code === 'approval_required') notice(`Deletion needs approval (#${d.approval_id}). Approve it in Approvals, then click Delete again.`, 'info')
      else if (d?.code === 'deleted') { notice('Entry deleted.', 'ok'); cal.reload() }
      else notice(d?.message || 'Done.', 'info')
    } catch (e) {
      if (e.code === 'approval_required') notice(`Deletion needs approval (#${e.approval_id}). Approve it, then retry.`, 'info')
      else setErr(e)
    } finally { setBusy(false) }
  }

  const addEntry = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post('/api/instagram/calendar', { ...entry, platform: 'instagram', status: 'draft' })
      setEntry({ ...entry, title: '', brief: '' })
      notice('Calendar entry created (draft).', 'ok')
      cal.reload()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const cells = monthMatrix(cursor)

  return (
    <div className="stack">
      <div className="page-head">
        <h2>Instagram Studio</h2>
        <p>Analysis, niche research, ideas, captions and a publish-ready calendar — publishing is approval-gated.</p>
      </div>

      <Tabs value={tab} onChange={setTab} tabs={[
        { id: 'create', label: 'Create' },
        { id: 'calendar', label: `Calendar${entries.length ? ` (${entries.length})` : ''}` },
        { id: 'analytics', label: 'Analytics' },
      ]} />

      {flash && (
        <Notice tone={flash.tone} onDismiss={() => setFlash(null)}>
          {flash.tone === 'warn' && <Badge tone="warn">Awaiting authentication</Badge>} {flash.text}
        </Notice>
      )}
      {err && <ErrorMsg error={err} />}

      {tab === 'create' && (
        <>
          <div className="grid grid-2">
            <Card title="Profile analysis">
              <Field label="Paste your bio / recent posts">
                <TextArea rows={6} value={profile} onChange={(e) => setProfile(e.target.value)} placeholder="Bio, captions, positioning…" />
              </Field>
              <Btn busy={busy} onClick={() => call('/api/instagram/profile/analyze', { profile_text: profile })}>Analyse profile</Btn>
            </Card>
            <Card title="Niche research">
              <Field label="Niche">
                <Input value={niche} onChange={(e) => setNiche(e.target.value)} placeholder="e.g. budget travel photography" />
              </Field>
              <Field label="Context (optional)">
                <TextArea rows={3} value={context} onChange={(e) => setContext(e.target.value)} placeholder="Audience, region, past results…" />
              </Field>
              <Btn busy={busy} onClick={() => call('/api/instagram/niche/research', { niche, context: context || null })}>Research niche</Btn>
            </Card>
          </div>

          <Card title="Content generation">
            <div className="grid grid-2">
              <Field label="Topic">
                <Input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. saving on flights" />
              </Field>
              <Field label="Tone">
                <Select value={tone} onChange={(e) => setTone(e.target.value)} options={['engaging', 'educational', 'bold', 'friendly']} />
              </Field>
            </div>
            <div className="row">
              <Btn busy={busy} onClick={() => call('/api/instagram/captions', { topic, count: 3, tone })}>Generate captions</Btn>
              <Btn variant="ghost" busy={busy} onClick={() => call('/api/instagram/reels/ideas', { topic, count: 3 })}>Reels ideas</Btn>
            </div>
            {out && <div className="mt"><AiMeta data={out} /><Result data={out} /></div>}
          </Card>

          <Card title="Publish (approval-gated)" actions={<Badge tone="warn">requires approval + Meta token</Badge>}>
            <p className="dim">
              The official Instagram Graph API publishes photo/video posts only and needs a
              publicly accessible <span className="mono">media_url</span>. This creates an approval
              request first; nothing is posted without your approval and a stored token.
            </p>
            <Field label="Caption">
              <TextArea rows={3} value={pub.caption} onChange={(e) => setPub({ ...pub, caption: e.target.value })} placeholder="Post caption…" />
            </Field>
            <Field label="Media URL (public image/video URL)" hint="Required by the Graph API for the actual publish step.">
              <Input value={pub.media_url} onChange={(e) => setPub({ ...pub, media_url: e.target.value })} placeholder="https://…" />
            </Field>
            <Btn busy={busy} disabled={!pub.caption.trim()} onClick={() => call('/api/instagram/publish', {
              caption: pub.caption,
              media_url: pub.media_url.trim() || null,
            })}>Request publish</Btn>
          </Card>
        </>
      )}

      {tab === 'calendar' && (
        <>
          <Card title="Add entry">
            <div className="grid grid-3">
              <Field label="Date"><Input type="date" value={entry.date} onChange={(e) => setEntry({ ...entry, date: e.target.value })} /></Field>
              <Field label="Title"><Input value={entry.title} onChange={(e) => setEntry({ ...entry, title: e.target.value })} placeholder="Reel: 3 flight hacks" /></Field>
              <Field label="Brief"><Input value={entry.brief} onChange={(e) => setEntry({ ...entry, brief: e.target.value })} placeholder="Hook + CTA" /></Field>
            </div>
            <Btn busy={busy} disabled={!entry.title.trim()} onClick={addEntry}>Add to calendar</Btn>
          </Card>

          <Card
            title={`${MONTHS[cursor.getMonth()]} ${cursor.getFullYear()}`}
            actions={
              <div className="row">
                <Btn variant="ghost" busy={busy} onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}>‹</Btn>
                <Btn variant="ghost" onClick={() => setCursor(new Date())}>Today</Btn>
                <Btn variant="ghost" busy={busy} onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}>›</Btn>
                <Btn variant="ghost" onClick={cal.reload} busy={cal.loading}>Refresh</Btn>
              </div>
            }
          >
            {cal.error && <ErrorMsg error={cal.error} onRetry={cal.reload} />}
            {cal.loading && !cal.data && <Spinner />}
            {!cal.error && (
              <div className="cal-grid">
                {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => (
                  <div key={d} className="cal-head">{d}</div>
                ))}
                {cells.map((d, i) => {
                  const key = d ? iso(d) : `x${i}`
                  const dayEntries = d ? (byDate[iso(d)] || []) : []
                  const isToday = d && iso(d) === iso(new Date())
                  return (
                    <div key={key} className={`cal-cell ${d ? '' : 'cal-blank'} ${isToday ? 'cal-today' : ''}`}>
                      {d && <span className="cal-daynum">{d.getDate()}</span>}
                      {dayEntries.map((e) => (
                        <div key={e.id} className={`cal-chip c-${e.status}`} title={`${e.title}${e.brief ? ` — ${e.brief}` : ''} (${e.status})`}>
                          <span className="cal-chip-title">{e.title}</span>
                          <button
                            className="cal-chip-x"
                            disabled={busy}
                            onClick={() => delEntry(e.id)}
                            aria-label={`Delete ${e.title}`}
                          >×</button>
                        </div>
                      ))}
                    </div>
                  )
                })}
              </div>
            )}
            <div className="row mt">
              {['draft', 'planned', 'approved', 'published'].map((s) => (
                <Badge key={s} tone={STATUS_TONE[s]}>{s}</Badge>
              ))}
              <span className="dim">deleting an entry also requires approval</span>
            </div>
          </Card>

          <Card title="All entries">
            {entries.length === 0 && <Empty>No planned content. Add your first entry above.</Empty>}
            {entries.length > 0 && (
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Date</th><th>Title</th><th>Brief</th><th>Status</th><th /></tr></thead>
                  <tbody>
                    {entries.map((e) => (
                      <tr key={e.id}>
                        <td className="mono">{e.date}</td>
                        <td>{e.title}</td>
                        <td className="muted">{e.brief || '—'}</td>
                        <td><Badge tone={STATUS_TONE[e.status] || 'neutral'}>{e.status}</Badge></td>
                        <td><Btn variant="danger" busy={busy} onClick={() => delEntry(e.id)}>Delete</Btn></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}

      {tab === 'analytics' && (
        <Card title="Instagram analytics" actions={<Btn variant="ghost" onClick={analytics.reload} busy={analytics.loading}>Refresh</Btn>}>
          {analytics.loading && !analytics.data && <Spinner />}
          {analytics.error && <ErrorMsg error={analytics.error} onRetry={analytics.reload} />}
          {analytics.data && (analytics.data.requires_auth
            ? (
              <div className="stack">
                <Notice tone="warn" title="Awaiting authentication">
                  <Badge tone="warn">awaiting_authentication</Badge>{' '}
                  {analytics.data.message || 'Connect a Meta Graph token + ig_user_id in Account Centre. No numbers are shown without real API data.'}
                </Notice>
              </div>
            )
            : <Result data={analytics.data} />)}
        </Card>
      )}
    </div>
  )
}
