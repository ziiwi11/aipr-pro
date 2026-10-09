const test=require('node:test');
const assert=require('node:assert/strict');
const {savedStartStrategy,mergeRuntimeCollectionStrategy}=require('./collection-strategy-runtime.cjs');
test('resume uses newly saved keywords rather than stale rendered button snapshot',()=>{
 const old={sourceDiscoveryMode:'keyword_search',keywords:['润唇'],maximumFollowers:0,targetCount:1000};
 const saved={...old,keywords:['润唇','秋冬护唇']};
 const started=mergeRuntimeCollectionStrategy({base:savedStartStrategy({collectionStrategy:saved},old),existing:old});
 assert.deepEqual(started.keywords,['润唇','秋冬护唇']);
 assert.equal(started.maximumFollowers,0);
 assert.equal(started.targetCount,1000);
 assert.deepEqual(savedStartStrategy({},old),old);
});

const fs=require('node:fs');
const vm=require('node:vm');
test('production sanitizer preserves expanded 62-keyword resume through runtime merge',()=>{
 const source=fs.readFileSync(require.resolve('./main.cjs'),'utf8');
 const code=source.slice(source.indexOf('function sanitizeCollectionStrategy('),source.indexOf('function portableBundle('));
 const sanitize=vm.runInNewContext(code+';sanitizeCollectionStrategy');
 const old={keywords:Array.from({length:42},(_,i)=>`原词${i}`),maximumFollowers:0,targetCount:1000};
 const saved={...old,keywords:[...old.keywords,...Array.from({length:20},(_,i)=>`新词${i}`)]};
 const base=sanitize(savedStartStrategy({collectionStrategy:saved},old));
 assert.equal(base.keywords.length,62);
 const result=mergeRuntimeCollectionStrategy({base,existing:old});
 assert.equal(result.keywords.length,62);
 assert.equal(result.maximumFollowers,0);
 assert.ok(result.keywords.includes('新词19'));
});
test('portable rules preserve explicit small task target over stale strategy default',()=>{
 const source=fs.readFileSync(require.resolve('./main.cjs'),'utf8');
 const code=source.slice(source.indexOf('function sanitizeCollectionStrategy('),source.indexOf('function appPaths('));
 const bundle=vm.runInNewContext(code+';portableBundle')({id:'test',name:'test',targetCount:2,collectionStrategy:{targetCount:500,maximumFollowers:0}});
 assert.equal(bundle.task.targetCount,2);
 assert.equal(bundle.task.collectionStrategy.targetCount,2);
 assert.equal(bundle.task.collectionStrategy.maximumFollowers,0);
});
