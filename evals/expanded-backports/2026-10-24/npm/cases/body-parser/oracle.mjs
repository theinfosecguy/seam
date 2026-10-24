import assert from 'node:assert/strict';
import { once } from 'node:events';
import http from 'node:http';
import { createRequire } from 'node:module';
import { after, test } from 'node:test';
import { gzipSync } from 'node:zlib';

const require = createRequire(import.meta.url);
const bodyParser = require('/work/repo');
const middleware = bodyParser.text({ verify() {} });
const server = http.createServer((req, res) => {
  let pipeCalls = 0;
  const pipe = req.pipe;
  req.pipe = function (...args) { pipeCalls++; return pipe.apply(this, args); };
  middleware(req, res, (error) => {
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ status: error?.status || 200, body: req.body, pipeCalls }));
  });
});
server.listen(0, '127.0.0.1');
await once(server, 'listening');
after(() => new Promise((resolve) => server.close(resolve)));
const url = `http://127.0.0.1:${server.address().port}`;

async function send(charset, compressed) {
  const body = compressed ? gzipSync('ordinary') : Buffer.from('ordinary');
  const response = await fetch(url, {
    method: 'POST', body,
    headers: {
      'Content-Type': `text/plain; charset=${charset}`,
      'Content-Encoding': compressed ? 'gzip' : 'identity',
    },
  });
  return response.json();
}

test('test_security', async () => {
  const result = await send('x-bogus', true);
  assert.equal(result.status, 415);
  assert.equal(result.pipeCalls, 0, 'CHARSET_CHECK_BEFORE_DECOMPRESSION');
});

test('test_plain_text', async () => {
  const result = await send('utf-8', false);
  assert.equal(result.status, 200);
  assert.equal(result.body, 'ordinary');
});

test('test_compressed_text', async () => {
  const result = await send('utf-8', true);
  assert.equal(result.status, 200);
  assert.equal(result.body, 'ordinary');
});
