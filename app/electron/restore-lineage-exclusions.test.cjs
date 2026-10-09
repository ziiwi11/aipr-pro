const test=require('node:test'),assert=require('node:assert/strict');
const {deliveryExclusionTasks}=require('./delivery-exclusions.cjs');
const {mergeRuntimeCollectionStrategy}=require('./collection-strategy-runtime.cjs');
test('restored current task is not treated as a foreign delivery; original foreign task wins',()=>{
 const tasks=[{id:'current',outputDir:'/tasks/current'},{id:'current-restored',outputDir:'/恢复-123/brand-tasks/current'},{id:'old',outputDir:'/tasks/old'},{id:'old-restored',outputDir:'/恢复-123/brand-tasks/old'}];
 assert.deepEqual(deliveryExclusionTasks(tasks,'current').map(t=>t.id),['old']);
 assert.deepEqual(deliveryExclusionTasks(tasks,'current-restored').map(t=>t.id),['old']);
});
test('cleans only self-contamination in delivery exclusion scope, preserving discovery and real foreign overlap',()=>{
 const merged=mergeRuntimeCollectionStrategy({base:{},existing:{excludeIdentities:['self','foreign'],deliveryExcludeIdentities:['self','foreign'],excludeContacts:['wx_self','wx_both','wx_foreign']},deliveredContacts:['wx_both','wx_foreign'],deliveredIdentities:['foreign'],ownDeliveredContacts:['wx_self','wx_both'],ownDeliveredIdentities:['self']});
 assert.deepEqual(merged.excludeContacts,['wx_both','wx_foreign']);assert.deepEqual(merged.deliveryExcludeIdentities,['foreign']);assert.ok(merged.excludeIdentities.includes('self'));
});
