const tape = require('tape'); let observed; tape('observed', t => { observed = t; t.pass('normal'); t.end(); }); process.once('beforeExit', () => { observed.fail('BEFORE_EXIT_TIME_FAILURE'); });
