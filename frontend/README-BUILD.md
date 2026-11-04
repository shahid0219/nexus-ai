# NEXUS AI frontend — build notes

Plain Vite 5 + React 18 + react-router-dom 6 SPA. No TypeScript, no UI kit,
no CDN assets. Design system: `src/styles.css`.

## Commands

```powershell
npm install     # project .npmrc disables lifecycle scripts (see below)
npm run build   # -> dist/ (served by the FastAPI backend)
npm run dev     # dev server, /api proxied to http://127.0.0.1:8777
```

## Why `.npmrc` sets `ignore-scripts=true`

This build sandbox (DeepSeek Harness) denies Node child processes that use
piped stdio — any `child_process.spawn` with `stdio: 'pipe'` fails with
`spawn EPERM`. esbuild's `postinstall` script therefore cannot run, and
nothing in this dependency tree needs install scripts.

## Why `node_modules/esbuild` is patched

Vite calls esbuild's JS API, and the **native** esbuild service always runs
as a spawned child process with piped stdio — impossible here
(`[vite:esbuild] spawn EPERM`).

The fix: `node_modules/esbuild/lib/main.js` is replaced by a wrapper that
runs the official **esbuild WebAssembly build in-process** (no child
process at all), exposing the same API Vite imports
(`transform`, `formatMessages`, `build`, `context`, `version`).

- Source of truth: `esbuild-shim/` (`main.js` + `wasm/browser.js` +
  `wasm/esbuild.wasm`, copied from the `esbuild-wasm` package).
- Applied automatically by `scripts/ensure-esbuild-inprocess.mjs`, which
  runs on `prebuild` / `predev` and is idempotent.
- The untouched native entry is kept at
  `node_modules/esbuild/lib/main.native.js`.

### Recovery if a reinstall wipes the patch

```powershell
npm install esbuild-wasm@0.21.5 --no-save --ignore-scripts
# then copy esbuild-wasm's lib/browser.js + esbuild.wasm into esbuild-shim/wasm/
npm run build        # prebuild re-applies the patch automatically
```

## Layout

```
frontend/
  package.json  vite.config.js  index.html  .npmrc
  esbuild-shim/            # in-process esbuild patch source (see above)
  scripts/                 # ensure-esbuild-inprocess.mjs (prebuild)
  src/
    main.jsx  App.jsx  api.js  ui.jsx  styles.css
    pages/  Dashboard, Approvals, Instagram, YouTube, LinkedIn, Content,
            Monetisation, Automation, Accounts, Logs
  dist/                    # build output (gitignored)
```
