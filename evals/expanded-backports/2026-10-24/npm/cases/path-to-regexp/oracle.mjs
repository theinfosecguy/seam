import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';
const require = createRequire(import.meta.url);
import { Worker } from 'node:worker_threads';

async function bounded(operation) {
  const worker = new Worker(`
    const { parentPort } = require('node:worker_threads');
    (async () => {
      ${operation.setup}
      parentPort.postMessage('ready');
      parentPort.once('message', () => {
        ${operation.run}
        parentPort.postMessage('finished');
      });
    })();
  `, { eval: true });
  try {
    return await new Promise((resolve, reject) => {
      worker.once('error', reject);
      worker.once('message', () => {
        const deadline = setTimeout(() => resolve(false), 1500);
        worker.once('message', () => { clearTimeout(deadline); resolve(true); });
        worker.postMessage('run');
      });
    });
  } finally {
    await worker.terminate();
  }
}

const route = require('/work/repo/index.js');
test('test_security', async () => {
  assert.equal(await bounded({
    setup: "const route = require('/work/repo/index.js'); const pattern = route('/:a-:b');",
    run: "pattern.test('/' + '-'.repeat(150000) + '/extra');",
  }), true, 'ROUTE_PATTERN_BOUNDED_WORK');
});
test('test_ordinary_match', () => {
  assert.equal(route('/user/:id').test('/user/42'), true);
});
test('test_ordinary_nonmatch', () => {
  assert.equal(route('/user/:id').test('/other/42'), false);
});
