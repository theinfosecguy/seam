const test=require('tape');test('late assertion',t=>{t.pass('first');t.end();setTimeout(()=>t.fail('LATE_ASSERTION_MARKER'),25)});
