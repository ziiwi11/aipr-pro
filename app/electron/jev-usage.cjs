const fs = require('node:fs');
const path = require('node:path');
const cache = new Map();
const signature = file => {try {const s=fs.statSync(file);return `${s.ino}:${s.size}:${s.mtimeMs}:${s.ctimeMs}`;}catch{return 'missing';}};
const validToken = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
const group = () => ({attempts:0,calls:0,failures:0,retries:0,inputTokens:null,outputTokens:null});
function addGroup(g,row,input,output) {
 g.attempts++;
 if (row.outcome && row.outcome !== 'success') g.failures++; else g.calls++;
 if (row.attempt > 1) g.retries++;
 if (input !== null) g.inputTokens=(g.inputTokens??0)+input;
 if (output !== null) g.outputTokens=(g.outputTokens??0)+output;
}
function summarizeUsage(dir) {
 const ledger=path.join(dir,'usage-ledger.ndjson'), account=path.join(dir,'account-status.json'), errors=path.join(dir,'usage-ledger-error.json');
 const key=[ledger,account,errors].map(signature).join('|');
 if (cache.get(dir)?.key===key) return structuredClone(cache.get(dir).value);
 const result = { calls:0,attempts:0,failures:0,retries:0,averageLatencyMs:null,inputTokens:null,outputTokens:null,inputCoverage:0,outputCoverage:0,firstAt:null,lastAt:null,lastModel:null,invalidRows:0,readError:false,writeError:false,accountStatus:null,byTask:Object.create(null),byDate:Object.create(null),balance:null,billedAmount:null };
 try {const state=JSON.parse(fs.readFileSync(account,'utf8'));if (Number.isFinite(Date.parse(state.recorded_at))) result.accountStatus={recordedAt:new Date(state.recorded_at).toISOString(), outcome:['success','http_error','network_error','invalid_response'].includes(state.outcome)?state.outcome:'unknown',httpStatus:Number.isInteger(state.http_status)&&state.http_status>=100&&state.http_status<=599?state.http_status:null};} catch {}
 result.writeError=fs.existsSync(errors);
 let text='';try{text=fs.readFileSync(ledger,'utf8');}catch(error){result.readError=error.code!=='ENOENT';}
 let latencyTotal=0, latencyCount=0;
 for (const line of text.split(/\r?\n/).filter(x=>x.trim())) {
  let row;try{row=JSON.parse(line);}catch{result.invalidRows++;continue;}
  if (!row||typeof row!=='object'){result.invalidRows++;continue;}
  if (row.app!=='aipr-pro') continue;
  const time=Date.parse(row.recorded_at);if (!Number.isFinite(time)){result.invalidRows++;continue;}
  const at=new Date(time).toISOString();
  const success=!row.outcome||row.outcome==='success';
  result.attempts++;
  if (!success) result.failures++; else result.calls++;
  if (row.attempt>1) result.retries++;
  if (!result.firstAt||at<result.firstAt)result.firstAt=at;
  if (success&&(!result.lastAt||at>=result.lastAt)){result.lastAt=at;result.lastModel=typeof row.model==='string'&&/^jev-[a-z0-9.-]{1,60}$/.test(row.model)?row.model:null;}
  const usage=success?(row.usage||{}):{};
  const input=validToken(usage.input_tokens)??validToken(usage.prompt_tokens),output=validToken(usage.output_tokens)??validToken(usage.completion_tokens);
  if(input!==null){result.inputTokens=(result.inputTokens??0)+input;result.inputCoverage++;}
  if(output!==null){result.outputTokens=(result.outputTokens??0)+output;result.outputCoverage++;}
  if(validToken(row.elapsed_ms)!==null){latencyTotal+=row.elapsed_ms;latencyCount++;}
  const task=typeof row.task_id==='string'&&/^[a-zA-Z0-9_-]{1,120}$/.test(row.task_id)?row.task_id:'未记录任务';
  const day=new Date(time+8*3600000).toISOString().slice(0,10);
  result.byTask[task] ||= group();result.byDate[day] ||= group();addGroup(result.byTask[task],row,input,output);addGroup(result.byDate[day],row,input,output);
 }
 result.averageLatencyMs=latencyCount?Math.round(latencyTotal/latencyCount):null;
 if(cache.size>30)cache.clear();cache.set(dir,{key,value:result});
 return structuredClone(result);
}
module.exports={summarizeUsage};
