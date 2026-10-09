const test=require('node:test'),assert=require('node:assert/strict');
const {createBootstrapPerformance}=require('./bootstrap-performance.cjs');
test('whole bootstrap timing retains dimensions and failures without storing contacts',()=>{
 let now=0;const meter=createBootstrapPerformance(()=>now);const data={candidateCreators:Array(3059),creators:Array(584),creatorLibrary:{creators:Array(1184)}};
 for(let i=1;i<=20;i++)assert.equal(meter.measure(()=>{now+=i;return data;}),data);
 assert.throws(()=>meter.measure(()=>{throw Error('bad');}),/bad/);
 const report=meter.summary();assert.equal(report.sampleCount,20);assert.equal(report.meanMs,10.5);assert.equal(report.p95Ms,19);assert.equal(report.failedCount,1);assert.deepEqual(report.lastDimensions,{candidates:3059,formal:584,library:1184});assert.equal(JSON.stringify(report).includes('phone'),false);
});
