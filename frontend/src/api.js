export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message)
    this.status = status
    this.payload = payload || {}
    this.code = (payload && payload.code) || null
    this.approval_id = payload && payload.approval_id
    this.requires_auth = payload && payload.requires_auth
  }
}

function humanDetail(payload, status) {
  if (payload && typeof payload.detail === 'string' && payload.detail) return payload.detail
  if (payload && payload.detail) {
    try { return JSON.stringify(payload.detail) } catch { /* ignore */ }
  }
  return `Request failed (HTTP ${status})`
}

async function request(path, opts = {}) {
  const { method = 'GET', body } = opts
  let res
  try {
    res = await fetch(path, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (e) {
    throw new ApiError(`Network error: ${e.message || e}`, 0, null)
  }
  const text = await res.text()
  let payload = null
  if (text) {
    try { payload = JSON.parse(text) } catch { payload = { detail: text } }
  }
  if (!res.ok) throw new ApiError(humanDetail(payload, res.status), res.status, payload)
  return payload
}

export const api = {
  get: (p) => request(p),
  post: (p, body) => request(p, { method: 'POST', body: body === undefined ? {} : body }),
  del: (p) => request(p, { method: 'DELETE' }),
}

export const qs = (params) => {
  const u = new URLSearchParams()
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') u.set(k, v)
  })
  const s = u.toString()
  return s ? `?${s}` : ''
}

export function errText(e) {
  if (!e) return ''
  if (e instanceof ApiError) return e.message
  return e.message || String(e)
}

export function isAuthError(e) {
  return !!(e && (e.code === 'requires_auth' || e.requires_auth || e.code === 'awaiting_authentication'))
}
