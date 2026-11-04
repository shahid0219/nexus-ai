import React, { useState } from 'react'
import { api } from '../api.js'
import {
  Badge, Btn, Card, Empty, ErrorMsg, Field, Input, Notice, Spinner, TextArea,
  useLoad,
} from '../ui.jsx'

function ScanRow({ f }) {
  return (
    <div className="row">
      <Badge tone={f.rule === 'forbidden_path' ? 'err' : 'warn'}>{f.rule}</Badge>
      <span className="mono">{f.path}:{f.line}</span>
      {f.preview && <span className="dim">{f.preview}</span>}
    </div>
  )
}

export default function GitHubPage() {
  const status = useLoad(() => api.get('/api/github/status'), [])
  const [scan, setScan] = useState(null)
  const [scanning, setScanning] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState(null)
  const [commitMsg, setCommitMsg] = useState('')
  const [paths, setPaths] = useState('')
  const [busy, setBusy] = useState(false)
  const [verify, setVerify] = useState(null)
  const [preview, setPreview] = useState(null)

  const runScan = async () => {
    setScanning(true); setErr(null)
    try { setScan(await api.get('/api/github/secret-scan'))
    } catch (e) { setErr(e) } finally { setScanning(false) }
  }

  const doCommit = async () => {
    setBusy(true); setErr(null); setMsg('')
    try {
      const list = paths.split('\n').map((p) => p.trim()).filter(Boolean)
      const d = await api.post('/api/github/commit',
        { message: commitMsg, paths: list, push: true })
      if (d.code === 'nothing_to_commit') setMsg('Nothing to commit — no staged changes.')
      else setMsg(`${d.code}: ${d.sha?.slice(0, 8) || ''} ${d.pushed ? '(pushed)' : ''} — ${d.staged?.length || 0} files`)
      status.reload()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const doVerify = async () => {
    setBusy(true); setErr(null)
    try { setVerify(await api.get('/api/github/verify')) } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const loadPreview = async () => {
    setBusy(true); setErr(null)
    try { setPreview(await api.get('/api/github/profile/preview')) } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const st = status.data
  const gh = st?.gh || {}

  return (
    <div className="stack">
      <div className="page-head">
        <h2>GitHub</h2>
        <p>Repository status, secret scanning and a safe commit/push workflow. Your gh login is used — NEXUS never reads or stores the token.</p>
      </div>

      {msg && <Notice tone="ok" onDismiss={() => setMsg('')}>{msg}</Notice>}
      {err && <ErrorMsg error={err} />}
      {status.error && <ErrorMsg error={status.error} onRetry={status.reload} />}
      {status.loading && !status.data && <Spinner label="Loading repository status…" />}

      {st && (
        <>
          <Card title="Connection" actions={<Btn variant="ghost" onClick={status.reload} busy={status.loading}>Refresh</Btn>}>
            <dl className="kv">
              <dt>Account</dt>
              <dd>
                {gh.authenticated
                  ? <><Badge tone="ok">connected via gh</Badge> <strong>{gh.account}</strong></>
                  : <><Badge tone="warn">not authenticated</Badge> {gh.detail}</>}
              </dd>
              <dt>Scopes</dt><dd>{gh.scopes || '—'}</dd>
              <dt>Remote</dt>
              <dd>{st.remote_ok ? <Badge tone="ok">{st.remote}</Badge> : <Badge tone="err">{st.remote || 'none'}</Badge>}</dd>
              <dt>Branch</dt><dd>{st.branch || '—'} {st.ahead != null && <span className="dim">(ahead {st.ahead} / behind {st.behind})</span>}</dd>
              <dt>Working tree</dt>
              <dd>
                {st.dirty
                  ? <><Badge tone="warn">{st.changed_files} changed</Badge></>
                  : <Badge tone="ok">clean</Badge>}
              </dd>
              <dt>Last commit</dt><dd className="mono">{st.last_commit?.hash?.slice(0, 8)} {st.last_commit?.subject}</dd>
            </dl>
          </Card>

          <Card title="Secret scan" actions={<Btn variant="ghost" onClick={runScan} busy={scanning}>Run scan</Btn>}>
            {!scan && <Empty>No scan yet — run one before committing.</Empty>}
            {scan && (
              <div className="stack">
                <div className="row">
                  <Badge tone={scan.clean ? 'ok' : 'err'}>{scan.clean ? 'clean' : `${scan.findings.length} finding(s)`}</Badge>
                  <span className="dim">{scan.scanned_files} files scanned</span>
                </div>
                {scan.findings.slice(0, 20).map((f, i) => <ScanRow key={i} f={f} />)}
              </div>
            )}
            <p className="dim mt">Every commit and push is blocked until the scan is clean. Scans cover tracked and untracked files against 10 credential patterns.</p>
          </Card>

          <Card title="Commit & push (NEXUS source only)">
            <Field label="Commit message">
              <Input value={commitMsg} onChange={(e) => setCommitMsg(e.target.value)}
                     placeholder="feat: describe the change" />
            </Field>
            <Field label="Paths to commit (one per line)"
                   hint="Credentials, databases, node_modules, dist, .env and caches are always refused.">
              <TextArea rows={5} value={paths} onChange={(e) => setPaths(e.target.value)}
                        placeholder={'backend/app/main.py\nfrontend/src/App.jsx'} />
            </Field>
            <Btn busy={busy} onClick={doCommit}
                 disabled={!commitMsg.trim() || paths.trim().length === 0}>
              Commit &amp; push
            </Btn>
          </Card>

          <Card title="Remote verification" actions={<Btn variant="ghost" onClick={doVerify} busy={busy}>Verify</Btn>}>
            {!verify && <Empty>Compares local HEAD with origin HEAD and reads repo metadata.</Empty>}
            {verify && (
              <dl className="kv">
                <dt>Local HEAD</dt><dd className="mono">{verify.local_head}</dd>
                <dt>Remote HEAD</dt><dd className="mono">{verify.remote_head || '—'}</dd>
                <dt>In sync</dt>
                <dd>{verify.in_sync ? <Badge tone="ok">yes</Badge> : <Badge tone="warn">no</Badge>}</dd>
                <dt>Repo</dt>
                <dd>{verify.repo ? `${verify.repo.name} · ${verify.repo.visibility}` : '—'}</dd>
              </dl>
            )}
          </Card>

          <Card title="Public developer profile" actions={<Btn variant="ghost" onClick={loadPreview} busy={busy}>Build preview</Btn>}>
            {!preview && <Empty>Previews the proposed bio, README and topics. Nothing is applied — updates require your approval in the Approvals page.</Empty>}
            {preview && (
              <div className="stack">
                <div className="row">
                  <Badge tone={preview.nexus_stays_private ? 'ok' : 'info'}>
                    nexus-ai stays {preview.nexus_repo_public ? 'public' : 'private'}
                  </Badge>
                  <Badge>{preview.public_repos.length} public repo(s)</Badge>
                </div>
                <p className="dim">Detected stack (from real repos): {preview.detected_stack.languages.join(', ') || 'none public yet'}</p>
                {preview.public_repos.length === 0 && (
                  <Notice tone="info">
                    No public repositories yet. A profile README repo can be created once
                    you approve; it is the sensible first public artefact.
                  </Notice>
                )}
                <p className="dim">{preview.note}</p>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  )
}
