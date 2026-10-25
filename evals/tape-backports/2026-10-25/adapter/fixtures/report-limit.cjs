const test = require('tape');
for (let i = 0; i < 100; i++) {
  test(String(i) + '&'.repeat(3000), t => {
    t.pass('one assertion');
    t.end();
  });
}
