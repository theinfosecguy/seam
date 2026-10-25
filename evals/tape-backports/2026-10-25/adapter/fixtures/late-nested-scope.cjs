const test = require('tape');
test('parent', t => {
  t.pass('parent assertion');
  t.end();
  setTimeout(() => t.test('late nested child', child => {
    child.pass('late child assertion');
    child.end();
  }), 10);
});
