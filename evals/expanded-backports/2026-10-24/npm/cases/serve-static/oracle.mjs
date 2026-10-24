import assert from 'node:assert/strict';
import { once } from 'node:events';
import http from 'node:http';
import { createRequire } from 'node:module';
import { after, test } from 'node:test';

const require = createRequire(import.meta.url);
const serveStatic = require('/work/repo');
const middleware = serveStatic('/work/repo/test/fixtures');
const server = http.createServer((req, res) => {
  middleware(req, res, (error) => {
    res.statusCode = error?.status || 404;
    res.end('Not found');
  });
});
server.listen(0, '127.0.0.1');
await once(server, 'listening');
after(() => new Promise((resolve) => server.close(resolve)));
const origin = `http://127.0.0.1:${server.address().port}`;

test('test_security', async () => {
  const response = await fetch(`${origin}/users`, { redirect: 'manual' });
  assert.equal(response.status, 301);
  assert.equal((await response.text()).includes('<a href='), false,
    'STATIC_REDIRECT_HAS_NO_LINK');
});

test('test_redirect_location', async () => {
  const response = await fetch(`${origin}/users`, { redirect: 'manual' });
  assert.equal(response.headers.get('location'), '/users/');
  await response.text();
});

test('test_file_content', async () => {
  const response = await fetch(`${origin}/users/tobi.txt`);
  assert.equal(response.status, 200);
  assert.equal(await response.text(), 'ferret');
});
