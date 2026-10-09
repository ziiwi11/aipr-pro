const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { TaskStore } = require('./task-store.cjs');
function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'aipr-task-recovery-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return new TaskStore(dir);
}
test('restart retains independent tasks and updates', t => {
  const store = fixture(t);
  store.create({ id: 'brand-a', name: 'A', wechat: 12 });
  store.create({ id: 'brand-b', name: 'B', wechat: 34 });
  const restarted = new TaskStore(path.dirname(store.dir));
  assert.equal(restarted.list().length, 2);
  restarted.select('brand-a');
  assert.equal(restarted.current().wechat, 12);
});
test('corrupt primary restores last valid snapshot and retains usable backup', t => {
  const store = fixture(t);
  store.create({ id: 'brand-a', name: 'A' });
  store.upsert({ id: 'brand-a', name: 'updated' });
  fs.writeFileSync(store.file, '{broken');
  assert.equal(store.current().name, 'A');
  store.upsert({ id: 'brand-b', name: 'B' });
  assert.equal(store.list().length, 2);
  fs.writeFileSync(store.file, '{broken again');
  assert.equal(store.current().name, 'A');
});
test('two damaged snapshots fail visibly without discarding files', t => {
  const store = fixture(t);
  fs.writeFileSync(store.file, '{broken');
  fs.writeFileSync(store.backupFile, '{broken backup');
  assert.throws(() => store.create({ id: 'new' }), /备份也不可用/);
  assert.equal(fs.readFileSync(store.file, 'utf8'), '{broken');
});

test('unchanged bootstrap upsert does not rotate backup or rewrite timestamps', t => {
 const store = fixture(t);
 const task = store.create({id:'a', plainContacts:584});
 let writes=0; const original=store.write.bind(store);store.write=state=>{writes++;return original(state)};
 assert.equal(store.upsert({...task,updatedAt:'ignored'}).updatedAt,task.updatedAt);
 assert.equal(writes,0);
 store.upsert({...task,plainContacts:585}); assert.equal(writes,1);
 assert.equal(store.current().plainContacts,585);
});


test('invalid save cannot replace either usable snapshot', t => {
 const store=fixture(t);store.create({id:'a',name:'保留资料'});
 const primary=fs.readFileSync(store.file,'utf8'),backup=fs.readFileSync(store.backupFile,'utf8');
 assert.throws(()=>store.write({tasks:null}),/任务保存数据无效/);
 assert.equal(fs.readFileSync(store.file,'utf8'),primary);
 assert.equal(fs.readFileSync(store.backupFile,'utf8'),backup);
});
test('backup disk failure aborts save and preserves prior task data', t => {
 const store=fixture(t);store.create({id:'a',name:'原资料'});
 const primary=fs.readFileSync(store.file,'utf8'),backup=fs.readFileSync(store.backupFile,'utf8');
 const originalCopy=fs.copyFileSync;
 fs.copyFileSync=(source,target,...args)=>{if(target===`${store.backupFile}.tmp`)throw Object.assign(new Error('disk full'),{code:'ENOSPC'});return originalCopy(source,target,...args);};
 try {assert.throws(()=>store.upsert({id:'a',name:'未写入修改'}),/disk full/);} finally {fs.copyFileSync=originalCopy;}
 assert.equal(fs.readFileSync(store.file,'utf8'),primary);assert.equal(fs.readFileSync(store.backupFile,'utf8'),backup);
 assert.equal(fs.existsSync(`${store.file}.tmp`),false);assert.equal(store.current().name,'原资料');
});
