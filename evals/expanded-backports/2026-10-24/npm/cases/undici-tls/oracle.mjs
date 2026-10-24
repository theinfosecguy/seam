import assert from 'node:assert/strict';
import { once } from 'node:events';
import fs from 'node:fs';
import https from 'node:https';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const { Agent, request } = require('/work/repo');
const fixture = (name) => fs.readFileSync(`/work/repo/test/fixtures/${name}`, 'utf8');

async function endpoint(t, options) {
  const server = https.createServer({ key: fixture('key.pem'), cert: fixture('cert.pem') },
    (req, res) => res.end('ordinary'));
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const agent = new Agent(options);
  t.after(async () => {
    await agent.close();
    await new Promise((resolve) => server.close(resolve));
  });
  return { agent, url: `https://127.0.0.1:${server.address().port}` };
}

const trusted = () => ({ ca: fixture('ca.pem'), servername: 'agent1' });

test('test_security', async (t) => {
  let calls = 0;
  const { agent, url } = await endpoint(t, { tls: {
    ...trusted(),
    checkServerIdentity() { calls++; return new Error('reviewed validation rejection'); },
  } });
  await assert.rejects(request(url, { dispatcher: agent }), /reviewed validation rejection/,
    'TLS_VALIDATION_CALLBACK_PRESERVED');
  assert.equal(calls, 1);
});

test('test_connect_callback', async (t) => {
  const { agent, url } = await endpoint(t, { connect: {
    ...trusted(),
    checkServerIdentity() { return new Error('normal connect validation rejection'); },
  } });
  await assert.rejects(request(url, { dispatcher: agent }), /normal connect validation rejection/);
});

test('test_trusted_tls_request', async (t) => {
  const { agent, url } = await endpoint(t, { tls: trusted() });
  const response = await request(url, { dispatcher: agent });
  assert.equal(response.statusCode, 200);
  assert.equal(await response.body.text(), 'ordinary');
});
