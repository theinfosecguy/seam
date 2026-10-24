const test=require('tape');test('whole skipped',{skip:true},t=>{t.fail('not executed');t.end()});test('normal',t=>{t.pass('normal');t.end()});
