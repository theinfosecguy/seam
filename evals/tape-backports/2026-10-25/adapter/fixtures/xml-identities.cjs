const test = require('tape');
test('scope < & "', t => {
  t.test('child\n\t\r >\' < &', sub => { sub.pass('same'); sub.pass('same'); sub.end(); });
  t.end();
});
