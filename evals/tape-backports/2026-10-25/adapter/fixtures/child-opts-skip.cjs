const tape = require('tape'); tape('parent', t => { t.test('skipped child', { skip: true }, child => { child.fail('never runs'); child.end(); }); t.pass('normal'); t.end(); });
