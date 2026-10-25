const tape = require('tape'); try { tape.skip('unobserved skip', t => t.end()); } catch (_) {} tape('observed', t => { t.pass('normal'); t.end(); });
