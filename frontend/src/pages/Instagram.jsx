import React, { useState } from 'react'
import { api } from '../api.js'
import {
  AiMeta, Badge, Btn, Card, Empty, ErrorMsg, Field, Input, Notice, Result,
  Select, Spinner, Tabs, TextArea, useLoad,
} from '../ui.jsx'

function AuthState({ msg }) {
  return <Notice tone="warn" title="Awaiting authentication">{msg || 'Connect the platform in Account Centre to enable this.'}</Notice>
}

export default function Instagram() {
  const [tab, setTab] = useState('create')
  const [profile, setProfile] = useState('')
  const [niche, setNiche] = useState('')
  const [topic, setTopic] = useState('')
  const [tone, setTone] = useState('engaging')
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [flash, setFlash] = useState(null)
  const [entry, setEntry] = useState({ date: new Date().toISOString().slice(0, 10), title: '', brief: '' })
  const cal = useLoad(() => api.get('/api/instagram/calendar'), [])
  const analytics = useLoad(() => api.get('/api/instagram/analytics'), [])

  const call = async (path, body) => {
    setBusy(true); setErr(null); setFlash(null)
    try {
      const d = await api.post(path, body)
      setOut(d)
      if (d?.code === 'approval_required') setFlash(`Approval requested (#${d.approval_id}) — approve it in Approvals, then retry.`)
      else if (d?.code) setFlash(d.message || d.code)
      return d
    } catch (e) {
      if (e.code === 'approval_required') setFlash(`Approval requested (#${e.approval_id}) — approve it in Approvals, then retry.`)
      else setErr(e)
    } finally { setBusy(false) }
  }

  const delEntry = async (id) => {
    setBusy(true); setErr(null); setFlash(null)
    try {
      const d = await api.del(`/api/instagram/calendar/${id}`)
      if (d?.code === 'approval_required') setFlash(`Deletion needs approval (#${d.approval_id}). Approve it in Approvals, then click Delete again.`)
      else if (d?.code === 'deleted') { setFlash('Entry deleted.'); cal.reload() }
      else setFlash(d?.message || 'Done.')
    } catch (e) {
      if (e.code === 'approval_required') setFlash(`Deletion needs approval (#${e.approval_id}). Approve it, then retry.`)
      else setErr(e)
    } finally { setBusy(false) }
  }

  const addEntry = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post('/api/instagram/calendar', { ...entry, platform: 'instagram', status: 'draft' })
      setEntry({ ...entry, title: '', brief: '' })
      setFlash('Calendar entry created.')
      cal.reload()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h2>Instagram Studio</h2>
        <p>Analysis, niche research, ideas, captions and a publish-ready calendar — publishing is approval-gated.</p>
      </div>

      <Tabs value={tab} onChange={setTab} tabs={[
        { id: 'create', label: 'Create' },
        { id: 'calendar', label: `Calendar${cal.data ? ` (${cal.data.length})` : ''}` },
        { id: 'analytics', label: 'Analytics' },
      ]} />

      {flash && <Notice tone="info" onDismiss={() => setFlash(null)}>{flash}</Notice>}
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
              <Btn busy={busy} onClick={() => call('/api/instagram/niche/research', { niche })}>Research niche</Btn>
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
              <Btn variant="ghost" busy={busy} onClick={() => call('/api/instagram/publish', { caption: topic })}>Request publish</Btn>
            </div>
            {out && <div className="mt"><AiMeta data={out} /><Result data={out} /></div>}
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
            <Btn busy={busy} onClick={addEntry}>Add to calendar</Btn>
          </Card>
          <Card title="Calendar" actions={<Btn variant="ghost" onClick={cal.reload} busy={cal.loading}>Refresh</Btn>}>
            {cal.error && <ErrorMsg error={cal.error} onRetry={cal.reload} />}
            {cal.loading && !cal.data && <Spinner />}
            {cal.data && cal.data.length === 0 && <Empty>No planned content. Add your first entry above.</Empty>}
            {cal.data && cal.data.length > 0 && (
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Date</th><th>Title</th><th>Brief</th><th>Status</th><th /></tr></thead>
                  <tbody>
                    {cal.data.map((e) => (
                      <tr key={e.id}>
                        <td className="mono">{e.date}</td>
                        <td>{e.title}</td>
                        <td className="muted">{e.brief || '—'}</td>
                        <td><Badge tone={e.status === 'published' ? 'ok' : e.status === 'approved' ? 'info' : 'neutral'}>{e.status}</Badge></td>
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
            ? <AuthState msg={analytics.data.message} />
            : <Result data={analytics.data} />)}
        </Card>
      )}
    </div>
  )
}
