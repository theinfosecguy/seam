const tape = require('tape'); let observed; tape('observed', t => { observed = t; t.pass('normal'); t.end(); }); process.on('exit', () => { observed.fail('EXIT_TIME_FAILURE'); });
