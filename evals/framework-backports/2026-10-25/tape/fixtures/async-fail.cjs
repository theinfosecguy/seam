const test=require('tape');test('async failure',t=>{setTimeout(()=>{t.fail('ASYNC_FAILURE_MARKER');t.end()},25)});
