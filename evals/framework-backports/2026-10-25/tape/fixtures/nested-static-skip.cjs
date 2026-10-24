const test=require('tape');test('outer',t=>{test.skip('nested static skipped',st=>{st.fail('not executed');st.end()});t.pass('normal');t.end()});
