const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const { createRequire } = require('node:module');

fs.cpSync('/source', '/work/repo', { recursive: true, verbatimSymlinks: true });
assert.ok(fs.statSync('/opt/seam/node_modules').isDirectory());
fs.symlinkSync('/opt/seam/node_modules', '/work/repo/node_modules', 'dir');
const load = createRequire('/work/repo/package.json');
const entry = load.resolve('/work/repo');
assert.ok(entry.startsWith('/work/repo/'));
assert.equal(fs.realpathSync(entry), entry);
const digest = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
assert.equal(digest(entry), process.argv[2]);
load(entry);
const tapeEntry = load.resolve('tape');
assert.ok(tapeEntry.startsWith('/opt/proof/node_modules/tape/'));
const dependencies = {};
for (const name of ['tape', 'side-channel', 'iconv-lite', 'safer-buffer']) {
  const file = load.resolve(name + '/package.json');
  dependencies[name] = { version: JSON.parse(fs.readFileSync(file)).version, file, sha256: digest(file) };
}
process.stdout.write(JSON.stringify({
  node: process.version,
  entry,
  entry_sha256: digest(entry),
  loaded_target_modules: Object.keys(require.cache).filter(file => file.startsWith('/work/repo/')),
  tape_entry: tapeEntry,
  dependencies,
  image_lock_sha256: digest('/opt/proof/package-lock.json'),
}) + '\n');
