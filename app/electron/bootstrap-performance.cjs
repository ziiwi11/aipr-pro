const {performance}=require('node:perf_hooks');
function createBootstrapPerformance(clock=()=>performance.now()){
 const samples=[];let failed=0;
 return {
  measure(fn){const start=clock();try{const value=fn();samples.push({ms:Math.max(0,clock()-start),candidates:value.candidateCreators?.length||0,formal:value.creators?.length||0,library:value.creatorLibrary?.creators?.length||0});if(samples.length>100)samples.shift();return value;}catch(error){failed++;throw error;}},
  summary(){const values=samples.map(s=>s.ms).sort((a,b)=>a-b);return {scope:'本机完整数据汇总读取（不含界面绘制、云端和采集）',sampleCount:values.length,failedCount:failed,meanMs:values.length?Number((values.reduce((a,b)=>a+b,0)/values.length).toFixed(2)):null,p95Ms:values.length?Number(values[Math.ceil(values.length*.95)-1].toFixed(2)):null,maxMs:values.length?Number(values.at(-1).toFixed(2)):null,lastDimensions:samples.at(-1)?{candidates:samples.at(-1).candidates,formal:samples.at(-1).formal,library:samples.at(-1).library}:null};}
 };
}
module.exports={createBootstrapPerformance};
