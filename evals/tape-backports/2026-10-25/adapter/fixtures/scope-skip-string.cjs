const tape = require('tape'); tape('skipped reason', { skip: 'not available' }, t => { t.fail('never runs'); t.end(); }); tape('observed', t => { t.pass('normal'); t.end(); });
