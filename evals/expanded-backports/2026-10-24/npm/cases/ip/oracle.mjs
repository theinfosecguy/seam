import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const ip = require('/work/repo/lib/ip.js');

test('test_security', () => {
  assert.equal(ip.isPrivate('0x7f.1'), true, 'IP_PRIVATE_ALTERNATE_NOTATION');
});

test('test_private_dotted_decimal', () => {
  assert.equal(ip.isPrivate('127.0.0.1'), true);
  assert.equal(ip.isPrivate('10.0.0.1'), true);
});

test('test_public_dotted_decimal', () => {
  assert.equal(ip.isPrivate('8.8.8.8'), false);
});
