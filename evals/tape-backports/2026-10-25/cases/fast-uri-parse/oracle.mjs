import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';
const require = createRequire(import.meta.url);

const uri = require('/work/repo/index.js');
test('test_security', () => {
  const parsed = uri.parse('ht%74ps://example.test/');
  assert.equal(parsed.error, 'URI scheme is malformed.', 'URI_ENCODED_SCHEME_REJECTED');
  assert.notEqual(parsed.scheme, 'https', 'URI_ENCODED_SCHEME_REJECTED');
});
test('test_ordinary_scheme', () => {
  assert.equal(uri.parse('HTTPS://example.test/').scheme, 'https');
});
test('test_ordinary_serialize', () => {
  assert.equal(uri.serialize({scheme: 'foo+bar', path: 'value'}), 'foo+bar:value');
});
