import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const { parseSetCookie } = require('/work/repo/lib/web/cookies/parse.js');

test('test_security', () => {
  assert.equal(parseSetCookie('session=alpha%3Bbeta').value, 'alpha%3Bbeta',
    'COOKIE_ENCODED_VALUE_PRESERVED');
});

test('test_plain_cookie', () => {
  assert.equal(parseSetCookie('session=ordinary').value, 'ordinary');
});

test('test_samesite_strict', () => {
  assert.equal(parseSetCookie('session=ordinary; SameSite=Strict').sameSite, 'Strict');
});
