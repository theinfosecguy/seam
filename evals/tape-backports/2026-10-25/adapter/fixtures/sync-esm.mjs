import test, { test as namedTest } from 'tape';
test('default synchronous ESM', t => { t.pass('default'); t.end(); });
namedTest('named synchronous ESM', t => { t.pass('named'); t.end(); });
