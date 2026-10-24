import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { Duplex } from 'node:stream';
import test from 'node:test';

const require = createRequire(import.meta.url);
const WebSocketServer = require('/work/repo/lib/websocket-server.js');

function checkRequest(t, headers, method = 'GET') {
  const server = new WebSocketServer({ noServer: true });
  const socket = new Duplex({
    read() {},
    write(chunk, encoding, done) { done(); },
  });
  t.after(() => { socket.destroy(); server.close(); });
  server.handleUpgrade({ method, headers }, socket, Buffer.alloc(0), () => {
    assert.fail('Unexpected accepted upgrade');
  });
}

test('test_security', (t) => {
  assert.doesNotThrow(() => checkRequest(t, {
    'sec-websocket-key': Buffer.alloc(16).toString('base64'),
    'sec-websocket-version': '13',
  }), 'WS_MISSING_UPGRADE_REJECTED');
});

test('test_invalid_upgrade_rejected', (t) => {
  assert.doesNotThrow(() => checkRequest(t, { upgrade: 'ordinary' }));
});

test('test_non_get_request_rejected', (t) => {
  assert.doesNotThrow(() => checkRequest(t, { upgrade: 'websocket' }, 'POST'));
});
