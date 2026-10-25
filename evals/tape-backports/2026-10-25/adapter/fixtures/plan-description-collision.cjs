const test = require('tape');
test('ordinary assertion message matches plan diagnostic', t => {
  t.fail('plan != count');
  t.end();
});
