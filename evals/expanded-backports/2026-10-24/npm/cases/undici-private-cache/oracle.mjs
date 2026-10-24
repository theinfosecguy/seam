import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const { parseCacheControlHeader } = require('/work/repo/lib/util/cache.js');

test('test_security', () => {
  assert.deepEqual(
    parseCacheControlHeader('private=""'),
    { private: true },
    'CACHE_PRIVATE_EMPTY_FIELD',
  );
});

test('test_public_max_age', () => {
  assert.deepEqual(parseCacheControlHeader('public, max-age=60'), {
    public: true,
    'max-age': 60,
  });
});

test('test_private_unqualified', () => {
  assert.deepEqual(parseCacheControlHeader('private'), { private: true });
});
