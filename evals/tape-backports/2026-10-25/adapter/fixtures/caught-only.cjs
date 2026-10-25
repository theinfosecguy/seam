const tape = require('tape'); try { tape.only('focused', t => { t.pass('focused'); t.end(); }); } catch (_) {} tape('observed', t => { t.pass('normal'); t.end(); });
