const test=require('tape');test.only('focused',t=>{t.pass('one observed');t.end()});test('other',t=>{t.fail('must not run');t.end()});
