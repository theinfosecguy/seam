import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);

const yaml = require('/work/repo/index.js');

test('test_security', () => {
  const value = yaml.load('entry:\n  <<:\n    __proto__:\n      seam_probe: local\n').entry;
  assert.equal(Object.hasOwn(value, '__proto__'), true,
    'JS_YAML_MERGE_PROTO_IS_OWN_DATA');
  assert.equal(Object.getPrototypeOf(value), Object.prototype,
    'JS_YAML_MERGE_PROTO_IS_OWN_DATA');
  assert.equal(value.seam_probe, undefined, 'JS_YAML_MERGE_PROTO_IS_OWN_DATA');
});

test('test_scalar_and_sequence', () => {
  assert.deepEqual(yaml.load('name: demo\ncount: 2\nitems: [one, two]\n'), {
    name: 'demo', count: 2, items: ['one', 'two'],
  });
});

test('test_ordinary_merge', () => {
  const value = yaml.load('defaults: &d\n  retry: 2\nentry:\n  <<: *d\n  mode: safe\n');
  assert.deepEqual(value.entry, { retry: 2, mode: 'safe' });
});
