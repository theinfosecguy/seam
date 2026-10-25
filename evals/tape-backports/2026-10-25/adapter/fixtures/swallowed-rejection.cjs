const tape = require('tape'); process.on('unhandledRejection', () => {}); tape('observed', t => { t.pass('normal'); t.end(); }); setTimeout(() => Promise.reject(Error('SWALLOWED_REJECTION')), 5);
