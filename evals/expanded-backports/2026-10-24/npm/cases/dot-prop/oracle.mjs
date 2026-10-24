import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);

const dotProp = require('/work/repo/index.js');

test('test_security', () => {
  const value = { constructor: { seam_probe: 'local' } };
  assert.equal(dotProp.get(value, 'constructor.seam_probe'), undefined,
    'DOT_PROP_RESERVED_PATH_REJECTED');
});

test('test_nested_lookup', () => {
  assert.equal(dotProp.get({ entry: { name: 'demo' } }, 'entry.name'), 'demo');
});

test('test_local_assignment', () => {
  const value = {};
  dotProp.set(value, 'entry.count', 2);
  assert.deepEqual(value, { entry: { count: 2 } });
});
