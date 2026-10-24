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

const ansiRegex = (await import('/work/repo/index.js')).default;
test('test_security', async () => {
  assert.equal(await bounded({
    setup: "const ansiRegex = (await import('/work/repo/index.js')).default;",
    run: "ansiRegex().test('\\u001B[' + ';'.repeat(150000) + '!');",
  }), true, 'ANSI_REGEX_BOUNDED_WORK');
});
test('test_ordinary_escape', () => {
  assert.equal('\u001B[31mred\u001B[0m'.replace(ansiRegex(), ''), 'red');
});
test('test_ordinary_text', () => {
  assert.equal(ansiRegex().test('ordinary text'), false);
});
