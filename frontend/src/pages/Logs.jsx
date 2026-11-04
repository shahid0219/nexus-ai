import React, { useState } from 'react'
import { api, qs } from '../api.js'
import { Badge, Btn, Card, Empty, ErrorMsg, Input, Spinner, useLoad } from '../ui.jsx'

const LEVELS = ['', 'info', 'warn', 'error', 'debug']

export default function Logs() {
  const [level, setLevel] = useState('')
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')
  const logs = useLoad(() => api.get(`/api/logs${qs({ limit: 100, level, q: query })}`), [level, query])
  const tasks = useLoad(() => api.get('/api/tasks?limit=50'), [])

  return (
    <div className="stack">
      <div className="page-head">
        <h2>Logs &amp; Tasks</h2>
        <p>Redacted activity stream and task history from the local database.</p>
      </div>

      <Card title="Activity log" actions={<Btn variant="ghost" busy={logs.loading} onClick={logs.reload}>Refresh</Btn>}>
        <div className="row">
          <div className="seg">
            {LEVELS.map((l) => (
              <button key={l || 'all'} className={level === l ? 'on' : ''} onClick={() => setLevel(l)}>{l || 'all'}</button>
            ))}
          </div>
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="search…" onKeyDown={(e) => e.key === 'Enter' && setQuery(q)} />
          <Btn variant="ghost" onClick={() => setQuery(q)}>Search</Btn>
        </div>
        {logs.error && <ErrorMsg error={logs.error} onRetry={logs.reload} />}
        {logs.loading && !logs.data && <Spinner />}
        {logs.data?.length === 0 && <Empty>No log entries match.</Empty>}
        {logs.data?.map((l) => (
          <div key={l.id} className="log-row">
            <Badge tone={l.level === 'error' ? 'err' : l.level === 'warn' ? 'warn' : 'neutral'}>{l.level}</Badge>
            <span className="log-msg">
              <span className="dim">[{l.module}]</span> {l.message}
              {l.detail && <div className="dim mono" style={{ whiteSpace: 'pre-wrap' }}>{l.detail}</div>}
            </span>
            <span className="log-meta">{l.ts}</span>
          </div>
        ))}
      </Card>

      <Card title="Task history" actions={<Btn variant="ghost" busy={tasks.loading} onClick={tasks.reload}>Refresh</Btn>}>
        {tasks.error && <ErrorMsg error={tasks.error} onRetry={tasks.reload} />}
        {tasks.data?.length === 0 && <Empty>No tasks recorded.</Empty>}
        {tasks.data?.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>When</th><th>Module</th><th>Task</th><th>Status</th><th>Duration</th><th>Detail</th></tr></thead>
              <tbody>
                {tasks.data.map((t) => (
                  <tr key={t.id}>
                    <td className="mono">{t.ts}</td>
                    <td>{t.module}</td>
                    <td>{t.name}</td>
                    <td><Badge tone={t.status === 'ok' ? 'ok' : 'err'}>{t.status}</Badge></td>
                    <td className="mono">{t.duration_ms} ms</td>
                    <td className="muted">{t.detail || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
