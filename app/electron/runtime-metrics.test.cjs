const test=require('node:test'),assert=require('node:assert/strict'),{summarizeRuntime}=require('./runtime-metrics.cjs');
const e=(seconds,fields)=>({recordedAt:new Date(seconds*1000).toISOString(),workerSession:'one',...fields});
test('runtime distinguishes platform cooling, observed progress, unresolved time and net additions',()=>{
 const rows=[e(0,{type:'worker-started',timingVersion:1,workerAction:'collect-creators',listedBaseline:500}),e(30,{type:'progress',status:'realtime_creator_progress',listed_count:501}),e(30,{type:'progress',status:'collection_retry_scheduled',wait_ms:120000}),e(150,{type:'progress',status:'collection_checkpoint_saved',listed_count:501}),e(180,{type:'progress',status:'realtime_creator_progress',listed_count:502}),e(180,{type:'finished',code:0})];
 const m=summarizeRuntime(rows);assert.equal(m.elapsedMs,180000);assert.equal(m.cooldownMs,120000);assert.equal(m.effectiveMs,60000);assert.equal(m.unknownMs,0);assert.equal(m.newCreators,2);assert.equal(m.netPerHour,120);
 const missing=summarizeRuntime([...rows.slice(0,-1),e(400,{type:'worker-stopped'})]);assert.equal(missing.netPerHour,null);assert.equal(missing.interruptions,1);assert(missing.unknownMs>0);
});
test('legacy history and login jobs cannot be counted as measured collection time',()=>{
 assert.equal(summarizeRuntime([e(0,{type:'finished',code:0})]).available,false);
 assert.equal(summarizeRuntime([e(0,{type:'worker-started',timingVersion:1,workerAction:'probe-login'})]).available,false);
});
test('restart does not count restored historical creators again; live formal count includes email contacts',()=>{
 const old=[e(0,{type:'worker-started',timingVersion:1,workerAction:'collect-creators',listedBaseline:4}),e(30,{type:'progress',status:'realtime_creator_progress',listed_count:584}),e(30,{type:'finished',code:0})];
 const fresh=[{...e(60,{type:'worker-started',timingVersion:1,workerAction:'collect-creators',listedBaseline:612}),workerSession:'two'},{...e(90,{type:'progress',status:'realtime_creator_progress',listed_count:614}),workerSession:'two'}];
 const result=summarizeRuntime([...old,...fresh],90000,'two',618);
 assert.equal(result.runs,1);assert.equal(result.newCreators,6);assert.equal(result.elapsedMs,30000);
});

const {collectionBaseline}=require('./runtime-metrics.cjs');
test('restored delivered creator is not counted as a net addition',()=>{
 const baseline=collectionBaseline({liveFormal:639,savedFormal:639,deliveredFormal:640});
 const start=e(0,{type:'worker-started',timingVersion:1,workerAction:'collect-creators',listedBaseline:baseline});
 const recovered=e(30,{type:'progress',status:'realtime_creator_progress',listed_count:640});
 assert.equal(summarizeRuntime([start,recovered],30000,'one',640).newCreators,0);
 const fresh=e(60,{type:'progress',status:'realtime_creator_progress',listed_count:641});
 assert.equal(summarizeRuntime([start,recovered,fresh],60000,'one',641).newCreators,1);
});
test('baseline keeps live additions and ignores invalid legacy counters',()=>{
 assert.equal(collectionBaseline({liveFormal:643,savedFormal:641,deliveredFormal:640}),643);
 assert.equal(collectionBaseline({liveFormal:NaN,savedFormal:-1,deliveredFormal:undefined}),0);
});
