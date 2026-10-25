const tape = require('tape'); tape('observed', t => { t.pass('normal'); t.end(); setTimeout(() => t.fail('HIDDEN_LATE_FAILURE'), 50); setTimeout(() => process.exit(0), 5); });
