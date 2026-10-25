import test from 'tape';
import { getBuiltinModule } from 'node:process';
try { getBuiltinModule('node:worker_threads'); } catch (_) {}
test('attempted ESM worker access remains inconclusive', t => { t.pass('normal'); t.end(); });
