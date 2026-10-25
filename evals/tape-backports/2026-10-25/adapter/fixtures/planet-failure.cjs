const tape = require('tape'); tape('ordinary failure', t => { t.fail('planet should be blue'); t.end(); });
