import React, { useState } from 'react'
import { api } from '../api.js'
import { Badge, Btn, Card, Empty, ErrorMsg, Field, Notice, Spinner, TextArea, useLoad } from '../ui.jsx'

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
  const [status, setStatus] = useState('')
  const list = useLoad(() => api.get(`/api/approvals?status=${encodeURIComponent(status)}`), [status])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [flash, setFlash] = useState(null)

  const act = async (a, kind, reason) => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/api/approvals/${a.id}/${kind}`, reason ? { reason } : {})
      setFlash(`#${a.id} ${kind}d.`)
      list.reload()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h2>Approvals</h2>
        <p>Human-in-the-loop gates raised by backend actions.</p>
      </div>

      <div className="pillbar">
        <div className="seg">
          {['', 'pending', 'approved', 'rejected'].map((s) => (
            <button key={s || 'all'} className={status === s ? 'on' : ''} onClick={() => setStatus(s)}>
              {s || 'all'}
            </button>
          ))}
        </div>
        <Btn variant="ghost" onClick={list.reload} busy={list.loading}>Refresh</Btn>
      </div>

      {flash && <Notice tone="ok" onDismiss={() => setFlash(null)}>{flash}</Notice>}
      {err && <ErrorMsg error={err} />}
      {list.error && <ErrorMsg error={list.error} onRetry={list.reload} />}
      {list.loading && !list.data && <Spinner label="Loading approvals…" />}
      {list.data && list.data.length === 0 && !list.error && <Empty>No approvals match this filter.</Empty>}
      {list.data && list.data.map((a) => <Row key={a.id} a={a} busy={busy} onAct={act} />)}
    </div>
  )
}
