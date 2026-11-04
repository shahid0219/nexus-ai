import React, { useCallback, useEffect, useState } from 'react'
import { ApiError, errText } from './api.js'

export function useLoad(fn, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const run = useCallback(() => {
    let alive = true
    setLoading(true)
    fn()
      .then((d) => { if (alive) { setData(d); setError(null) } })
      .catch((e) => { if (alive) setError(e) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => run(), [run])
  return { data, error, loading, reload: run }
}

export function Badge({ children, tone }) {
  if (!children && children !== 0) return null
  const t = tone || 'neutral'
  return <span className={`badge b-${t}`}>{children}</span>
}

export function Card({ title, actions, children, className }) {
  return (
    <section className={`card ${className || ''}`}>
      {(title || actions) && (
        <header className="card-head">
          {title && <h3>{title}</h3>}
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      <div className="card-body">{children}</div>
    </section>
  )
}

export function Spinner({ label }) {
  return (
    <div className="spin-wrap">
      <span className="spinner" />
      {label && <span className="spin-label">{label}</span>}
    </div>
  )
}

export function ErrorMsg({ error, onRetry }) {
  if (!error) return null
  const msg = errText(error)
  const needsAuth = error instanceof ApiError && (error.code === 'requires_auth' || error.requires_auth || error.code === 'awaiting_authentication')
  return (
    <div className="notice n-error" role="alert">
      <div className="notice-body">
        {needsAuth && <Badge tone="warn">Awaiting authentication</Badge>}
        <span>{msg}</span>
      </div>
      {onRetry && <button className="btn btn-ghost btn-sm" onClick={onRetry}>Retry</button>}
    </div>
  )
}

export function Notice({ children, tone, title, onDismiss }) {
  if (!children) return null
  return (
    <div className={`notice n-${tone || 'info'}`}>
      <div className="notice-body">
        {title && <strong>{title}</strong>}
        <span>{children}</span>
      </div>
      {onDismiss && <button className="btn btn-ghost btn-sm" onClick={onDismiss}>×</button>}
    </div>
  )
}

export function Empty({ children }) {
  return <p className="empty">{children || 'Nothing here yet.'}</p>
}

export function Field({ label, hint, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  )
}

export function TextArea({ rows, ...rest }) {
  return <textarea rows={rows || 4} {...rest} />
}

export function Input(rest) {
  return <input {...rest} />
}

export function Select({ options, ...rest }) {
  return (
    <select {...rest}>
      {(options || []).map((o) =>
        typeof o === 'string' ? (
          <option key={o} value={o}>{o}</option>
        ) : (
          <option key={o.value} value={o.value}>{o.label}</option>
        ),
      )}
    </select>
  )
}

export function Btn({ children, onClick, busy, variant, disabled, type, className }) {
  return (
    <button
      type={type || 'button'}
      className={`btn btn-${variant || 'primary'} ${className || ''}`}
      onClick={onClick}
      disabled={disabled || busy}
      aria-busy={!!busy}
    >
      {busy && <span className="spinner spinner-sm" />}
      {children}
    </button>
  )
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          className={`tab ${value === t.id ? 'tab-on' : ''}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

export function Result({ data, empty }) {
  if (data === null || data === undefined) return null
  return (
    <pre className="result">{typeof data === 'string' ? data : JSON.stringify(data, null, 2)}</pre>
  )
}

export function AiMeta({ data }) {
  if (!data || typeof data !== 'object') return null
  const fb = data.fallback || data.generated_by === 'fallback'
  return (
    <div className="ai-meta">
      <Badge tone={fb ? 'warn' : 'ok'}>{fb ? 'fallback' : (data.generated_by || 'ai')}</Badge>
      {data.model && <Badge>{data.model}</Badge>}
      {data.latency_ms != null && <Badge>{data.latency_ms} ms</Badge>}
    </div>
  )
}
