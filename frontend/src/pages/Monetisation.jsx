import React, { useState } from 'react'
import { api } from '../api.js'
import {
  AiMeta, Badge, Btn, Card, Empty, ErrorMsg, Field, Input, Notice, Result,
  Spinner, Tabs, TextArea, useLoad,
} from '../ui.jsx'

export default function Monetisation() {
  const [tab, setTab] = useState('revenue')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [flash, setFlash] = useState(null)
  const [out, setOut] = useState(null)
  const [prod, setProd] = useState({ name: '', idea: '' })
  const [spon, setSpon] = useState({ brand: '', niche: '', contact: '', url: '' })
  const [rev, setRev] = useState({ amount: '', currency: 'USD', source: '', description: '', payment_reference: '' })

  const revenue = useLoad(() => api.get('/api/monetisation/revenue'), [])
  const products = useLoad(() => api.get('/api/monetisation/products'), [])
  const leads = useLoad(() => api.get('/api/monetisation/leads'), [])
  const affiliates = useLoad(() => api.get('/api/monetisation/affiliates'), [])
  const sponsors = useLoad(() => api.get('/api/monetisation/sponsorships'), [])

  const post = async (path, body, after) => {
    setBusy(true); setErr(null); setFlash(null); setOut(null)
    try {
      const d = await api.post(path, body)
      setOut(d)
      if (d?.code === 'approval_required') setFlash(`Approval requested (#${d.approval_id}). Approve it in Approvals, then retry.`)
      else if (d?.code) setFlash(d.message || d.code)
      else if (after) { setFlash(after); after() }
      return d
    } catch (e) {
      if (e.code === 'approval_required') setFlash(`Approval requested (#${e.approval_id}). Approve it, then retry.`)
      else setErr(e)
    } finally { setBusy(false) }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h2>Monetisation</h2>
        <p>Verified revenue only, permitted leads, honest affiliate directory, approval-gated financial actions.</p>
      </div>

      <Tabs value={tab} onChange={setTab} tabs={[
        { id: 'revenue', label: 'Revenue' },
        { id: 'products', label: 'Products' },
        { id: 'leads', label: 'Leads' },
        { id: 'affiliates', label: 'Affiliates' },
        { id: 'sponsors', label: 'Sponsorships' },
      ]} />

      {flash && <Notice tone="info" onDismiss={() => setFlash(null)}>{flash}</Notice>}
      {err && <ErrorMsg error={err} />}

      {tab === 'revenue' && (
        <>
          <Card title="Totals">
            {revenue.loading && !revenue.data && <Spinner />}
            {revenue.error && <ErrorMsg error={revenue.error} onRetry={revenue.reload} />}
            {revenue.data && (
              <>
                <div className="grid grid-2">
                  <div className="stat"><span className="k">Verified</span><span className="v">{revenue.data.verified_total}</span><span className="s">{revenue.data.verified_count} events with payment reference</span></div>
                  <div className="stat"><span className="k">Unverified</span><span className="v">{revenue.data.unverified_total}</span><span className="s">{revenue.data.unverified_count} events without reference</span></div>
                </div>
                <div className="row mt">
                  <a className="btn btn-ghost" href="/api/monetisation/revenue/export">Export CSV</a>
                </div>
                <div className="table-wrap mt">
                  <table className="table">
                    <thead><tr><th>When</th><th>Amount</th><th>Source</th><th>Reference</th><th>Verified</th></tr></thead>
                    <tbody>
                      {revenue.data.events.map((e) => (
                        <tr key={e.id}>
                          <td className="mono">{e.ts}</td>
                          <td>{e.amount} {e.currency}</td>
                          <td>{e.source}</td>
                          <td className="mono">{e.payment_reference || '—'}</td>
                          <td><Badge tone={e.verified ? 'ok' : 'warn'}>{e.verified ? 'verified' : 'unverified'}</Badge></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </Card>
          <Card title="Record revenue (approval required)">
            <div className="grid grid-3">
              <Field label="Amount"><Input type="number" value={rev.amount} onChange={(e) => setRev({ ...rev, amount: e.target.value })} /></Field>
              <Field label="Currency"><Input value={rev.currency} onChange={(e) => setRev({ ...rev, currency: e.target.value })} /></Field>
              <Field label="Source"><Input value={rev.source} onChange={(e) => setRev({ ...rev, source: e.target.value })} /></Field>
            </div>
            <Field label="Payment reference (required to count as verified)">
              <Input value={rev.payment_reference} onChange={(e) => setRev({ ...rev, payment_reference: e.target.value })} placeholder="e.g. Stripe tx id" />
            </Field>
            <Field label="Description"><Input value={rev.description} onChange={(e) => setRev({ ...rev, description: e.target.value })} /></Field>
            <Btn busy={busy} disabled={!rev.amount || !rev.source} onClick={() => post('/api/monetisation/revenue', {
              amount: Number(rev.amount), currency: rev.currency, source: rev.source,
              description: rev.description || null, payment_reference: rev.payment_reference || null,
            }, 'Revenue recorded.')}>Record</Btn>
          </Card>
        </>
      )}

      {tab === 'products' && (
        <>
          <Card title="Register a digital product">
            <div className="grid grid-2">
              <Field label="Name"><Input value={prod.name} onChange={(e) => setProd({ ...prod, name: e.target.value })} /></Field>
              <Field label="Idea"><Input value={prod.idea} onChange={(e) => setProd({ ...prod, idea: e.target.value })} /></Field>
            </div>
            <Btn busy={busy} disabled={!prod.name.trim()} onClick={() => post('/api/monetisation/products', prod, 'Product registered.').then(() => products.reload())}>Add product</Btn>
          </Card>
          <Card title="Products" actions={<Btn variant="ghost" busy={products.loading} onClick={products.reload}>Refresh</Btn>}>
            {products.error && <ErrorMsg error={products.error} onRetry={products.reload} />}
            {products.data?.length === 0 && <Empty>No products registered.</Empty>}
            {products.data?.length > 0 && (
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Name</th><th>Idea</th><th>Status</th></tr></thead>
                <tbody>{products.data.map((x) => <tr key={x.id}><td>{x.name}</td><td className="muted">{x.idea || '—'}</td><td><Badge>{x.status}</Badge></td></tr>)}</tbody>
              </table></div>
            )}
          </Card>
        </>
      )}

      {tab === 'leads' && (
        <Card title="Freelance leads" actions={<Btn variant="ghost" busy={leads.loading} onClick={leads.reload}>Refresh</Btn>}>
          <p className="dim">{leads.data?.note}</p>
          {leads.error && <ErrorMsg error={leads.error} onRetry={leads.reload} />}
          {leads.data?.leads?.length === 0 && <Empty>No leads yet — run automation `job_discovery`.</Empty>}
          {leads.data?.leads?.map((l, i) => (
            <div key={i} className="log-row">
              <span className="log-msg"><a href={l.url} target="_blank" rel="noreferrer">{l.title}</a> <span className="dim">· {l.client}</span></span>
              <span className="log-meta">{l.source} · {l.fetched_at?.slice(0, 10)}</span>
            </div>
          ))}
        </Card>
      )}

      {tab === 'affiliates' && (
        <Card title="Affiliate research directory">
          {affiliates.error && <ErrorMsg error={affiliates.error} onRetry={affiliates.reload} />}
          {affiliates.data && <Notice tone="warn">{affiliates.data.disclaimer}</Notice>}
          {affiliates.data?.programs?.map((p) => (
            <div key={p.name} className="card mt"><div className="card-body">
              <div className="row"><strong>{p.name}</strong><Badge>{p.category}</Badge><Badge>{p.as_of}</Badge></div>
              <p className="muted">{p.terms}</p>
              <a href={p.source_url} target="_blank" rel="noreferrer" className="dim">{p.source_url}</a>
            </div></div>
          ))}
        </Card>
      )}

      {tab === 'sponsors' && (
        <>
          <Card title="Track a sponsorship opportunity">
            <div className="grid grid-2">
              <Field label="Brand"><Input value={spon.brand} onChange={(e) => setSpon({ ...spon, brand: e.target.value })} /></Field>
              <Field label="Niche"><Input value={spon.niche} onChange={(e) => setSpon({ ...spon, niche: e.target.value })} /></Field>
              <Field label="Contact"><Input value={spon.contact} onChange={(e) => setSpon({ ...spon, contact: e.target.value })} /></Field>
              <Field label="URL"><Input value={spon.url} onChange={(e) => setSpon({ ...spon, url: e.target.value })} /></Field>
            </div>
            <Btn busy={busy} disabled={!spon.brand.trim()} onClick={() => post('/api/monetisation/sponsorships', { ...spon, url: spon.url || null, contact: spon.contact || null, niche: spon.niche || null }, 'Opportunity tracked.').then(() => sponsors.reload())}>Add opportunity</Btn>
          </Card>
          <Card title="Opportunities" actions={<Btn variant="ghost" busy={sponsors.loading} onClick={sponsors.reload}>Refresh</Btn>}>
            {sponsors.error && <ErrorMsg error={sponsors.error} onRetry={sponsors.reload} />}
            {sponsors.data?.length === 0 && <Empty>None tracked yet.</Empty>}
            {sponsors.data?.length > 0 && (
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Brand</th><th>Niche</th><th>Status</th><th /></tr></thead>
                <tbody>{sponsors.data.map((s) => (
                  <tr key={s.id}><td>{s.brand}</td><td>{s.niche || '—'}</td><td><Badge>{s.status}</Badge></td>
                    <td><Btn variant="ghost" busy={busy} onClick={() => post(`/api/monetisation/sponsorships/${s.id}/draft`, {}, 'Draft created (never sent).')}>Draft outreach</Btn></td></tr>
                ))}</tbody>
              </table></div>
            )}
          </Card>
        </>
      )}

      {out && <Card title="Latest result"><AiMeta data={out} /><Result data={out} /></Card>}
    </div>
  )
}
