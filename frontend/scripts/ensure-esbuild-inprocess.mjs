// Self-healing in-process esbuild patch for the NEXUS AI frontend build.
//
// Why: this build sandbox denies Node child processes that use piped stdio,
// so the native esbuild service (`spawn EPERM`) can never start. Vite needs
// esbuild for transforms, so we swap node_modules/esbuild's entry for a
// wrapper that runs the official esbuild WebAssembly build in-process.
//
// Run automatically via the `prebuild` script. Idempotent: it does nothing
// when the patch is already applied. See README-BUILD.md for recovery steps.
//
// The shim is only needed where Node cannot start the native esbuild service
// (this sandbox denies piped-stdio child processes). On a normal machine and on
// GitHub Actions the native binary works and the shim actively breaks the build,
// so it is skipped unless it is genuinely required. Override with:
//   NEXUS_ESBUILD_SHIM=1   force the shim on
//   NEXUS_ESBUILD_SHIM=0   force it off (even in the sandbox)
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const esbuildLib = path.join(root, 'node_modules', 'esbuild', 'lib')
const target = path.join(esbuildLib, 'main.js')
const marker = 'In-process esbuild entry'

const forced = process.env.NEXUS_ESBUILD_SHIM
if (forced !== '1' && (forced === '0' || process.env.CI || process.platform !== 'win32')) {
  console.log('[ensure-esbuild] native esbuild available; shim not needed')
  process.exit(0)
}

function isPatched() {
  try {
    return fs.readFileSync(target, 'utf8').includes(marker)
  } catch {
    return false
  }
}

if (isPatched()) process.exit(0)

const source = path.join(root, 'esbuild-shim')
const required = [
  path.join(source, 'main.js'),
  path.join(source, 'wasm', 'browser.js'),
  path.join(source, 'wasm', 'esbuild.wasm'),
]
if (!required.every((p) => fs.existsSync(p))) {
  console.warn(
    '[ensure-esbuild] node_modules/esbuild is not patched and esbuild-shim/ is incomplete;',
    'skipping (a native esbuild build will fail with spawn EPERM in this sandbox).',
  )
  process.exit(0)
}

if (!fs.existsSync(path.join(root, 'node_modules', 'esbuild', 'package.json'))) {
  console.warn('[ensure-esbuild] esbuild is not installed; skipping patch.')
  process.exit(0)
}

const wasmDir = path.join(root, 'node_modules', 'esbuild', 'wasm')
fs.mkdirSync(wasmDir, { recursive: true })
for (const name of ['browser.js', 'esbuild.wasm']) {
  fs.copyFileSync(path.join(source, 'wasm', name), path.join(wasmDir, name))
}

const nativeBackup = path.join(esbuildLib, 'main.native.js')
if (!fs.existsSync(nativeBackup) && fs.existsSync(target)) {
  fs.copyFileSync(target, nativeBackup)
}
fs.copyFileSync(path.join(source, 'main.js'), target)
console.log('[ensure-esbuild] applied in-process esbuild (wasm) patch')
