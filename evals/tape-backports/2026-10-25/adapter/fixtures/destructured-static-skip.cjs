const { skip, test } = require('tape'); skip('unobserved destructured skip', t => { t.end(); }); test('observed', t => { t.pass('normal'); t.end(); });
