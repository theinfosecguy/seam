const tape = require('tape'); tape('observed', t => { t.pass('normal'); t.end(); }); process.on('beforeExit', () => { process.exitCode = 1; });
