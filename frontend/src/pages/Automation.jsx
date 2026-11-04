import React, { useState } from 'react'
import { api } from '../api.js'
import { Badge, Btn, Card, Empty, ErrorMsg, Notice, Result, Spinner, useLoad } from '../ui.jsx'

export default function Automation() {
  const jobs = useLoad(() => api.get('/api/automation/jobs'), [])
  const runs = useLoad(() => api.get('/api/automation/runs?limit=25'), [])
  const reports = useLoad(() => api.get('/api/automation/reports'), [])
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState(null)
  const [flash, setFlash] = useState(null)
  const [out, setOut] = useState(null)

  const runNow = async (name) => {
    setBusy(name); setErr(null); setFlash(null); setOut(null)
    try {
      const d = await api.post('/api/automation/run', { job: name })
      setOut(d)
      setFlash(`Job ${name}: ${d.status} (${d.attempts} attempt(s))`)
      runs.reload(); jobs.reload(); reports.reload()
    } catch (e) { setErr(e) } finally { setBusy('') }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h2>Automation</h2>
        <p>Scheduled local jobs with retries. Nothing publishes automatically — every side effect still needs approval.</p>
      </div>

      {flash && <Notice tone="ok" onDismiss={() => setFlash(null)}>{flash}</Notice>}
      {err && <ErrorMsg error={err} />}

      <Card title="Jobs" actions={<Btn variant="ghost" busy={jobs.loading} onClick={jobs.reload}>Refresh</Btn>}>
        {jobs.loading && !jobs.data && <Spinner />}
        {jobs.error && <ErrorMsg error={jobs.error} onRetry={jobs.reload} />}
        {jobs.data?.map((j) => (
          <div key={j.name} className="log-row">
            <div className="log-msg">
              <strong>{j.name}</strong>
              <div className="dim">{j.description}</div>
              <div className="dim">every {j.interval_minutes} min · last: {j.last_run_ts || 'never'}
                {j.last_status && <> · <Badge tone={j.last_status === 'ok' ? 'ok' : 'err'}>{j.last_status}</Badge></>}
              </div>
            </div>
            <Btn variant="ghost" busy={busy === j.name} onClick={() => runNow(j.name)}>Run now</Btn>
          </div>
        ))}
      </Card>

      <div className="grid grid-2">
        <Card title="Recent runs" actions={<Btn variant="ghost" busy={runs.loading} onClick={runs.reload}>Refresh</Btn>}>
          {runs.error && <ErrorMsg error={runs.error} onRetry={runs.reload} />}
          {runs.data?.length === 0 && <Empty>No runs yet.</Empty>}
          {runs.data?.map((r) => (
            <div key={r.id} className="log-row">
              <span className="log-msg"><strong>{r.job}</strong> <Badge tone={r.status === 'ok' ? 'ok' : 'err'}>{r.status}</Badge>{r.attempts > 1 && <Badge tone="warn">{r.attempts} attempts</Badge>}</span>
              <span className="log-meta">{r.ts}</span>
            </div>
          ))}
        </Card>
        <Card title="Reports" actions={<Btn variant="ghost" busy={reports.loading} onClick={reports.reload}>Refresh</Btn>}>
          {reports.error && <ErrorMsg error={reports.error} onRetry={reports.reload} />}
          {reports.data?.reports?.length === 0 && <Empty>No reports yet — run weekly_report.</Empty>}
          {reports.data?.reports?.map((r) => (
            <div key={r.name} className="log-row">
              <span className="log-msg"><strong>{r.name}</strong><div className="dim">{r.kind} · {r.ts}</div></span>
              <Btn variant="ghost" onClick={async () => {
                try { setOut(await api.get(`/api/automation/reports/content?name=${encodeURIComponent(r.name)}`)) }
                catch (e) { setErr(e) }
              }}>Open</Btn>
            </div>
          ))}
        </Card>
      </div>

      {out && <Card title="Output"><Result data={out} /></Card>}
    </div>
  )
}
