const tape = require('tape'); tape.skip('unobserved skipped case', t => { t.fail('never runs'); t.end(); }); tape('observed', t => { t.pass('normal'); t.end(); });
