const { test } = require('node:test');
const assert = require('node:assert/strict');
const { buildCreatorLibrary } = require('./creator-library.cjs');
test('library combines deliveries and retains batch membership while merging repeated identities', () => {
 const tasks=[{id:'a',name:'第一批',deliveryPath:'a'},{id:'b',name:'第二批',deliveryPath:'b'},{id:'empty',deliveryPath:''}];
 const data={a:{creators:[{id:'one',douyinId:'creator1',phone:'13800138000'}]},b:{creators:[{id:'one',douyinId:'creator1',wechat:'creator_wx'},{id:'two',douyinId:'creator2'}]}};
 const out=buildCreatorLibrary(tasks,p=>data[p]);
 assert.equal(out.creators.length,2);
 assert.deepEqual(out.creators[0].libraryTaskIds,['a','b']);
 assert.equal(out.creators[0].phone,'13800138000');
 assert.equal(out.creators[0].wechat,'creator_wx');
 assert.equal(out.batches.length,2);
});
test('live formal list replaces stale delivery while retaining other batches and deduplicating identities',()=>{
 const tasks=[{id:'a',name:'本批',deliveryPath:'old'},{id:'b',name:'旧批',deliveryPath:'b'}];
 const out=buildCreatorLibrary(tasks,p=>({creators:p==='old'?[{douyinId:'old'}]:[{douyinId:'history'}]}),t=>t.id==='a'?[{douyinId:'live'},{douyinId:'history'}]:null);
 assert.equal(out.creators.length,2);assert.equal(out.creators.some(r=>r.douyinId==='old'),false);assert.equal(out.batches[0].count,2);assert.deepEqual(out.creators.find(r=>r.douyinId==='history').libraryTaskIds,['a','b']);
});
test('restore copies do not add obsolete identities when original batch still exists',()=>{
 const tasks=[{id:'a',name:'原批',outputDir:'/brand-tasks/a',deliveryPath:'a'},{id:'a-restored',name:'恢复',outputDir:'/root/恢复-123/brand-tasks/a',deliveryPath:'stale'}];
 const out=buildCreatorLibrary(tasks,p=>({creators:p==='a'?[{douyinId:'one'}]:[{douyinId:'one'},{douyinId:'obsolete'}]}));
 assert.equal(out.creators.length,1);assert.equal(out.batches.length,1);
 const fallback=buildCreatorLibrary(tasks.slice(1),p=>({creators:[{douyinId:'retained'}]}));assert.equal(fallback.creators.length,1);
});
