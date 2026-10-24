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

const semver = require('/work/repo/index.js');
test('test_security', async () => {
  assert.equal(await bounded({
    setup: "const Range = require('/work/repo/classes/range.js');",
    run: "new Range('1.2.3 ' + ' '.repeat(150000) + ' <1.3.0');",
  }), true, 'SEMVER_WHITESPACE_BOUNDED_WORK');
});
test('test_ordinary_version', () => {
  assert.equal(semver.valid('1.2.3'), '1.2.3');
});
test('test_ordinary_range', () => {
  assert.equal(semver.satisfies('1.2.3', '>=1.0.0 <2.0.0'), true);
});
