const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {readCachedJson,readCachedNdjson}=require('./cached-file.cjs');
test('file cache reuses unchanged payloads and never returns stale data after replacement or damage',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'qianxun-cache-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));const file=path.join(root,'snapshot.json');fs.writeFileSync(file,'{"count":584}');const first=readCachedJson(file);assert.equal(readCachedJson(file),first);
 fs.writeFileSync(file+'.new','{"count":600}');fs.renameSync(file+'.new',file);assert.equal(readCachedJson(file).count,600);fs.writeFileSync(file,'broken');assert.throws(()=>readCachedJson(file));fs.unlinkSync(file);assert.throws(()=>readCachedJson(file));
 const history=path.join(root,'events.ndjson');fs.writeFileSync(history,'{"status":"one"}\nbroken\n');assert.equal(readCachedNdjson(history).length,1);fs.appendFileSync(history,'{"status":"two"}\n');assert.equal(readCachedNdjson(history).length,2);
});
