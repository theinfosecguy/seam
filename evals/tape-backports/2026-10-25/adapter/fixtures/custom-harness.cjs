const test=require('tape');
const h=test.createHarness();
h('unobserved failure',t=>{t.fail('CUSTOM_HARNESS_FAILURE');t.end()});
h.createStream().resume();
test('observed normal',t=>{t.pass('normal');t.end()});
