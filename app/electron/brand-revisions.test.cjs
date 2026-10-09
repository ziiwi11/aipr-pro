const test=require('node:test'),assert=require('node:assert/strict'),{withBrandRevision}=require('./brand-revisions.cjs');
test('brand rules retain version evidence while unchanged saves and unrelated settings do not create revisions',()=>{
 const task={id:'task',collectionStrategy:{brief:'旧简报',criteria:'宽松',exclusions:[],maximumFollowers:0}};
 const first=withBrandRevision(task,task,'2026-01-01');assert.equal(first.brandRevisions.length,1);
 const same=withBrandRevision(first,{...first,shops:{A:{label:'店铺备注'}}});assert.equal(same.brandRevisions.length,1);
 const next=withBrandRevision(first,{...first,collectionStrategy:{...first.collectionStrategy,criteria:'新增适配说明'}});assert.equal(next.brandRevisions.length,2);assert.equal(first.brandRevisions[0].config.criteria,'宽松');assert.equal(next.collectionStrategy.maximumFollowers,0);assert.equal(next.brandRevisions[1].config.criteria,'新增适配说明');
});
