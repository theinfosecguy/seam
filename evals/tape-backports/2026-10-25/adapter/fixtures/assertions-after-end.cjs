const tape = require('tape'); tape('late failure', t => { t.pass('normal'); t.end(); setTimeout(() => t.fail('LATE_FAILURE'), 5); });
