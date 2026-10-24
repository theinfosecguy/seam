const test=require('tape');test.skip('whole skipped',t=>{t.pass('not executed');t.end()});test('mixed',t=>{t.pass('normal');t.skip('skipped assertion');t.end()});
