const tape = require('tape'); process.stdout.write('this is ordinary application stdout\n'); tape('observed', t => { t.pass('normal'); t.end(); });
