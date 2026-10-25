const test=require('tape');
test('outer alpha',t=>{t.equal(1,1,'same assertion');t.test('nested one',st=>{st.equal(2,2,'same assertion');st.end()});t.end()});
test('outer beta',t=>{t.equal(3,3,'same assertion');t.end()});
