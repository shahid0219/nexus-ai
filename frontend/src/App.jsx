import React, { useCallback, useEffect, useState } from 'react'
import { Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { api } from './api.js'
import Dashboard from './pages/Dashboard.jsx'
import Approvals from './pages/Approvals.jsx'
import Instagram from './pages/Instagram.jsx'
import YouTube from './pages/YouTube.jsx'
import LinkedIn from './pages/LinkedIn.jsx'
import Content from './pages/Content.jsx'
import Monetisation from './pages/Monetisation.jsx'
import Automation from './pages/Automation.jsx'
import Accounts from './pages/Accounts.jsx'
import Settings from './pages/Settings.jsx'
import GitHubPage from './pages/GitHubPage.jsx'
import Logs from './pages/Logs.jsx'

const NAV = [
  { to: '/', label: 'Dashboard', ico: '◈', end: true },
  { to: '/approvals', label: 'Approvals', ico: '✓' },
  { to: '/instagram', label: 'Instagram', ico: '◎' },
  { to: '/youtube', label: 'YouTube', ico: '▶' },
  { to: '/linkedin', label: 'LinkedIn', ico: 'in' },
  { to: '/content', label: 'Content', ico: '✎' },
  { to: '/monetisation', label: 'Monetisation', ico: '¤' },
  { to: '/automation', label: 'Automation', ico: '⚙' },
  { to: '/accounts', label: 'Accounts', ico: '⚿' },
  { to: '/settings', label: 'AI Settings', ico: '✦' },
  { to: '/github', label: 'GitHub', ico: '◉' },
  { to: '/logs', label: 'Logs & Tasks', ico: '≡' },
]

const TITLES = Object.fromEntries(NAV.map((n) => [n.to, n.label]))

function HealthPill() {
  const [h, setH] = useState(null)
  const [err, setErr] = useState(false)
  const load = useCallback(() => {
    api
      .get('/api/health')
      .then((d) => { setH(d); setErr(false) })
      .catch(() => { setH(null); setErr(true) })
  }, [])
  useEffect(() => {
    load()
    const t = setInterval(load, 20000)
    return () => clearInterval(t)
  }, [load])
  if (err) return <span className="health bad"><span className="dot" />API offline</span>
  if (!h) return <span className="health"><span className="dot" />checking…</span>
  const oll = h.ollama || {}
  return (
    <span className={`health ${h.status === 'ok' ? 'ok' : 'bad'}`} title={`frontend_built: ${h.frontend_built}`}>
      <span className="dot" />
      {h.status || 'unknown'}
      <span className="sep">·</span>v{h.version || '?'}
      <span className="sep">·</span>
      ollama {oll.available ? `${(oll.models || []).length}m` : 'off'}
      {h.uptime_s != null && <><span className="sep">·</span>{Math.round(h.uptime_s)}s</>}
    </span>
  )
}

function Sidebar({ open, onClose }) {
  return (
    <nav className={`sidebar ${open ? 'open' : ''}`}>
      <div className="brand">
        <span className="brand-mark">N</span>
        <span>
          <div className="brand-name">NEXUS AI</div>
          <div className="brand-sub">command centre</div>
        </span>
      </div>
      <div className="nav-label">Workspace</div>
      {NAV.map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.end}
          onClick={onClose}
          className={({ isActive }) => `nav-link ${isActive ? 'on' : ''}`}
        >
          <span className="nav-ico">{n.ico}</span>
          {n.label}
        </NavLink>
      ))}
    </nav>
  )
}

export default function App() {
  const [open, setOpen] = useState(false)
  const loc = useLocation()
  useEffect(() => { setOpen(false) }, [loc.pathname])
  const title = TITLES[loc.pathname] || 'NEXUS AI'
  return (
    <div className="shell">
      <Sidebar open={open} onClose={() => setOpen(false)} />
      {open && <div className="overlay" onClick={() => setOpen(false)} />}
      <div className="main">
        <header className="topbar">
          <button className="btn btn-ghost btn-sm menu-btn" onClick={() => setOpen((v) => !v)} aria-label="Menu">☰</button>
          <h1>{title}</h1>
          <span className="spacer" />
          <HealthPill />
        </header>
        <main className="content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/approvals" element={<Approvals />} />
            <Route path="/instagram" element={<Instagram />} />
            <Route path="/youtube" element={<YouTube />} />
            <Route path="/linkedin" element={<LinkedIn />} />
            <Route path="/content" element={<Content />} />
            <Route path="/monetisation" element={<Monetisation />} />
            <Route path="/automation" element={<Automation />} />
            <Route path="/accounts" element={<Accounts />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/github" element={<GitHubPage />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="*" element={<Dashboard />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
