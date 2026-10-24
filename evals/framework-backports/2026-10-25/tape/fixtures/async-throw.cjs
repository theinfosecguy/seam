const test=require('tape');test('async throw',t=>{setTimeout(()=>{throw Error('ASYNC_THROW_MARKER')},25)});
