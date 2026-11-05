import React, { useState } from 'react'
import {
  api } from '../api.js'
import { Badge, Btn, Empty, ErrorMsg, Field, Notice, TextArea, useLoad,
} from '../ui.jsx'

const TONE = { pending: 'warn', approved: 'ok', rejected: 'err', auto: 'info' }

function pretty(p) {
  if (p == null) return null
  if (typeof p === 'string') {
    try { return JSON.stringify(JSON.parse(p), null, 2) } catch { return p }
  }
  return JSON.stringify(p, null, 2)
}

function Row({ a, onAct, busy }) {
  const [reason, setReason] = useState('')
  const [open, setOpen] = useState(false)
  const act = (kind) => { onAct(a, kind, reason); setOpen(false) }
  return (
    <div className="card" style={{ marginBottom: 10 }}>
      <div className="card-body">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div className="row">
            <Badge tone={TONE[a.status] || 'neutral'}>{a.status}</Badge>
            <Badge tone="info">{a.kind}</Badge>
            <strong>{a.title}</strong>
          </div>
          <span className="log-meta">#{a.id} · {a.ts}</span>
        </div>
        {a.payload != null && <pre className="result mt">{pretty(a.payload)}</pre>}
        {a.status !== 'pending' && (
          <p className="dim mt">
            decided {a.decided_ts || '—'} by {a.decided_by || '—'}
            {a.reason ? <> · reason: {a.reason}</> : null}
            {a.used_ts ? <> · executed {a.used_ts}</> : <> · not executed</>}
          </p>
        )}
        {a.status === 'pending' && (
          <div className="mt">
            {open ? (
              <div className="stack">
                <Field label="Reason (optional)">
                  <TextArea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why?" />
                </Field>
                <div className="row">
                  <Btn busy={busy} onClick={() => act('approve')}>Approve</Btn>
                  <Btn variant="danger" busy={busy} onClick={() => act('reject')}>Reject</Btn>
                  <Btn variant="ghost" onClick={() => setOpen(false)}>Cancel</Btn>
                </div>
              </div>
            ) : (
              <div className="row">
                <Btn variant="ghost" onClick={() => setOpen(true)}>Decide…</Btn>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default function Approvals() {
  const [status, setStatus] = useState('pending')
  const list = useLoad(() => api.get(`/api/approvals?status=${encodeURIComponent(status)}`), [status])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [flash, setFlash] = useState(null)

  const act = async (a, kind, reason) => {
    setBusy(true); setErr(null)
    try {
      const d = await api.post(`/api/approvals/${a.id}/${kind}`, reason ? { reason } : {})
      setFlash(d?.hint ? `#${a.id} approved — ${d.hint}.` : `#${a.id} ${kind === 'approve' ? 'approved' : 'rejected'}.`)
      list.reload()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h2>Approvals</h2>
        <p>Human-in-the-loop gates raised by backend actions.</p>
      </div>

      <div className="notice n-info">
        <div className="notice-body">
          <strong>How the approval gate works</strong>
          <span>
            Side-effecting actions (publishing, uploading, job applications, deleting data,
            recording revenue, disconnecting accounts) never run on their own. When you trigger
            one, the backend creates a <em>pending</em> approval with the exact payload and
            returns <span className="mono">409 approval_required</span> — nothing happens yet.
            Review the payload below, then <b>Approve</b> (records your decision + timestamp) or
            <b> Reject</b> with a reason. Approvals are <b>single-use</b>: retry the original
            request afterwards and it executes exactly once against the approved payload.
          </span>
        </div>
      </div>

      <div className="pillbar">
        <div className="seg">
          {['pending', 'approved', 'rejected'].map((s) => (
            <button key={s} className={status === s ? 'on' : ''} onClick={() => setStatus(s)}>
              {s}
            </button>
          ))}
        </div>
        <Btn variant="ghost" onClick={list.reload} busy={list.loading}>Refresh</Btn>
      </div>

      {flash && <Notice tone="ok" onDismiss={() => setFlash(null)}>{flash}</Notice>}
      {err && <ErrorMsg error={err} />}
      {list.error && <ErrorMsg error={list.error} onRetry={list.reload} />}
      {list.loading && !list.data && <Spinner label="Loading approvals…" />}
      {list.data && (Array.isArray(list.data) ? list.data : list.data.approvals || []).length === 0 && !list.error && (
        <Empty>No {status} approvals.</Empty>
      )}
      {(Array.isArray(list.data) ? list.data : list.data?.approvals || []).map((a) => (
        <Row key={a.id} a={a} busy={busy} onAct={act} />
      ))}
    </div>
  )
}
