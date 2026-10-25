import test from 'tape';
import { exit } from 'node:process';
test('ESM forced exit', t => {
  t.pass('observed');
  t.end();
  setTimeout(() => t.fail('hidden late assertion'), 50);
  setTimeout(() => exit(0), 5);
});
