const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const jev = require('./jev-settings.cjs');
test('fresh setup and edits preserve other apps and do not expose credentials', t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'aipr-jev-test-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  fs.writeFileSync(path.join(dir, 'enabled-apps'), 'other-app\n');
  const result = jev.save({ apiKey: 'test-credential' }, dir);
  assert.equal(result.configured, true);
  assert.equal(result.decisionMode, true);
  assert.equal(JSON.stringify(result).includes('test-credential'), false);
  assert.equal(fs.statSync(path.join(dir, 'aipr-pro.json')).mode & 0o777, 0o600);
  assert.equal(fs.readFileSync(path.join(dir, 'enabled-apps'), 'utf8'), 'other-app\naipr-pro\n');
  jev.save({ apiKey: '' }, dir);
  assert.equal(JSON.parse(fs.readFileSync(path.join(dir, 'aipr-pro.json'))).api_key, 'test-credential');
});
test('blank fresh configuration is rejected', t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'aipr-jev-empty-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  assert.throws(() => jev.save({}, dir), /API Key/);
});
test('model changes preserve the saved credential and invalid models do not modify config', t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'jev-model-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 jev.save({apiKey:'credential',model:'jev-1.13.0'},dir);
 assert.equal(jev.save({apiKey:'',model:'jev-preview'},dir).model,'jev-preview');
 assert.equal(JSON.parse(fs.readFileSync(path.join(dir,'aipr-pro.json'))).api_key,'credential');
 assert.throws(()=>jev.save({model:'invalid'},dir),/模型/);
 assert.equal(jev.status(dir).model,'jev-preview');
});
test('system encryption migrates plaintext credentials without exposing them or losing model settings',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'jev-vault-'));t.after(()=>{jev.configureEncryption(null);fs.rmSync(dir,{recursive:true,force:true});});
 const flip=buffer=>Buffer.from(buffer.map(x=>x^255));
 const provider={isEncryptionAvailable:()=>true,encryptString:value=>flip(Buffer.from(value)),decryptString:buffer=>flip(buffer).toString()};
 jev.save({apiKey:'private-test-key',model:'jev-preview'},dir);
 jev.configureEncryption(provider);assert.equal(jev.migrate(dir),true);
 const config=JSON.parse(fs.readFileSync(path.join(dir,'aipr-pro.json'),'utf8'));
 assert.equal(config.api_key,undefined);assert.equal(config.credential_storage,'os-encrypted');
 assert.ok(!fs.readFileSync(path.join(dir,'aipr-pro.credential')).includes('private-test-key'));
 assert.equal(jev.getApiKey(dir),'private-test-key');assert.equal(jev.status(dir).configured,true);
 assert.equal(jev.save({apiKey:'',model:'jev-latest'},dir).model,'jev-latest');assert.equal(jev.getApiKey(dir),'private-test-key');
 jev.configureEncryption({isEncryptionAvailable:()=>false});
 assert.throws(()=>jev.save({apiKey:'replacement'},dir),/原配置已保留/);
 assert.equal(JSON.parse(fs.readFileSync(path.join(dir,'aipr-pro.json'),'utf8')).model,'jev-latest');
});

test('already encrypted configuration does not access the keychain during startup migration', () => {
 const tmp = fs.mkdtempSync(path.join(os.tmpdir(),'qianxun-migration-'));
 try {
  fs.writeFileSync(path.join(tmp,'aipr-pro.json'),JSON.stringify({credential_storage:'os-encrypted',model:'jev-latest'}));
  let keychainAccesses=0;
  jev.configureEncryption({isEncryptionAvailable(){keychainAccesses++;throw new Error('system prompt');}});
  assert.equal(jev.migrate(tmp),false);
  assert.equal(keychainAccesses,0);
 }finally{jev.configureEncryption(null);fs.rmSync(tmp,{recursive:true,force:true});}
});
