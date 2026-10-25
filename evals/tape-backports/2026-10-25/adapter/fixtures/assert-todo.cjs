const tape = require('tape'); tape('has todo', t => { t.pass('normal'); t.fail('pending', { todo: true }); t.end(); });
