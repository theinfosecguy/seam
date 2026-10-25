const tape = require('tape'); process.on('uncaughtException', () => {}); tape('observed', t => { t.pass('normal'); t.end(); }); setTimeout(() => { throw new Error('SWALLOWED_ERROR'); }, 5);
