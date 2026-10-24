import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';
const require = createRequire(import.meta.url);
import http from 'node:http';
import { once } from 'node:events';
const axios = (await import('/work/repo/index.js')).default;

async function requestToLocalServers(options) {
  const counts = [0, 0];
  const servers = counts.map((_, index) => http.createServer((request, response) => {
    counts[index]++;
    response.end(index === 0 ? 'base' : 'absolute');
  }));
  try {
    await Promise.all(servers.map(async server => {
      server.listen(0, '127.0.0.1');
      await once(server, 'listening');
    }));
    const urls = servers.map(server => `http://127.0.0.1:${server.address().port}`);
    const result = await axios.get(urls[1] + '/ordinary', {
      baseURL: urls[0], proxy: false, timeout: 2000, ...options,
    });
    return { body: result.data, counts };
  } finally {
    await Promise.all(servers.map(server => new Promise(resolve => server.close(resolve))));
  }
}
test('test_security', async () => {
  const result = await requestToLocalServers({allowAbsoluteUrls: false});
  assert.deepEqual(result, {body: 'base', counts: [1, 0]}, 'AXIOS_BASE_URL_RESTRICTION');
});
test('test_absolute_url_default', async () => {
  assert.deepEqual(await requestToLocalServers({}), {body: 'absolute', counts: [0, 1]});
});
test('test_absolute_url_enabled', async () => {
  assert.deepEqual(await requestToLocalServers({allowAbsoluteUrls: true}), {
    body: 'absolute', counts: [0, 1],
  });
});
