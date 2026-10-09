const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createBackup,restoreBackup,validateBackup}=require('./data-backup.cjs');
test('backup storage failures give actionable messages while retaining diagnostic cause',()=>{
 const {backupWriteError}=require('./data-backup.cjs');
 for(const [code,expected] of [['EPERM',/没有写入权限/],['EACCES',/没有写入权限/],['EROFS',/只读/],['ENOSPC',/空间不足/],['EDQUOT',/额度不足/]]){
  const cause=Object.assign(new Error('internal path'),{code}),error=backupWriteError(cause);
  assert.match(error.message,expected);assert.equal(error.cause,cause);assert.ok(!error.message.includes('internal path'));
 }
 const unknown=new Error('已知业务错误');assert.equal(backupWriteError(unknown),unknown);
});
test('failed backup destination cannot overwrite an existing file or alter the source',async t=>{
 const dir=fixture(t),source=path.join(dir,'source'),target=path.join(dir,'occupied');fs.mkdirSync(source);fs.writeFileSync(path.join(source,'a'),'original');fs.writeFileSync(target,'keep');
 await assert.rejects(()=>createBackup([{key:'brand-tasks',source}],target),/目录已存在/);
 assert.equal(fs.readFileSync(target,'utf8'),'keep');assert.equal(fs.readFileSync(path.join(source,'a'),'utf8'),'original');
});
function fixture(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qianxun-backup-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));return dir;}
test('wrong backup directory and damaged manifest explain recovery action without creating destination',async t=>{
 const dir=fixture(t),source=path.join(dir,'wrong'),target=path.join(dir,'restored');fs.mkdirSync(source);
 await assert.rejects(()=>restoreBackup(source,target),/请选择包含 manifest.json/);assert.ok(!fs.existsSync(target));
 fs.writeFileSync(path.join(source,'manifest.json'),'{broken');
 await assert.rejects(()=>restoreBackup(source,target),/备份清单损坏/);assert.ok(!fs.existsSync(target));
});
test('backup restores independent copies of 600 legacy and 584 current records, without touching originals',async t=>{
 const dir=fixture(t),source=path.join(dir,'source');fs.mkdirSync(source);fs.writeFileSync(path.join(source,'legacy.json'),JSON.stringify({rows:Array.from({length:600},(_,id)=>({id}))}));fs.writeFileSync(path.join(source,'current.json'),JSON.stringify({rows:Array.from({length:584},(_,id)=>({id}))}));
 const backup=path.join(dir,'backup'),target=path.join(dir,'restored');await createBackup([{key:'brand-tasks',source}],backup);await restoreBackup(backup,target);
 assert.equal(JSON.parse(fs.readFileSync(path.join(target,'brand-tasks','legacy.json'))).rows.length,600);assert.equal(JSON.parse(fs.readFileSync(path.join(target,'brand-tasks','current.json'))).rows.length,584);
 assert.ok(fs.existsSync(path.join(source,'current.json')));assert.equal((await validateBackup(backup)).files.length,2);
 fs.writeFileSync(path.join(backup,'files','brand-tasks','legacy.json'),'tampered');await assert.rejects(()=>restoreBackup(backup,path.join(dir,'bad')),/校验失败/);assert.ok(!fs.existsSync(path.join(dir,'bad')));
});
test('backup rejects recursive destinations, path traversal and out-of-root symlinks',async t=>{
 const dir=fixture(t),source=path.join(dir,'source');fs.mkdirSync(source);fs.writeFileSync(path.join(source,'a.txt'),'a');
 await assert.rejects(()=>createBackup([{key:'brand-tasks',source}],path.join(source,'nested')),/源数据/);
 const backup=path.join(dir,'backup');await createBackup([{key:'brand-tasks',source}],backup);
 const file=path.join(backup,'manifest.json'),manifest=JSON.parse(fs.readFileSync(file));manifest.files[0].path='../../secret';fs.writeFileSync(file,JSON.stringify(manifest));await assert.rejects(()=>validateBackup(backup),/不安全路径/);
 fs.symlinkSync(path.join(dir,'backup'),path.join(source,'link'));await assert.rejects(()=>createBackup([{key:'brand-tasks',source}],path.join(dir,'backup2')),/符号链接/);
});
test('business backups exclude software bundles and build dependencies with declared omissions while preserving data and rejecting other links',async t=>{
 const dir=fixture(t),source=path.join(dir,'source');fs.mkdirSync(source);fs.mkdirSync(path.join(source,'task'));fs.writeFileSync(path.join(source,'task','contact.json'),'saved-data');fs.writeFileSync(path.join(source,'task','work.png'),'saved-evidence');
 fs.mkdirSync(path.join(source,'验收.app'));fs.symlinkSync('/outside-runtime',path.join(source,'验收.app','python'));fs.symlinkSync('/outside-node_modules',path.join(source,'node_modules'));
 const backup=path.join(dir,'backup'),result=await createBackup([{key:'brand-tasks',source}],backup);assert.equal(result.files,2);const manifest=await validateBackup(backup);assert.equal(manifest.skipped.length,2);assert.ok(manifest.skipped.every(x=>x.reason&&x.root==='brand-tasks'));assert.ok(manifest.files.some(x=>x.path==='task/work.png'));assert.ok(!manifest.files.some(x=>/node_modules|app/.test(x.path)));
 const target=path.join(dir,'restored');await restoreBackup(backup,target);assert.equal(fs.readFileSync(path.join(target,'brand-tasks','task','contact.json'),'utf8'),'saved-data');assert.ok(!fs.existsSync(path.join(target,'brand-tasks','验收.app')));
 fs.symlinkSync('/outside-data',path.join(source,'task','evidence-link'));await assert.rejects(()=>createBackup([{key:'brand-tasks',source}],path.join(dir,'unsafe-backup')),/符号链接/);
});
