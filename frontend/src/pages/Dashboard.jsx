import React from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { Badge, Card, Empty, ErrorMsg, Spinner, useLoad } from '../ui.jsx'

const fmt = (v) => (v === null || v === undefined ? '—' : typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(1)) : String(v))

const bytes = (v) => {
  if (v === null || v === undefined) return '—'
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  if (n < 1024) return `${n} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let x = n / 1024
  let i = 0
  while (x >= 1024 && i < units.length - 1) { x /= 1024; i += 1 }
  return `${x.toFixed(x >= 100 ? 0 : 1)} ${units[i]}`
}

const secs = (v) => {
  const n = Number(v)
  if (!Number.isFinite(n)) return fmt(v)
  if (n < 90) return `${Math.round(n)}s`
  if (n < 5400) return `${Math.round(n / 60)}m`
  if (n < 129600) return `${(n / 3600).toFixed(1)}h`
  return `${(n / 86400).toFixed(1)}d`
}

function Stat({ k, v, s }) {
  return (
    <div className="stat">
      <span className="k">{k}</span>
      <span className="v">{fmt(v)}</span>
      {s && <span className="s">{s}</span>}
    </div>
  )
}

function SysTile({ k, v, tone, s }) {
  return (
    <div className="stat">
      <span className="k">{k}</span>
      <span className="v" style={{ fontSize: 17 }}>
        {typeof v === 'string' || typeof v === 'number' ? fmt(v) : v}
      </span>
      {s && <span className="s">{tone ? <Badge tone={tone}>{s}</Badge> : s}</span>}
    </div>
  )
}

function LogLine({ l }) {
  const tone = l.level === 'error' ? 'err' : l.level === 'warn' ? 'warn' : 'neutral'
  return (
    <div className="log-row">
      <Badge tone={tone}>{l.level}</Badge>
      <span className="log-msg">
        <span className="dim">[{l.module}]</span> {l.message}
      </span>
      <span className="log-meta">{l.ts}</span>
    </div>
  )
}

export default function Dashboard() {
  const stats = useLoad(() => api.get('/api/stats'), [])
  const sys = useLoad(() => api.get('/api/system/status'), [])
  const health = useLoad(() => api.get('/api/health'), [])
  const pending = useLoad(() => api.get('/api/approvals?status=pending&limit=5'), [])
  const logs = useLoad(() => api.get('/api/logs?limit=15'), [])
  const tasks = useLoad(() => api.get('/api/tasks?limit=10'), [])

  const s = stats.data || {}
  const st = sys.data || {}
  const h = health.data || {}
  const tools = st.tools || {}
  const ram = st.ram || {}
  const disk = st.disk || {}
  const oll = h.ollama || {}
  const pendingRows = Array.isArray(pending.data) ? pending.data : (pending.data?.approvals || [])

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
          <Card><Stat k="Revenue verified" v={s.revenue_verified_total} s="payment reference recorded" /></Card>
          <Card><Stat k="Revenue unverified" v={s.revenue_unverified_total} s="no payment reference" /></Card>
          <Card><Stat k="Jobs discovered" v={s.jobs_discovered} /></Card>
          <Card><Stat k="Freelance leads" v={s.freelance_leads} /></Card>
          <Card><Stat k="Calendar planned" v={s.calendar_planned} /></Card>
        </div>
      )}

      <Card
        title="System"
        actions={sys.error ? <ErrorMsg error={sys.error} onRetry={sys.reload} /> : <BtnLike onClick={sys.reload} busy={sys.loading} />}
      >
        {sys.loading && !sys.data && <Spinner />}
        {sys.data && (
          <div className="grid grid-4">
            <SysTile k="CPU" v={`${fmt(st.cpu_percent)}%`} s={`${fmt(st.cpu_cores)} cores`} />
            <SysTile k="RAM" v={`${fmt(ram.used_pct)}%`} s={`${fmt(ram.total_gb)} GB total`} />
            <SysTile k="Disk" v={disk.used_pct == null ? '—' : `${fmt(disk.used_pct)}%`} s={disk.free_gb == null ? 'unavailable' : `${fmt(disk.free_gb)} GB free`} />
            <SysTile k="Python" v={st.python} s="runtime" />
            <SysTile k="Node.js" v={tools.node ? 'found' : 'missing'} tone={tools.node ? 'ok' : 'err'} s={tools.node ? 'on PATH' : 'not on PATH'} />
            <SysTile k="FFmpeg" v={tools.ffmpeg || 'missing'} tone={tools.ffmpeg ? 'ok' : 'err'} s={tools.ffmpeg ? 'available' : 'not found'} />
            <SysTile k="Ollama" v={tools.ollama || (tools.ollama_running ? 'running' : 'offline')} tone={tools.ollama_running ? 'ok' : 'warn'} s={tools.ollama_running ? 'service up' : 'service down'} />
            <SysTile k="Database" v={bytes(st.db_size)} s="sqlite (WAL)" />
            <SysTile k="Uptime" v={secs(st.uptime_s)} s="since backend start" />
            <SysTile k="Port" v={st.port} s="localhost" />
            <SysTile k="Platform" v={st.platform} s="host" />
            <SysTile
              k="Frontend"
              v={st.frontend_built ? 'built' : 'not built'}
              tone={st.frontend_built ? 'ok' : 'warn'}
              s={st.frontend_built ? 'dist/ present' : 'run npm run build'}
            />
          </div>
        )}
      </Card>

      <div className="grid grid-2">
        <Card title="Ollama" actions={health.error ? <ErrorMsg error={health.error} onRetry={health.reload} /> : <BtnLike onClick={health.reload} busy={health.loading} />}>
          {health.loading && !health.data && <Spinner />}
          {!health.data && !health.loading && !health.error && <Empty>No health data.</Empty>}
          {health.data && (
            <div className="stack">
              <div className="row">
                <Badge tone={oll.available ? 'ok' : 'warn'}>{oll.available ? 'available' : 'unavailable'}</Badge>
                <Badge>{h.status || '—'}</Badge>
                <Badge>v{h.version || '—'}</Badge>
                <Badge>uptime {secs(h.uptime_s)}</Badge>
                <Badge tone={h.frontend_built ? 'ok' : 'warn'}>frontend {h.frontend_built ? 'built' : 'not built'}</Badge>
              </div>
              <div>
                <h3>Models</h3>
                {(oll.models || []).length === 0 && <Empty>No models reported — run <span className="mono">ollama pull</span> to add one.</Empty>}
                <div className="row mt">
                  {(oll.models || []).map((m) => <Badge key={m} tone="accent">{m}</Badge>)}
                </div>
              </div>
              <p className="dim">Database: <span className="mono">{h.db?.path || '—'}</span> ({bytes(h.db?.size)})</p>
            </div>
          )}
        </Card>

        <Card title="Pending approvals" actions={<Link className="btn btn-ghost btn-sm" to="/approvals">Open Approvals →</Link>}>
          {pending.loading && !pending.data && <Spinner />}
          {pending.error && <ErrorMsg error={pending.error} onRetry={pending.reload} />}
          {pending.data && pendingRows.length === 0 && <Empty>Nothing waiting for approval.</Empty>}
          {pendingRows.map((a) => (
            <div key={a.id} className="log-row">
              <Badge tone="warn">{a.status}</Badge>
              <span className="log-msg">
                <span className="dim">[{a.kind}]</span> {a.title}
              </span>
              <span className="log-meta">#{a.id} · {a.ts}</span>
            </div>
          ))}
        </Card>
      </div>

      <div className="grid grid-2">
        <Card title="Recent activity" actions={<Link className="btn btn-ghost btn-sm" to="/logs">All logs →</Link>}>
          {logs.loading && !logs.data && <Spinner />}
          {logs.error && <ErrorMsg error={logs.error} onRetry={logs.reload} />}
          {Array.isArray(logs.data) && logs.data.length === 0 && <Empty>No log entries yet.</Empty>}
          {Array.isArray(logs.data) && logs.data.map((l) => <LogLine key={l.id} l={l} />)}
        </Card>

        <Card title="Recent tasks" actions={<Link className="btn btn-ghost btn-sm" to="/logs">Task history →</Link>}>
          {tasks.loading && !tasks.data && <Spinner />}
          {tasks.error && <ErrorMsg error={tasks.error} onRetry={tasks.reload} />}
          {Array.isArray(tasks.data) && tasks.data.length === 0 && <Empty>No tasks recorded yet.</Empty>}
          {Array.isArray(tasks.data) && tasks.data.map((t) => (
            <div key={t.id} className="log-row">
              <Badge tone={t.status === 'ok' ? 'ok' : 'err'}>{t.status}</Badge>
              <span className="log-msg">
                <span className="dim">[{t.module}]</span> {t.name}
                {t.detail ? <span className="dim"> — {t.detail}</span> : null}
              </span>
              <span className="log-meta">{t.duration_ms ?? '—'} ms</span>
            </div>
          ))}
        </Card>
      </div>
    </div>
  )
}

function BtnLike({ onClick, busy }) {
  return (
    <button className="btn btn-ghost btn-sm" onClick={onClick} disabled={busy} aria-busy={!!busy}>
      {busy && <span className="spinner spinner-sm" />} Refresh
    </button>
  )
}
