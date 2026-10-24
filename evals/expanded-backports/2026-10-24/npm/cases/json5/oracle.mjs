import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import test from 'node:test';

const parsePath = existsSync('/work/repo/lib/parse.js')
  ? '/work/repo/lib/parse.js'
  : '/work/repo/src/parse.js';
const parse = (await import(parsePath)).default;

test('test_security', () => {
  const value = parse('{"__proto__":{"seam_probe":"local"}}');
  assert.equal(Object.hasOwn(value, '__proto__'), true,
    'JSON5_PROTO_KEY_IS_OWN_DATA');
  assert.equal(Object.getPrototypeOf(value), Object.prototype,
    'JSON5_PROTO_KEY_IS_OWN_DATA');
  assert.equal(value.seam_probe, undefined, 'JSON5_PROTO_KEY_IS_OWN_DATA');
});

test('test_json5_syntax', () => {
  assert.deepEqual(parse('{answer: 42, values: [1, 2,],}'), {
    answer: 42, values: [1, 2],
  });
});

test('test_reviver', () => {
  const value = parse('{count: 2}', (key, item) =>
    typeof item === 'number' ? item + 1 : item);
  assert.deepEqual(value, { count: 3 });
});
