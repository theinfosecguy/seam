const test=require('tape');test('outer',t=>{t.test('nested skipped',{skip:true},st=>{st.fail('not executed');st.end()});t.test('normal child',st=>{st.pass('normal');st.end()});t.end()});
