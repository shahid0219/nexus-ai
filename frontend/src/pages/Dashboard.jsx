import React from 'react'
import { api } from '../api.js'
import { Badge, Card, Empty, ErrorMsg, Spinner, useLoad } from '../ui.jsx'

const fmt = (v) => (v === null || v === undefined ? '—' : typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(1)) : String(v))

function Stat({ k, v, s }) {
  return (
    <div className="stat">
      <span className="k">{k}</span>
      <span className="v">{fmt(v)}</span>
      {s && <span className="s">{s}</span>}
    </div>
  )
}

export default function Dashboard() {
  const stats = useLoad(() => api.get('/api/stats'), [])
  const sys = useLoad(() => api.get('/api/system/status'), [])
  const health = useLoad(() => api.get('/api/health'), [])

  const s = stats.data || {}
  const st = sys.data || {}
  const h = health.data || {}
  const tools = st.tools || {}
  const ram = st.ram || {}
  const disk = st.disk || {}
  const oll = h.ollama || {}

  return (
    <div className="stack">
      <div className="page-head">
        <h2>Command Centre</h2>
        <p>Live overview of the NEXUS AI backend.</p>
      </div>

      {stats.error && <ErrorMsg error={stats.error} onRetry={stats.reload} />}
      {stats.loading && !stats.data && <Spinner label="Loading stats…" />}

      {!stats.error && stats.data && (
        <div className="grid grid-4">
          <Card><Stat k="Pending approvals" v={s.approvals_pending} /></Card>
          <Card><Stat k="Tasks today" v={s.tasks_today} /></Card>
          <Card><Stat k="AI calls today" v={s.ai_calls_today} /></Card>
          <Card><Stat k="Automation runs" v={s.automation_runs_today} /></Card>
          <Card><Stat k="Revenue verified" v={s.revenue_verified_total} s="currency units" /></Card>
          <Card><Stat k="Revenue unverified" v={s.revenue_unverified_total} s="currency units" /></Card>
          <Card><Stat k="Jobs discovered" v={s.jobs_discovered} /></Card>
          <Card><Stat k="Freelance leads" v={s.freelance_leads} /></Card>
          <Card><Stat k="Calendar planned" v={s.calendar_planned} /></Card>
        </div>
      )}

      <div className="grid grid-2">
        <Card title="System" actions={sys.error ? <ErrorMsg error={sys.error} onRetry={sys.reload} /> : null}>
          {sys.loading && !sys.data && <Spinner />}
          {sys.data && (
            <dl className="kv">
              <dt>Platform</dt><dd>{st.platform || '—'}</dd>
              <dt>Python</dt><dd>{fmt(st.python)}</dd>
              <dt>CPU</dt><dd>{fmt(st.cpu_percent)}%</dd>
              <dt>RAM</dt><dd>{fmt(ram.total_gb)} GB total · {fmt(ram.used_pct)}% used</dd>
              <dt>Disk</dt><dd>{fmt(disk.used_pct)}% used · {fmt(disk.free_gb)} GB free</dd>
              <dt>DB size</dt><dd>{fmt(st.db_size)}</dd>
              <dt>Uptime</dt><dd>{fmt(st.uptime_s)}s</dd>
              <dt>Frontend</dt><dd>{st.frontend_built ? <Badge tone="ok">built</Badge> : <Badge tone="warn">not built</Badge>}</dd>
              <dt>Tools</dt><dd className="row">
                {Object.entries(tools)
                  .filter(([k]) => k !== 'ollama_running')
                  .map(([k, v]) => (
                    <Badge key={k} tone={v ? 'ok' : 'err'}>
                      {k}{typeof v === 'string' && v !== '' ? ` ${v}` : v ? '' : ' ✗'}
                    </Badge>
                  ))}
              </dd>
            </dl>
          )}
        </Card>

        <Card title="Ollama" actions={health.error ? <ErrorMsg error={health.error} onRetry={health.reload} /> : null}>
          {health.loading && !health.data && <Spinner />}
          {!health.data && !health.loading && !health.error && <Empty>No health data.</Empty>}
          {health.data && (
            <div className="stack">
              <div className="row">
                <Badge tone={oll.available ? 'ok' : 'warn'}>{oll.available ? 'available' : 'unavailable'}</Badge>
                <Badge>{h.status || '—'}</Badge>
                <Badge>v{h.version || '—'}</Badge>
                <Badge>uptime {fmt(h.uptime_s)}s</Badge>
                <Badge tone={h.frontend_built ? 'ok' : 'warn'}>frontend {h.frontend_built ? 'built' : 'not built'}</Badge>
              </div>
              <div>
                <h3>Models</h3>
                {(oll.models || []).length === 0 && <Empty>No models reported.</Empty>}
                <div className="row mt">
                  {(oll.models || []).map((m) => <Badge key={m} tone="accent">{m}</Badge>)}
                </div>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
