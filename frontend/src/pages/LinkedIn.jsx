import React, { useState } from 'react'
import { api, qs } from '../api.js'
import {
  AiMeta, Badge, Btn, Card, Empty, ErrorMsg, Field, Input, Notice, Result,
  Spinner, Tabs, TextArea, useLoad,
} from '../ui.jsx'

const emptyProfile = {
  name: '', headline: '', skills: '', experience: '', education: '',
}

function splitList(s) { return (s || '').split(/[,\n]/).map((x) => x.trim()).filter(Boolean) }

function docText(data) {
  if (data == null) return ''
  if (typeof data === 'string') return data
  for (const key of ['cv_markdown', 'markdown', 'text', 'cover_letter', 'output']) {
    if (typeof data[key] === 'string' && data[key]) return data[key]
  }
  return JSON.stringify(data, null, 2)
}

function DocumentOut({ data, title }) {
  const [copied, setCopied] = useState(false)
  if (!data) return null
  const text = docText(data)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }
  return (
    <div className="mt">
      <div className="doc-head">
        <div className="doc-badges">
          {(data.truthfulness || typeof data.cv_markdown === 'string') && (
            <Badge tone="warn">truthfulness: facts only from your profile</Badge>
          )}
          {data.generated_by && <Badge tone={data.generated_by === 'fallback' ? 'warn' : 'ok'}>{data.generated_by}</Badge>}
          {Array.isArray(data.missing) && data.missing.length > 0 && (
            <Badge tone="info">missing: {data.missing.join(', ')}</Badge>
          )}
        </div>
        <div className="row">
          <Btn variant="ghost" onClick={copy}>{copied ? 'Copied ✓' : 'Copy'}</Btn>
        </div>
      </div>
      <pre className="result">{text}</pre>
      {(data.truthfulness || data.disclaimer) && (
        <p className="dim mt">{data.truthfulness || data.disclaimer}</p>
      )}
    </div>
  )
}

function MatchOut({ data }) {
  if (!data || data.score === undefined) return null
  return (
    <div className="stack mt">
      <div className="row">
        <div className="stat"><span className="k">Match score</span><span className="v">{data.score}%</span></div>
        <Badge tone="info">{data.breakdown?.matched ?? (data.matched || []).length} of {data.breakdown?.your_skills ?? '?'} skills matched</Badge>
      </div>
      {Array.isArray(data.matched) && data.matched.length > 0 && (
        <div className="row">{data.matched.map((m) => <Badge key={m} tone="ok">{m}</Badge>)}</div>
      )}
      {Array.isArray(data.missing_top) && data.missing_top.length > 0 && (
        <div className="row">
          <span className="dim">not covered:</span>
          {data.missing_top.map((m) => <Badge key={m}>{m}</Badge>)}
        </div>
      )}
      {data.job && (
        <p className="dim">
          {data.job.title} — {data.job.company}{' '}
          {data.job.url && <a href={data.job.url} target="_blank" rel="noreferrer">listing</a>}
        </p>
      )}
      {data.note && <p className="dim">{data.note}</p>}
    </div>
  )
}

export default function LinkedIn() {
  const [tab, setTab] = useState('profile')
  const [p, setP] = useState(emptyProfile)
  const [profileText, setProfileText] = useState('')
  const [facts, setFacts] = useState('')
  const [targetRole, setTargetRole] = useState('')
  const [skills, setSkills] = useState('')
  const [remote, setRemote] = useState(true)
  const [jobText, setJobText] = useState('')
  const [company, setCompany] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [flash, setFlash] = useState(null)
  const [out, setOut] = useState(null)
  const [app, setApp] = useState({ role: '', company: '', notes: '' })
  const jobs = useLoad(
    () => api.get(`/api/linkedin/jobs${qs({ skills, remote: remote ? 'true' : 'false' })}`),
    [skills, remote],
  )
  const apps = useLoad(() => api.get('/api/linkedin/applications'), [])

  const post = async (path, body, label) => {
    setBusy(true); setErr(null); setFlash(null)
    try {
      const d = await api.post(path, body)
      setOut(d)
      if (d?.requires_auth) setFlash({ tone: 'warn', text: d.message || 'Authentication required.' })
      else if (d?.code === 'approval_required') setFlash({ tone: 'info', text: `Approval requested (#${d.approval_id}) — approve it in Approvals, then retry.` })
      else if (d?.code) setFlash({ tone: 'info', text: d.message || d.code })
      else if (label) setFlash({ tone: 'ok', text: `${label} ready.` })
      return d
    } catch (e) {
      if (e.code === 'approval_required') setFlash({ tone: 'info', text: `Approval requested (#${e.approval_id}) — approve it, then retry.` })
      else setErr(e)
    } finally { setBusy(false) }
  }

  const profileObj = () => ({
    name: p.name || null,
    headline: p.headline || null,
    skills: splitList(p.skills),
    experience: splitList(p.experience).map((line) => {
      const [role, company, dates, ...rest] = line.split('|').map((x) => x.trim())
      return { role, company, dates, bullets: rest.filter(Boolean) }
    }),
    education: splitList(p.education).map((line) => {
      const [degree, institution, dates] = line.split('|').map((x) => x.trim())
      return { degree, institution, dates }
    }),
  })

  const addApp = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post('/api/linkedin/applications', app)
      setApp({ role: '', company: '', notes: '' })
      setFlash({ tone: 'ok', text: 'Application tracked (draft).' })
      apps.reload()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const appRows = Array.isArray(apps.data) ? apps.data : (apps.data?.applications || [])
  const jobRows = jobs.data?.jobs || (Array.isArray(jobs.data) ? jobs.data : [])

  return (
    <div className="stack">
      <div className="page-head">
        <h2>LinkedIn Career Studio</h2>
        <p>Truthful CVs, permitted job discovery and application tracking. LinkedIn itself is never automated.</p>
      </div>

      <Tabs value={tab} onChange={setTab} tabs={[
        { id: 'profile', label: 'Profile & CV' },
        { id: 'jobs', label: `Jobs${jobRows.length ? ` (${jobRows.length})` : ''}` },
        { id: 'applications', label: `Applications${appRows.length ? ` (${appRows.length})` : ''}` },
      ]} />

      {flash && (
        <Notice tone={flash.tone || 'info'} onDismiss={() => setFlash(null)}>
          {flash.tone === 'warn' && <Badge tone="warn">Awaiting authentication</Badge>} {flash.text}
        </Notice>
      )}
      {err && <ErrorMsg error={err} />}

      {tab === 'profile' && (
        <>
          <div className="grid grid-2">
            <Card title="Improve pasted profile">
              <Field label="Paste your current profile text">
                <TextArea rows={7} value={profileText} onChange={(e) => setProfileText(e.target.value)} />
              </Field>
              <Btn busy={busy} onClick={() => post('/api/linkedin/profile/improve', { profile_text: profileText })}>Improve</Btn>
            </Card>
            <Card title="Developer branding ideas">
              <Field label="Facts you can prove (projects, results)">
                <TextArea rows={5} value={facts} onChange={(e) => setFacts(e.target.value)} />
              </Field>
              <Btn busy={busy} onClick={() => post('/api/linkedin/branding', { facts })}>Generate ideas</Btn>
            </Card>
          </div>

          <Card title="Structured profile → truthful CV" actions={<Badge tone="warn">facts only from your profile</Badge>}>
            <div className="grid grid-2">
              <Field label="Name"><Input value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} /></Field>
              <Field label="Headline"><Input value={p.headline} onChange={(e) => setP({ ...p, headline: e.target.value })} /></Field>
            </div>
            <Field label="Skills (comma separated)"><Input value={p.skills} onChange={(e) => setP({ ...p, skills: e.target.value })} placeholder="Python, FastAPI, SQLite" /></Field>
            <Field label="Experience — one per line: role | company | dates | bullet" hint="Missing dates stay [not provided]">
              <TextArea rows={3} value={p.experience} onChange={(e) => setP({ ...p, experience: e.target.value })} placeholder="Developer | Acme | 2020-2023 | Built internal tools" />
            </Field>
            <Field label="Education — one per line: degree | institution | dates">
              <TextArea rows={2} value={p.education} onChange={(e) => setP({ ...p, education: e.target.value })} />
            </Field>
            <div className="row">
              <Field label="Target role"><Input value={targetRole} onChange={(e) => setTargetRole(e.target.value)} /></Field>
            </div>
            <Btn busy={busy} onClick={() => post('/api/linkedin/cv', { profile: profileObj(), target_role: targetRole || null }, 'CV')}>Generate CV</Btn>
          </Card>
        </>
      )}

      {tab === 'jobs' && (
        <Card title="Permitted job discovery" actions={
          <div className="row">
            <Input value={skills} onChange={(e) => setSkills(e.target.value)} placeholder="filter by skills" style={{ minWidth: 180 }} />
            <label className="check">
              <input type="checkbox" checked={remote} onChange={(e) => setRemote(e.target.checked)} />
              remote only
            </label>
            <Btn variant="ghost" busy={jobs.loading} onClick={() => jobs.reload()}>Refresh</Btn>
          </div>
        }>
          <p className="dim">Sources: RemoteOK &amp; Remotive public APIs. Attribution preserved; LinkedIn is never scraped.</p>
          {jobs.error && <ErrorMsg error={jobs.error} onRetry={jobs.reload} />}
          {jobs.loading && !jobs.data && <Spinner />}
          {jobs.data?.stale && <Notice tone="warn">Feeds unreachable — showing cached listings.</Notice>}
          {jobs.data?.sources?.length > 0 && (
            <div className="row">
              {jobs.data.sources.map((s) => (
                <Badge key={s.name} tone={s.ok ? 'ok' : 'err'}>{s.name} {s.ok ? 'ok' : (s.error || 'offline')}</Badge>
              ))}
              {jobs.data.fetched_at && <span className="dim">fetched {jobs.data.fetched_at}</span>}
            </div>
          )}
          {jobs.data?.note && <p className="dim">{jobs.data.note}</p>}
          {jobRows.length === 0 && !jobs.error && <Empty>No matching listings.</Empty>}
          {jobRows.map((j) => (
            <div key={j.id} className="card" style={{ marginBottom: 8 }}>
              <div className="card-body">
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <div>
                    <strong>{j.title}</strong>
                    <div className="dim">{j.company} · {j.location} · <Badge>{j.source}</Badge></div>
                  </div>
                  <div className="row">
                    <a className="btn btn-ghost btn-sm" href={j.url} target="_blank" rel="noreferrer">Open</a>
                    <Btn variant="ghost" busy={busy} onClick={() => post('/api/linkedin/jobs/match', { profile_skills: splitList(p.skills || skills), job_id: j.id })}>Match</Btn>
                  </div>
                </div>
                {j.tags && <p className="dim mono">{j.tags}</p>}
                <p className="dim">source {j.source} · fetched {j.fetched_at}</p>
              </div>
            </div>
          ))}
        </Card>
      )}

      {tab === 'applications' && (
        <>
          <Card title="Track an application">
            <div className="grid grid-3">
              <Field label="Role"><Input value={app.role} onChange={(e) => setApp({ ...app, role: e.target.value })} /></Field>
              <Field label="Company"><Input value={app.company} onChange={(e) => setApp({ ...app, company: e.target.value })} /></Field>
              <Field label="Notes"><Input value={app.notes} onChange={(e) => setApp({ ...app, notes: e.target.value })} /></Field>
            </div>
            <Btn busy={busy} onClick={addApp} disabled={!app.role.trim()}>Add application</Btn>
          </Card>
          <Card title="Applications" actions={<Btn variant="ghost" busy={apps.loading} onClick={apps.reload}>Refresh</Btn>}>
            <p className="dim">
              Submitting is approval-gated and never auto-sends: LinkedIn has no official
              application API for personal accounts, so an approved submission is marked
              <span className="mono"> ready_for_manual_submission</span> for you to send at the listing URL.
            </p>
            {apps.error && <ErrorMsg error={apps.error} onRetry={apps.reload} />}
            {apps.loading && !apps.data && <Spinner />}
            {appRows.length === 0 && !apps.error && <Empty>No applications tracked.</Empty>}
            {appRows.length > 0 && (
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Role</th><th>Company</th><th>Status</th><th /></tr></thead>
                  <tbody>
                    {appRows.map((a) => (
                      <tr key={a.id}>
                        <td>{a.role}</td>
                        <td>{a.company || '—'}</td>
                        <td>
                          <Badge tone={a.status === 'ready_for_manual_submission' ? 'info' : a.status === 'draft' ? 'warn' : 'neutral'}>
                            {a.status}
                          </Badge>
                        </td>
                        <td>
                          <Btn variant="ghost" busy={busy} disabled={a.status === 'ready_for_manual_submission'}
                            onClick={() => post(`/api/linkedin/applications/${a.id}/submit`, {}, null)}>
                            Submit
                          </Btn>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <Card title="Cover letter">
            <Field label="Job description"><TextArea rows={4} value={jobText} onChange={(e) => setJobText(e.target.value)} /></Field>
            <Field label="Company"><Input value={company} onChange={(e) => setCompany(e.target.value)} /></Field>
            <Btn busy={busy} disabled={jobText.trim().length < 10}
              onClick={() => post('/api/linkedin/cover-letter', { profile: profileObj(), job_description: jobText, company: company || null }, 'Cover letter')}>
              Generate cover letter
            </Btn>
          </Card>
        </>
      )}

      {out && (
        <Card title="Latest result">
          <AiMeta data={out} />
          {out.disclaimer && <p className="dim">{out.disclaimer}</p>}
          {out.note && <p className="dim">{out.note}</p>}
          {(typeof out.cv_markdown === 'string' || typeof out.text === 'string') && <DocumentOut data={out} />}
          <MatchOut data={out} />
          {typeof out.cv_markdown !== 'string' && typeof out.text !== 'string' && out.score === undefined && (
            <Result data={out} />
          )}
        </Card>
      )}
    </div>
  )
}
