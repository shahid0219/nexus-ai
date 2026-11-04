const cp = require('child_process')
const orig = cp.spawn
cp.spawn = function (file, args, opts) {
  try {
    return orig.call(this, file, args, opts)
  } catch (e) {
    console.error('SPAWN-FAIL file=' + file + ' args=' + JSON.stringify(args) + ' stdio=' + JSON.stringify(opts && opts.stdio) + ' code=' + e.code)
    console.error(new Error('trace').stack)
    throw e
  }
}
