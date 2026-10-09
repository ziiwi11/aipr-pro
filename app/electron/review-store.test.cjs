const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {ReviewStore}=require('./review-store.cjs');
test('review notes retain history across restart without granting admission',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qianxun-review-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));const store=new ReviewStore(dir);
 store.save('brand-2',{creatorId:'a',note:'待补近期作品',disposition:'needs_evidence',admissionChanged:true});
 store.save('brand-2',{creatorId:'a',note:'已核对文字证据',disposition:'reviewed_note'});
 const rows=new ReviewStore(dir).read('brand-2').records;assert.equal(rows.length,2);assert.equal(rows[1].revision,2);assert.equal(rows[0].admissionChanged,false);
 assert.throws(()=>store.save('brand-2',{creatorId:'a',note:'强行通过',disposition:'approved'}),/方式无效/);
 assert.throws(()=>store.read('../escape'),/标识无效/);
});
