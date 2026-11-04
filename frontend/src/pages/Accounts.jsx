import React, { useState } from 'react'
import { api } from '../api.js'
import { Badge, Btn, Card, ErrorMsg, Field, Input, Notice, Spinner, useLoad } from '../ui.jsx'

const TONE = { connected: 'ok', awaiting_authentication: 'warn', awaiting_configuration: 'warn', not_applicable: 'neutral' }
const FORMS = {
  meta: [
    { key: 'access_token', label: 'Instagram Graph API access token', type: 'password' },
    { key: 'ig_user_id', label: 'Instagram business account id', type: 'text' },
  ],
  google: [
    { key: 'client_id', label: 'OAuth client id', type: 'text' },
    { key: 'client_secret', label: 'OAuth client secret', type: 'password' },
  ],
}

export default function Accounts() {
  const list = useLoad(() => api.get('/api/accounts'), [])
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState(null)
  const [flash, setFlash] = useState(null)
  const [form, setForm] = useState({})
  const [open, setOpen] = useState('')

  const configure = async (provider) => {
    setBusy(provider); setErr(null); setFlash(null)
    try {
      const secrets = {}
      const cfg = {}
      ;(FORMS[provider] || []).forEach((f) => {
        if (f.key === 'ig_user_id') cfg.ig_user_id = form[f.key]
        else secrets[f.key] = form[f.key]
      })
      const d = await api.post(`/api/accounts/${provider}/configure`, { secrets, config: cfg })
      setFlash(d?.note || `${provider}: credentials stored locally (never displayed).`)
      setForm({}); setOpen(''); list.reload()
    } catch (e) { setErr(e) } finally { setBusy('') }
  }

  const disconnect = async (provider) => {
    setBusy(provider); setErr(null); setFlash(null)
    try {
      const d = await api.del(`/api/accounts/${provider}`)
      if (d?.code === 'approval_required') setFlash(`Deleting credentials requires owner approval (#${d.approval_id}) — approve it in Approvals, then retry.`)
      else if (d?.code === 'not_connected') setFlash(`${provider}: no stored credentials to remove.`)
      else { setFlash(`${provider} disconnected.`); list.reload() }
    } catch (e) {
      if (e.code === 'approval_required') setFlash(`Deleting credentials requires owner approval (#${e.approval_id}) — approve it in Approvals, then retry.`)
      else setErr(e)
    } finally { setBusy('') }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h2>Account Centre</h2>
        <p>Credentials stay local in <span className="mono">data/credentials.json</span> (gitignored) and are never returned by the API.</p>
      </div>

      {flash && <Notice tone="info" onDismiss={() => setFlash(null)}>{flash}</Notice>}
      {err && <ErrorMsg error={err} />}
      {list.loading && !list.data && <Spinner />}
      {list.error && <ErrorMsg error={list.error} onRetry={list.reload} />}

      {list.data?.providers?.map((p) => (
        <Card key={p.provider} title={p.label} actions={<Badge tone={TONE[p.status] || 'neutral'}>{p.status}</Badge>}>
          <p className="muted">{p.note}</p>

          {p.scopes && <p className="dim mono">scopes: {p.scopes}</p>}
          {p.updated_at && <p className="dim">updated {p.updated_at}</p>}

          {FORMS[p.provider] && (
            <>
              {open === p.provider ? (
                <div className="stack">
                  {FORMS[p.provider].map((f) => (
                    <Field key={f.key} label={f.label}>
                      <Input
                        type={f.type}
                        autoComplete="off"
                        value={form[f.key] || ''}
                        onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                      />
                    </Field>
                  ))}
                  <div className="row">
                    <Btn busy={busy === p.provider} onClick={() => configure(p.provider)}>Save locally</Btn>
                    <Btn variant="ghost" onClick={() => setOpen('')}>Cancel</Btn>
                  </div>
                </div>
              ) : (
                <div className="row">
                  <Btn variant="ghost" onClick={() => setOpen(p.provider)}>{p.present ? 'Replace credentials' : 'Configure'}</Btn>
                  {p.present && <Btn variant="danger" busy={busy === p.provider} onClick={() => disconnect(p.provider)}>Disconnect</Btn>}
                </div>
              )}
            </>
          )}

          {p.provider === 'github' && p.account && (
            <p className="dim">Authenticated via system <span className="mono">gh</span> as <strong>{p.account}</strong> — token never read by NEXUS.</p>
          )}
          {p.provider === 'linkedin' && (
            <p className="dim">Permitted features only: job discovery via public feeds and truthful document generation.</p>
          )}
        </Card>
      ))}
    </div>
  )
}
