const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {ContactCorrectionStore}=require('./contact-corrections.cjs');
test('contact correction keeps auditable history, digit WeChat and dedup across channels',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qianxun-contact-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));const store=new ContactCorrectionStore(dir),rows=[{id:'a',wechat:'old_wx',phone:'',contactAcquiredAt:'2026-10-01T00:00:00Z'},{id:'b',phone:'13800138000'}];
 const payload={creatorId:'a',wechat:'1234567890',phone:'',email:'',source:'本地合成证据',reason:'测试微信渠道人工修订'};
 store.save('test',payload,rows);const applied=new ContactCorrectionStore(dir).apply('test',rows);assert.equal(applied[0].wechat,'1234567890');assert.equal(applied[0].contactAcquiredAt,'2026-10-01T00:00:00Z');assert.ok(applied[0].contactCorrectedAt);assert.notEqual(applied[0].contactCorrectedAt,applied[0].contactAcquiredAt);assert.equal(rows[0].wechat,'old_wx');assert.equal(applied[0].contactVerification,'尚未验证可达性');
 assert.throws(()=>store.save('test',{...payload,wechat:'13800138000'},rows),/重复/);
 assert.throws(()=>store.save('test',{...payload,wechat:'***'},rows),/格式无效/);
 assert.throws(()=>store.save('test',{...payload,wechat:''},rows),/至少保留/);
 store.save('test',{...payload,wechat:'old_wx',reason:'恢复原合成测试值'},rows);const history=store.read('test').records;assert.equal(history[1].revision,2);assert.equal(history[1].before.wechat,'1234567890');assert.equal(history[0].admissionChanged,false);assert.equal(store.apply('test',rows)[0].wechat,'old_wx');assert.throws(()=>store.read('../bad'),/标识无效/);
});
test('backup correction restores to a new task while retaining old source',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qianxun-contact-restore-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));const store=new ContactCorrectionStore(dir),rows=[{id:'a',wechat:'wx_original'}];
 store.save('original',{creatorId:'a',wechat:'wx_changed',phone:'',email:'',source:'合成证据',reason:'合成变更'},rows);const old=fs.readFileSync(store.file('original'),'utf8');store.restore(store.file('original'),'original','restored');assert.equal(store.read('restored').taskId,'restored');assert.equal(store.apply('restored',rows)[0].wechat,'wx_changed');assert.equal(fs.readFileSync(store.file('original'),'utf8'),old);
});
test('encrypted identity rotation with the same public identity is not another creator, but name or contact alone never proves identity',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qianxun-rotated-contact-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));const store=new ContactCorrectionStore(dir);
 const current={id:'encrypted-current',douyinId:'same-public-account',nickname:'昵称',wechat:'13800000000',phone:''};
 const alias={id:'encrypted-history',douyinId:'same-public-account',nickname:'昵称',wechat:'A13800000000',phone:''};
 const payload={creatorId:current.id,wechat:'A13800000000',phone:'',email:'',source:'合成平台标签证据',reason:'恢复同人原始完整微信'};
 store.save('test',payload,[current],[alias]);assert.equal(store.apply('test',[current])[0].wechat,payload.wechat);assert.equal(alias.wechat,payload.wechat);
 const stranger={...alias,id:'other',douyinId:'different-public-account'};
 assert.throws(()=>store.save('other-task',payload,[current],[stranger]),/重复/);assert.equal(store.read('other-task').records.length,0);
});
test('trusted current identity resolves historical alias display without changing its identity or old source',()=>{
 const {applyContactCorrections,sameIdentity}=require('./contact-corrections.cjs');
 const current={id:'current',douyinId:'public-same',wechat:'old'},history={id:'old-encrypted',douyinId:'public-same',wechat:'old'};
 const record={creatorId:'current',after:{wechat:'updated',phone:'',email:''},revision:1,source:'合成证据',recordedAt:'2026-10-01'};
 const applied=applyContactCorrections([history],[record],[current]);assert.equal(applied[0].wechat,'updated');assert.equal(applied[0].id,history.id);assert.equal(applied[0].contactCorrectionCreatorId,'current');assert.equal(history.wechat,'old');
 const stranger={id:'stranger',douyinId:'other-public',nickname:'same',wechat:'old'};assert.equal(applyContactCorrections([stranger],[record],[current])[0].wechat,'old');
 assert.equal(sameIdentity({id:'foo'},{douyinId:'foo'}),false);assert.equal(applyContactCorrections([history],[record],[])[0].wechat,'old');
});
test('indexed owner resolution accepts one saved strong identity and refuses ambiguous or cross-field matches',()=>{
 const {createIdentityResolver}=require('./contact-corrections.cjs'),owner={id:'one',douyinId:'public-one'},other={id:'two',douyinId:'public-two'};
 const resolve=createIdentityResolver([owner,other]);assert.equal(resolve({id:'rotated',douyinId:'public-one'}),owner);assert.equal(resolve({id:'public-one'}),undefined);assert.equal(resolve({id:'one',douyinId:'public-two'}),undefined);assert.equal(resolve({nickname:'public-one',wechat:'public-one'}),undefined);
});
test('a newer canonical revision wins over an older exact encrypted-alias revision',()=>{
 const {applyContactCorrections}=require('./contact-corrections.cjs'),canonical={id:'new-id',douyinId:'public-person'},alias={id:'old-id',douyinId:'public-person'};
 const records=[{creatorId:'old-id',after:{wechat:'older',phone:'',email:''},revision:1,recordedAt:'2026-10-08',source:'旧证据'},{creatorId:'new-id',after:{wechat:'newer',phone:'',email:''},revision:1,recordedAt:'2026-10-09',source:'新证据'}];
 const row=applyContactCorrections([alias],records,[canonical])[0];assert.equal(row.wechat,'newer');assert.equal(row.contactCorrectedAt,'2026-10-09');assert.equal(row.contactCorrectionCreatorId,'new-id');assert.equal(alias.wechat,undefined);
});
