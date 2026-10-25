const test = require('tape');
test('bounded structured events', t => {
  for (let i = 0; i < 1000; i++) t.pass('x'.repeat(2000));
  t.end();
});
