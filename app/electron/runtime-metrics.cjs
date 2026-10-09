const COLLECTION=new Set(['collect-creators','contact-icons']);
function summarizeRuntime(events,now=Date.now(),liveSession='',currentFormal){
 const starts=events.filter(e=>e.type==='worker-started'&&e.timingVersion===1&&COLLECTION.has(e.workerAction)).sort((a,b)=>Date.parse(a.recordedAt)-Date.parse(b.recordedAt)).slice(-1);
 if(!starts.length)return {available:false,scope:'尚无完整作业计时记录；历史进程存活时间不能视为有效作业时间'};
 let elapsedMs=0,cooldownMs=0,effectiveMs=0,unknownMs=0,newCreators=0,interruptions=0,incompleteRuns=0;
 for(const start of starts){
  const rows=events.filter(e=>e.workerSession===start.workerSession).sort((a,b)=>Date.parse(a.recordedAt)-Date.parse(b.recordedAt));
  const began=Date.parse(start.recordedAt),terminal=rows.find(e=>e.type==='finished'||e.type==='worker-stopped');
  if(!terminal && start.workerSession!==liveSession)incompleteRuns++;
  const end=terminal?Date.parse(terminal.recordedAt):start.workerSession===liveSession?now:Date.parse(rows.at(-1)?.recordedAt||start.recordedAt);
  if(!Number.isFinite(began)||!Number.isFinite(end)||end<began)continue;
  elapsedMs+=end-began;let last=began,coolingUntil=began,high=Number(start.listedBaseline)||0;
  for(const row of rows){
   const at=Math.min(end,Date.parse(row.recordedAt));if(!Number.isFinite(at)||at<last)continue;
   const cooling=Math.max(0,Math.min(at,coolingUntil)-last);cooldownMs+=cooling;
   const remainder=at-last-cooling;
   const meaningful=row.type==='progress'&&/progress|processed|checkpoint_saved|filters_applied/.test(String(row.status));
   if(meaningful && remainder<=60000)effectiveMs+=remainder;else unknownMs+=remainder;
   if(row.status==='collection_retry_scheduled')coolingUntil=Math.max(coolingUntil,at+Math.max(0,Number(row.wait_ms??row.backoff_ms)||0));
   high=Math.max(high,Number(row.listed_count??row.qualified_plain_contact_count)||0);last=at;
  }
  const cooling=Math.max(0,Math.min(end,coolingUntil)-last);cooldownMs+=cooling;unknownMs+=Math.max(0,end-last-cooling);
  if(start.workerSession===liveSession && Number.isFinite(currentFormal))high=currentFormal;
  newCreators+=Math.max(0,high-(Number(start.listedBaseline)||0));
  if(terminal&&(terminal.type==='worker-stopped'||terminal.code!==0))interruptions++;
 }
 return {available:true,runs:starts.length,elapsedMs,cooldownMs,effectiveMs,unknownMs,newCreators,interruptions,incompleteRuns,netPerHour:incompleteRuns===0&&unknownMs===0&&effectiveMs>0?newCreators*3600000/effectiveMs:null,scope:'仅统计最近一次显式启动的采集作业；60秒以上无进展或无法判定的间隔计入未证实，不计有效吞吐'};
}
function collectionBaseline({liveFormal=0,savedFormal=0,deliveredFormal=0}={}) {
 // A preserved delivery is already-owned data, even if a stale live audit
 // temporarily excluded it. Restoring it is never a new creator.
 return Math.max(...[liveFormal,savedFormal,deliveredFormal].map(value=>{
  const number=Number(value);return Number.isFinite(number)?Math.max(0,Math.floor(number)):0;
 }));
}
module.exports={summarizeRuntime,collectionBaseline};
