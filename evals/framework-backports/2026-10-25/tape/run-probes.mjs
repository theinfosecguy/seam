import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const root=path.dirname(new URL(import.meta.url).pathname);
const digest=value=>createHash('sha256').update(value).digest('hex');
const outcomes={};
for(const name of fs.readdirSync(path.join(root,'fixtures')).sort()){
 const result=spawnSync(process.execPath,[path.join(root,'object-events.cjs'),path.join(root,'fixtures',name)],{
  encoding:'utf8',timeout:10000,maxBuffer:2097152,
  env:{...process.env,NODE_TAPE_NO_ONLY_TEST:'true'}
 });
 const events=[];
 let malformed=0;
 for(const line of result.stdout.split('\n').filter(Boolean)){
  try {events.push(JSON.parse(line));}catch {malformed++;}
 }
 const rows=events.filter(row=>row&&typeof row==='object');
 outcomes[name]={
  exit_code:result.status,signal:result.signal,error:result.error?.message,
  scopes:rows.filter(row=>row.type==='test').length,
  assertions:rows.filter(row=>row.type==='assert').length,
  closed_scopes:rows.filter(row=>row.type==='end').length,
  stream_end:rows.filter(row=>row.type==='stream-end').length,
  skipped_or_todo_events:rows.filter(row=>row.skip||row.todo).length,
  failed_assertions:rows.filter(row=>row.type==='assert'&&!row.ok&&!row.skip&&!row.todo).length,
  malformed_output_lines:malformed,
  stdout_sha256:digest(result.stdout),stderr_sha256:digest(result.stderr)
 };
}
process.stdout.write(JSON.stringify(outcomes,null,2)+'\n');
