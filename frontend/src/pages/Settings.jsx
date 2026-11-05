import React, { useEffect, useState } from 'react'
import {
  api } from '../api.js'
import {
  Badge, Btn, Card, Empty, ErrorMsg, Field, Input, Notice, Spinner, TextArea, useLoad,
} from '../ui.jsx'

const KIND_TONE = { remote: 'info', local: 'ok', deterministic: 'neutral' }

function ProviderRow({ p, onMove, onSaveKey, onClearKey, onPickModel, busy }) {
  const [key, setKey] = useState('')
  const [model, setModel] = useState(p.selected_model || '')
  useEffect(() => { setModel(p.selected_model || '') }, [p.selected_model])

  return (
    <div className="card" style={{ marginBottom: 10 }}>
      <div className="card-body">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div className="row">
            <strong>{p.label}</strong>
            <Badge tone={KIND_TONE[p.kind]}>{p.kind}</Badge>
            {p.name === p.active && <Badge tone="ok">active</Badge>}
            {p.configured ? <Badge tone="ok">configured</Badge> : <Badge tone="warn">not configured</Badge>}
            {p.cooling_down && <Badge tone="err">cooling {p.cooldown_remaining_s}s</Badge>}
          </div>
          <div className="row">
            <Btn variant="ghost" onClick={() => onMove(p.name, -1)} disabled={busy}>↑</Btn>
            <Btn variant="ghost" onClick={() => onMove(p.name, 1)} disabled={busy}>↓</Btn>
          </div>
        </div>

        <p className="dim mt">{p.free_note}</p>
        {p.doc && <p className="dim">{p.doc}</p>}

        {p.last_error && (
          <p className="dim mono">
            last error ({p.last_error_class || 'error'}): {p.last_error}
          </p>
        )}
        {p.last_ok_ts && <p className="dim">last success: {p.last_ok_ts}</p>}
        {p.last_latency_ms != null && <p className="dim">latency: {p.last_latency_ms} ms</p>}

        {p.kind === 'local' && (
          <div className="stack mt">
            {p.models && p.models.length > 0 ? (
              <p className="dim">installed: {p.models.join(', ')}</p>
            ) : (
              <p className="dim">No model selected. Start Ollama and pull a small model.</p>
            )}
            <Field label="Model override (optional)">
              <Input value={model} placeholder={p.selected_model || 'e.g. qwen2.5:3b'}
                     onChange={(e) => setModel(e.target.value)} />
            </Field>
            <div className="row">
              <Btn variant="ghost" onClick={() => onPickModel(p.name, model)} busy={busy}>
                Save model
              </Btn>
            </div>
          </div>
        )}

        {p.kind === 'remote' && (
          <div className="stack mt">
            {p.configured ? (
              <div className="row">
                <span className="dim">An API key is stored locally. It is never displayed.</span>
                <Btn variant="danger" onClick={() => onClearKey(p.name)} busy={busy}>
                  Remove key
                </Btn>
              </div>
            ) : (
              <>
                <Field label="API key" hint="Stored in data/credentials.json (gitignored). Never returned by the API.">
                  <Input type="password" autoComplete="off" value={key}
                         onChange={(e) => setKey(e.target.value)} />
                </Field>
                <div className="row">
                  <Btn onClick={() => { onSaveKey(p.name, key); setKey('') }}
                       disabled={key.trim().length < 8} busy={busy}>
                    Save key
                  </Btn>
                </div>
              </>
            )}
          </div>
        )}

        {p.kind === 'deterministic' && (
          <p className="dim mt">
            Always available. Used only when no model is usable, and every result is
            labelled <span className="mono">generated_by: fallback</span>.
          </p>
        )}
      </div>
    </div>
  )
}

export default function Settings() {
  const status = useLoad(() => api.get('/api/ai/status'), [])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [flash, setFlash] = useState(null)
  const [test, setTest] = useState(null)
  const [testing, setTesting] = useState(false)
  const [prompt, setPrompt] = useState('Write one sentence about local-first AI.')
  const [out, setOut] = useState(null)
  const [running, setRunning] = useState(false)

  const order = status.data?.order || []
  const byName = Object.fromEntries((status.data?.providers || []).map((p) => [p.name, p]))

  const run = async (fn, msg) => {
    setBusy(true); setErr(null); setFlash(null)
    try {
      const d = await fn()
      if (msg) setFlash(msg(d))
      status.reload()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const move = (name, dir) => {
    const idx = order.indexOf(name)
    const target = idx + dir
    if (idx < 0 || target < 0 || target >= order.length) return
    if (order[target] === 'fallback') return
    const next = [...order]
    ;[next[idx], next[target]] = [next[target], next[idx]]
    run(() => api.post('/api/ai/order', { order: next }), () => 'Provider order saved.')
  }

  const saveKey = (provider, apiKey) =>
    run(() => api.post('/api/ai/provider/credentials', { provider, api_key: apiKey }),
        (d) => `${provider}: ${d.note}`)

  const clearKey = (provider) =>
    run(() => api.del(`/api/ai/provider/${provider}/credentials`),
        (d) => d.code === 'approval_required'
          ? `Deleting requires approval (#${d.approval_id}) — approve in Approvals, then retry.`
          : `${provider} key removed.`)

  const pickModel = (provider, model) =>
    run(() => api.post('/api/ai/model', { provider, model }), () => 'Model override saved.')

  const testAll = async () => {
    setTesting(true); setErr(null)
    try { setTest(await api.post('/api/ai/test', {})); status.reload() }
    catch (e) { setErr(e) } finally { setTesting(false) }
  }

  const generate = async () => {
    setRunning(true); setErr(null); setOut(null)
    try {
      setOut(await api.post('/api/ai/generate',
        { prompt, module: 'settings.test', max_tokens: 256 }))
    } catch (e) { setErr(e) } finally { setRunning(false) }
  }

  const active = status.data?.active
  const activeLabel = status.data?.active_label

  return (
    <div className="stack">
      <div className="page-head">
        <h2>AI Settings</h2>
        <p>
          One router serves every AI feature. Remote providers are tried in the order
          below; Ollama runs locally; deterministic templates are the honest last resort.
        </p>
      </div>

      {flash && <Notice tone="ok" onDismiss={() => setFlash(null)}>{flash}</Notice>}
      {err && <ErrorMsg error={err} />}
      {status.error && <ErrorMsg error={status.error} onRetry={status.reload} />}
      {status.loading && !status.data && <Spinner label="Loading providers…" />}

      {status.data && (
        <>
          <Card title="Current provider"
                actions={<Btn variant="ghost" onClick={testAll} busy={testing}>Test all providers</Btn>}>
            <div className="row">
              <Badge tone={active ? 'ok' : 'warn'}>{activeLabel}</Badge>
              {active && byName[active]?.selected_model && (
                <Badge>{byName[active].selected_model}</Badge>
              )}
              {!active && <span className="dim">No model available — templates in use.</span>}
            </div>
            <p className="dim mt">
              Order: {order.join(' → ')}
            </p>
            {status.data.hint && (
              <Notice tone="warn" title="Local AI needs attention">
                {status.data.hint}
              </Notice>
            )}
            {status.data.ollama && (
              <p className="dim">
                Ollama at <code>{status.data.ollama.url}</code>:{' '}
                {status.data.ollama.available
                  ? `${status.data.ollama.models.length} model(s) installed`
                  : 'not reachable'}
                {status.data.ollama.models.length > 0 && (
                  <> — {status.data.ollama.models.join(', ')}</>
                )}
              </p>
            )}
            <p className="dim">
              DeepSeek does not offer a free API. Its website chat is not an API, so
              NEXUS never scrapes it. A DeepSeek key is used only if you store one here.
            </p>
          </Card>

          {test && (
            <Card title="Connectivity test">
              <div className="stack">
                {test.results.map((r) => (
                  <div key={r.provider} className="row">
                    <Badge tone={r.ok ? 'ok' : 'warn'}>{r.provider}</Badge>
                    <span className="dim">{r.detail}</span>
                    {r.latency_ms != null && <span className="dim">{r.latency_ms} ms</span>}
                  </div>
                ))}
              </div>
              <p className="dim mt">
                Remotes are probed with a model-listing call, which does not consume
                generation quota.
              </p>
            </Card>
          )}

          <Card title="Providers">
            <p className="dim mb">Use ↑ / ↓ to change priority. Templates always stay last.</p>
            {(status.data.providers || []).map((p) => (
              <ProviderRow key={p.name} p={p} onMove={move} onSaveKey={saveKey}
                           onClearKey={clearKey} onPickModel={pickModel} busy={busy} />
            ))}
          </Card>

          <Card title="Try the active provider">
            <Field label="Prompt">
              <TextArea rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
            </Field>
            <div className="row mt">
              <Btn onClick={generate} busy={running} disabled={!prompt.trim()}>Generate</Btn>
            </div>
            {out && (
              <div className="mt">
                <div className="row">
                  <Badge tone={out.fallback ? 'warn' : 'ok'}>
                    {out.provider_label || out.generated_by}
                  </Badge>
                  {out.model && <Badge>{out.model}</Badge>}
                  <Badge>{out.latency_ms} ms</Badge>
                  {out.fallback && <Badge tone="warn">fallback</Badge>}
                </div>
                {out.attempts?.length > 0 && (
                  <details className="mt">
                    <summary className="dim">Provider attempts ({out.attempts.length})</summary>
                    <pre className="result">{JSON.stringify(out.attempts, null, 2)}</pre>
                  </details>
                )}
                <pre className="result mt">{out.text}</pre>
              </div>
            )}
          </Card>
        </>
      )}

      {status.data && (status.data.providers || []).length === 0 && (
        <Empty>No providers reported by the backend.</Empty>
      )}
    </div>
  )
}
