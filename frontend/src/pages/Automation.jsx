import React, { useState } from 'react'
import { api } from '../api.js'
import { Badge, Btn, Card, Empty, ErrorMsg, Notice, Result, Spinner, useLoad } from '../ui.jsx'

export default function Automation() {
  const jobs = useLoad(() => api.get('/api/automation/jobs'), [])
  const runs = useLoad(() => api.get('/api/automation/runs?limit=30'), [])
  const reports = useLoad(() => api.get('/api/automation/reports'), [])
  const sched = useLoad(() => api.get('/api/automation/status'), [])
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState(null)
  const [flash, setFlash] = useState(null)
  const [out, setOut] = useState(null)

  const runNow = async (name) => {
    setBusy(name); setErr(null); setFlash(null); setOut(null)
    try {
      const d = await api.post('/api/automation/run', { job: name })
      setOut(d)
      setFlash(`Job ${name}: ${d.status || 'done'}${d.attempts ? ` (${d.attempts} attempt(s))` : ''}`)
      runs.reload(); jobs.reload(); reports.reload()
    } catch (e) { setErr(e) } finally { setBusy('') }
  }

  const jobRows = Array.isArray(jobs.data) ? jobs.data : (jobs.data?.jobs || [])
  const runRows = Array.isArray(runs.data) ? runs.data : (runs.data?.runs || [])
  const reportRows = reports.data?.reports || (Array.isArray(reports.data) ? reports.data : [])
  const st = sched.data || {}

  return (
    <div className="stack">
      <div className="page-head">
        <h2>Automation</h2>
        <p>Scheduled local jobs with retries. Nothing publishes automatically — every side effect still needs approval.</p>
      </div>

      {flash && <Notice tone="ok" onDismiss={() => setFlash(null)}>{flash}</Notice>}
      {err && <ErrorMsg error={err} />}

      <Card title="Scheduler" actions={<Btn variant="ghost" busy={sched.loading} onClick={sched.reload}>Refresh</Btn>}>
        {sched.loading && !sched.data && <Spinner />}
        {sched.error && (
          <p className="dim">
            Scheduler status unavailable: {sched.error.message}
            {sched.error.status === 404 ? ' (endpoint not present in this backend build)' : ''}
          </p>
        )}
        {sched.data && (
          <div className="row">
            <Badge tone={st.running ? 'ok' : 'warn'}>{st.running ? 'running' : 'stopped'}</Badge>
            <Badge>tick {st.tick ?? '—'}</Badge>
            <Badge>checks every {st.interval_s ?? '—'}s</Badge>
            <Badge tone="info">{st.jobs_enabled ?? jobRows.filter((j) => j.enabled).length} jobs enabled</Badge>
          </div>
        )}
      </Card>

      <Card title="Jobs" actions={<Btn variant="ghost" busy={jobs.loading} onClick={jobs.reload}>Refresh</Btn>}>
        {jobs.loading && !jobs.data && <Spinner />}
        {jobs.error && <ErrorMsg error={jobs.error} onRetry={jobs.reload} />}
        {jobRows.length === 0 && !jobs.error && <Empty>No jobs registered.</Empty>}
        {jobRows.map((j) => (
          <div key={j.name} className="log-row">
            <div className="log-msg">
              <div className="row">
                <strong>{j.name}</strong>
                <Badge tone={j.enabled ? 'ok' : 'neutral'}>{j.enabled ? 'enabled' : 'disabled'}</Badge>
              </div>
              <div className="dim">{j.description}</div>
              <div className="dim">
                {j.interval_minutes ? `every ${j.interval_minutes} min` : ''}
                {j.daily_time ? `${j.interval_minutes ? ' · ' : ''}daily at ${j.daily_time}` : ''}
                {' · last: '}{j.last_run_ts || 'never'}
                {j.last_status && <> · <Badge tone={j.last_status === 'ok' ? 'ok' : 'err'}>{j.last_status}</Badge></>}
              </div>
            </div>
            <Btn variant="ghost" busy={busy === j.name} onClick={() => runNow(j.name)}>Run now</Btn>
          </div>
        ))}
      </Card>

      <div className="grid grid-2">
        <Card title="Recent runs (last 30)" actions={<Btn variant="ghost" busy={runs.loading} onClick={runs.reload}>Refresh</Btn>}>
          {runs.error && <ErrorMsg error={runs.error} onRetry={runs.reload} />}
          {runs.loading && !runs.data && <Spinner />}
          {runRows.length === 0 && !runs.error && <Empty>No runs yet.</Empty>}
          {runRows.map((r) => {
            let detail = r.detail
            if (typeof detail === 'string') { try { detail = JSON.parse(detail) } catch { detail = null } }
            return (
              <div key={r.id} className="log-row">
                <span className="log-msg">
                  <div className="row">
                    <strong>{r.job}</strong>
                    <Badge tone={r.status === 'ok' ? 'ok' : 'err'}>{r.status}</Badge>
                    {r.attempts > 1 && <Badge tone="warn">{r.attempts} attempts</Badge>}
                    {detail?.trigger && <Badge>{detail.trigger}</Badge>}
                    {detail?.duration_ms != null && <span className="dim">{detail.duration_ms} ms</span>}
                  </div>
                  {detail?.error && <div className="dim mono">{detail.error}</div>}
                </span>
                <span className="log-meta">{r.ts}</span>
              </div>
            )
          })}
        </Card>

        <Card title="Reports" actions={<Btn variant="ghost" busy={reports.loading} onClick={reports.reload}>Refresh</Btn>}>
          {reports.error && <ErrorMsg error={reports.error} onRetry={reports.reload} />}
          {reports.loading && !reports.data && <Spinner />}
          {reportRows.length === 0 && !reports.error && <Empty>No reports yet — run weekly_report.</Empty>}
          {reportRows.map((r) => (
            <div key={`${r.id ?? 'f'}-${r.name}`} className="log-row">
              <span className="log-msg">
                <strong>{r.name}</strong>
                <div className="dim">{r.kind} · {r.ts}</div>
                {r.summary && <div className="dim mono">{typeof r.summary === 'string' ? r.summary : JSON.stringify(r.summary)}</div>}
              </span>
              <Btn variant="ghost" onClick={async () => {
                setErr(null)
                try { setOut(await api.get(`/api/automation/reports/content?name=${encodeURIComponent(r.name)}`)) }
                catch (e) { setErr(e) }
              }}>Open</Btn>
            </div>
          ))}
        </Card>
      </div>

      {out && (
        <Card title={out.name ? `Report: ${out.name}` : 'Output'}>
          {typeof out.content === 'string'
            ? <pre className="result">{out.content}</pre>
            : <Result data={out} />}
        </Card>
      )}
    </div>
  )
}
