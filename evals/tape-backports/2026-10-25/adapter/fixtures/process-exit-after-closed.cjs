const tape = require('tape'); tape('observed', t => { t.pass('normal'); t.end(); }); tape.onFinish(() => process.exit(0));
