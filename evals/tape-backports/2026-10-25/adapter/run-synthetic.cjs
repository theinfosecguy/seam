const fs = require('node:fs');
const { spawnSync } = require('node:child_process');
fs.cpSync('/fixtures', '/work/repo', { recursive: true });
fs.symlinkSync('/opt/seam/node_modules', '/work/repo/node_modules', 'dir');
process.chdir('/work/repo');
const adapter = fs.readFileSync('/adapter/tape.cjs.txt', 'utf8');
const { createHash } = require('node:crypto');
if (createHash('sha256').update(adapter).digest('hex')
    !== '6795d26b4898a9de9881dd9216ad7494403f9c1d90ad33f5900c650d326e1894') {
  throw new Error('The adapter does not match the frozen proof input');
}
const results = {};
for (const filename of fs.readdirSync('/fixtures').filter(name => /\.[cm]?js$/.test(name))
  .filter(name => !process.argv[2] || name === process.argv[2]).sort()) {
  fs.writeFileSync('/report.xml', '');
  const result = spawnSync(process.execPath, ['--eval', adapter, '--', `/work/repo/${filename}`], {
    encoding: 'utf8', timeout: 5000, maxBuffer: 2 * 1024 * 1024,
  });
  results[filename] = {
    exitCode: result.status, signal: result.signal,
    report: fs.readFileSync('/report.xml', 'utf8'),
  };
}
console.log(JSON.stringify(results, null, 2));
