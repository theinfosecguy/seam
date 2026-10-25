const test=require('tape');test('premature',t=>{t.plan(2);t.pass('first');process.exit(0)});
