import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';
import util from 'node:util';
import { Worker } from 'node:worker_threads';

const require = createRequire(import.meta.url);
const debug = require('/work/repo/src/node.js');
const format = (text) => debug.formatters.o.call({ inspectOpts: {}, useColors: false }, {
  [util.inspect.custom]() { return text; },
});

test('test_security', async () => {
  const worker = new Worker(`
    const { parentPort } = require('node:worker_threads');
    const util = require('node:util');
    const debug = require('/work/repo/src/node.js');
    parentPort.postMessage('ready');
    parentPort.once('message', () => {
      debug.formatters.o.call({ inspectOpts: {}, useColors: false }, {
        [util.inspect.custom]() { return ' '.repeat(150000); }
      });
      parentPort.postMessage('finished');
    });
  `, { eval: true });
  try {
    const completed = await new Promise((resolve, reject) => {
      worker.once('error', reject);
      worker.once('message', () => {
        const deadline = setTimeout(() => resolve(false), 1500);
        worker.once('message', () => { clearTimeout(deadline); resolve(true); });
        worker.postMessage('format');
      });
    });
    assert.equal(completed, true, 'DEBUG_FORMATTER_BOUNDED_WORK');
  } finally {
    await worker.terminate();
  }
});

test('test_normal_formatter', () => {
  assert.equal(format('ordinary'), 'ordinary');
});

test('test_multiline_formatter', () => {
  assert.equal(format('alpha\n beta'), 'alpha beta');
});
