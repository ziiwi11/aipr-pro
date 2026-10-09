const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {readCredential}=require('./credential-vault.cjs');
test('authorized decryption reused only within same provider and encrypted content; rotation invalidates cache',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'vault-cache-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));let reads=0;
 const provider={isEncryptionAvailable:()=>true,decryptString:b=>{reads++;return b.toString();}};
 const file=path.join(dir,'aipr-pro.credential');fs.writeFileSync(file,'synthetic-one');
 assert.equal(readCredential(dir,provider),'synthetic-one');assert.equal(readCredential(dir,provider),'synthetic-one');assert.equal(reads,1);
 fs.writeFileSync(file,'synthetic-two');assert.equal(readCredential(dir,provider),'synthetic-two');assert.equal(reads,2);
 const other={...provider};assert.equal(readCredential(dir,other),'synthetic-two');assert.equal(reads,3);
 fs.unlinkSync(file);assert.throws(()=>readCredential(dir,provider),/无法解密/);
});
