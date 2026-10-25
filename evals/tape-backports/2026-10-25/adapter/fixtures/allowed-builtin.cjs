const test = require('tape');
const fs = process.getBuiltinModule('node:fs');
test('ordinary builtin access', t => {
  t.equal(typeof fs.readFileSync, 'function');
  t.equal(fs, require('node:fs'));
  t.end();
});
