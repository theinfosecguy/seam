const path=require('node:path');
const test=require('tape');
const entry=require.resolve('tape');
for(const id of Object.keys(require.cache)){
 if(id.startsWith(path.dirname(entry)+path.sep))delete require.cache[id];
}
const other=require('tape');
other('unobserved secondary scope',t=>{t.pass('unobserved');t.end()});
test('observed normal',t=>{t.pass('normal');t.end()});
