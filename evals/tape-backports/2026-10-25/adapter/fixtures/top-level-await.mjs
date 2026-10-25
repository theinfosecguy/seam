import test from 'tape';
await Promise.resolve();
test('unsupported asynchronous ESM', t => { t.pass('not executed'); t.end(); });
