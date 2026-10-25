const tape = require('tape'); tape('parent', t => { for (let n = 0; n < 2; n += 1) t.test('same child', child => { child.pass('normal'); child.end(); }); t.end(); });
