const tape = require('tape');
const fields = ['type','id','name','skip','todo','parent','test','ok','operator','file','line','column','at'];
const stream=tape.createStream({objectMode:true});
stream.on('data',row=>{
 if(typeof row==='string'){process.stdout.write(JSON.stringify(row)+'\n');return;}
 const normalized={};
 for(const field of fields){
  if(Object.hasOwn(row,field))normalized[field]=row[field];
 }
 process.stdout.write(JSON.stringify(normalized)+'\n');
});
stream.on('end',()=>process.stdout.write(JSON.stringify({type:'stream-end'})+'\n'));
require(process.argv[2]);
