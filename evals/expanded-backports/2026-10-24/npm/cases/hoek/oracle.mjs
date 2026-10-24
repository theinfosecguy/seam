import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);

const clone = require('/work/repo/lib/clone.js');

test('test_security', () => {
  const value = JSON.parse('{"__proto__":{"seam_probe":"local"}}');
  const copy = clone(value);
  assert.equal(Object.getPrototypeOf(copy), Object.prototype,
    'HOEK_CLONE_PROTOTYPE_PRESERVED');
  assert.equal(copy.seam_probe, undefined, 'HOEK_CLONE_PROTOTYPE_PRESERVED');
});

test('test_nested_clone', () => {
  const value = { entry: { count: 2 } };
  const copy = clone(value);
  assert.deepEqual(copy, value);
  assert.notEqual(copy.entry, value.entry);
});

test('test_array_clone', () => {
  const value = [1, { name: 'demo' }];
  const copy = clone(value);
  assert.deepEqual(copy, value);
  assert.notEqual(copy[1], value[1]);
});
