import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);

const parse = require('/work/repo/index.js');

test('test_security', () => {
  const value = parse(['--entry.__proto__=local']);
  assert.equal(Object.hasOwn(value.entry, '___proto___'), true,
    'YARGS_RESERVED_KEY_SANITIZED');
  assert.equal(value.entry.___proto___, 'local', 'YARGS_RESERVED_KEY_SANITIZED');
});

test('test_positional_and_number', () => {
  const value = parse(['--count', '3', 'input']);
  assert.equal(value.count, 3);
  assert.deepEqual(value._, ['input']);
});

test('test_boolean_alias', () => {
  const value = parse(['-v'], { boolean: ['v'], alias: { v: ['verbose'] } });
  assert.equal(value.v, true);
  assert.equal(value.verbose, true);
});
