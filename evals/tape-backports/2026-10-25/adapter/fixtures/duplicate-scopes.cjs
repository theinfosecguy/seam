const tape = require('tape'); for (let n = 0; n < 2; n += 1) tape('same scope', t => { t.pass('normal'); t.end(); });
