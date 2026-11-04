'use strict'

/**
 * In-process esbuild entry for the NEXUS AI frontend build.
 *
 * The build sandbox refuses Node child processes that use piped stdio
 * (`spawn EPERM`), and the native esbuild service always runs as such a
 * child process. This entry runs the official esbuild WebAssembly build
 * (bundled in ../wasm/, copied from the esbuild-wasm package) fully
 * in-process, exposing the same API surface Vite imports:
 *
 *   import esbuild, { transform, formatMessages, build } from 'esbuild'
 *   import { version } from 'esbuild'
 *
 * The original native entry is preserved as ./main.native.js.
 *
 * NOTE: this file is copied to node_modules/esbuild/lib/main.js by
 * scripts/ensure-esbuild-inprocess.mjs (run automatically as prebuild).
 */

const path = require('path')

// esbuild-wasm's in-process bootstrap copies browser globals off `self`,
// which does not exist in Node.
if (typeof globalThis.self === 'undefined') {
  Object.defineProperty(globalThis, 'self', {
    value: globalThis,
    writable: true,
    configurable: true,
  })
}

const wasm = require(path.join(__dirname, '..', 'wasm', 'browser.js'))
const wasmModulePath = path.join(__dirname, '..', 'wasm', 'esbuild.wasm')

let readyPromise = null
function ensureReady() {
  if (!readyPromise) {
    readyPromise = (async () => {
      const fs = require('fs')
      const bytes = fs.readFileSync(wasmModulePath)
      const module = await WebAssembly.compile(bytes)
      await wasm.initialize({ wasmModule: module, worker: false })
      return wasm
    })()
    readyPromise.catch((err) => {
      readyPromise = null
      throw err
    })
  }
  return readyPromise
}

const whenReady = (fn) => (...args) => ensureReady().then(() => fn(...args))

const transform = whenReady(wasm.transform)
const formatMessages = whenReady(wasm.formatMessages)
const analyzeMetafile = whenReady(wasm.analyzeMetafile)
const build = whenReady(wasm.build)
const context = whenReady(wasm.context)
const initialize = () => ensureReady()
const stop = () =>
  ensureReady().then(() => {
    if (typeof wasm.stop === 'function') return wasm.stop()
    return undefined
  })
const version = wasm.version

const unsupportedSync = (name) => () => {
  const asyncName = name.replace(/Sync$/, '')
  throw new Error(
    `esbuild: ${name}() is unavailable with the in-process wasm service; ` +
      `call the async ${asyncName}() API instead`,
  )
}
const transformSync = unsupportedSync('transformSync')
const buildSync = unsupportedSync('buildSync')
const formatMessagesSync = unsupportedSync('formatMessagesSync')
const analyzeMetafileSync = unsupportedSync('analyzeMetafileSync')

exports.transform = transform
exports.formatMessages = formatMessages
exports.analyzeMetafile = analyzeMetafile
exports.build = build
exports.context = context
exports.initialize = initialize
exports.stop = stop
exports.version = version
exports.transformSync = transformSync
exports.buildSync = buildSync
exports.formatMessagesSync = formatMessagesSync
exports.analyzeMetafileSync = analyzeMetafileSync
