const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {summarizeUsage} = require('./jev-usage.cjs');
function fixture(t) { const dir=fs.mkdtempSync(path.join(os.tmpdir(),'jev-usage-')); t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));return dir; }
test('no ledger means unknown historical usage and balance, not zero cost', t=>{
 const result=summarizeUsage(fixture(t)); assert.equal(result.calls,0);assert.equal(result.inputTokens,null);assert.equal(result.balance,null);assert.equal(result.billedAmount,null);
});
test('summarizes only this app; missing and corrupt records cannot invent usage or credentials', t=>{
 const dir=fixture(t);
 const rows=[{app:'other',recorded_at:'2026-10-08',usage:{input_tokens:999}}, {app:'aipr-pro',recorded_at:'2026-10-08T02:00:00Z',model:'jev-1.13.0',usage:{input_tokens:120,output_tokens:0,total_tokens:120},api_key:'secret'}, {app:'aipr-pro',recorded_at:'2026-10-08T01:00:00Z',usage:{input_tokens:true,output_tokens:-1}}, {app:'aipr-pro',recorded_at:'2026-10-08T03:00:00Z',usage:{prompt_tokens:30,completion_tokens:4}}];
 fs.writeFileSync(path.join(dir,'usage-ledger.ndjson'),rows.map(JSON.stringify).join('\n')+'\n{broken');
 const r=summarizeUsage(dir);assert.equal(r.calls,3);assert.equal(r.inputTokens,150);assert.equal(r.outputTokens,4);assert.equal(r.inputCoverage,2);assert.equal(r.invalidRows,1);assert.equal(r.lastAt,'2026-10-08T03:00:00.000Z');assert.equal(JSON.stringify(r).includes('secret'),false);
});
test('failed retries and Beijing dates remain distinct from successful billed-token evidence', t=>{
 const dir=fixture(t);
 const rows=[{app:'aipr-pro',recorded_at:'2026-10-07T16:00:00Z',task_id:'brand-task-2',outcome:'http_error',http_status:503,attempt:1,elapsed_ms:100}, {app:'aipr-pro',recorded_at:'2026-10-07T16:00:03Z',task_id:'brand-task-2',outcome:'success',attempt:2,elapsed_ms:300,model:'jev-latest',usage:{input_tokens:10,output_tokens:2}}];
 fs.writeFileSync(path.join(dir,'usage-ledger.ndjson'),rows.map(JSON.stringify).join('\n'));
 fs.writeFileSync(path.join(dir,'account-status.json'),JSON.stringify({recorded_at:'2026-10-08T01:00:00Z',outcome:'http_error',http_status:402,api_key:'secret'}));
 const r=summarizeUsage(dir);assert.equal(r.calls,1);assert.equal(r.attempts,2);assert.equal(r.failures,1);assert.equal(r.retries,1);assert.equal(r.byDate['2026-10-08'].calls,1);assert.equal(r.byTask['brand-task-2'].inputTokens,10);assert.equal(r.averageLatencyMs,200);assert.equal(r.accountStatus.httpStatus,402);assert.ok(!JSON.stringify(r).includes('secret'));
});
test('cached aggregates are isolated and invalidate when ledger or write-error marker changes', t=>{
 const dir=fixture(t);const file=path.join(dir,'usage-ledger.ndjson');
 fs.writeFileSync(file,JSON.stringify({app:'aipr-pro',recorded_at:'2026-10-08',task_id:'__proto__'})+'\n');
 const a=summarizeUsage(dir);a.calls=99;assert.equal(summarizeUsage(dir).calls,1);
 assert.equal(summarizeUsage(dir).byTask['__proto__'].calls,1);assert.equal({}.calls,undefined);
 fs.writeFileSync(path.join(dir,'usage-ledger-error.json'),'{}');assert.equal(summarizeUsage(dir).writeError,true);
 fs.appendFileSync(file,JSON.stringify({app:'aipr-pro',recorded_at:'2026-10-08'})+'\n');assert.equal(summarizeUsage(dir).calls,2);
});
