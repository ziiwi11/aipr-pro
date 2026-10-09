const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{EventEmitter}=require('node:events');
const {createStartupDiagnostics}=require('./startup-diagnostics.cjs');
test('startup failures retain process metadata without credentials, URLs or console text',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qianxun-startup-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));const logger=createStartupDiagnostics(dir),app=new EventEmitter(),wc=new EventEmitter();logger.observeApp(app);logger.observeWindow({webContents:wc});
 app.emit('child-process-gone',{}, {type:'Utility',reason:'launch-failed',exitCode:100,url:'https://private?key=secret',name:'private creator',apiKey:'secret'});
 wc.emit('did-fail-load',{},-6,'secret error','file:///private',true);wc.emit('preload-error',{},'/private',new Error('secret'));wc.emit('did-finish-load');
 const text=fs.readFileSync(logger.file,'utf8');assert.ok(!text.includes('secret'));assert.ok(!text.includes('private'));const all=text.trim().split('\n').map(JSON.parse);assert.equal(all[0].event,'diagnostics-ready');assert.ok(all.some(row=>row.event==='window-created'));const rows=all.filter(row=>!['diagnostics-ready','window-created'].includes(row.event));assert.equal(rows[0].reason,'launch-failed');assert.equal(rows[0].exitCode,100);assert.equal(rows[1].errorCode,-6);assert.equal(rows[3].event,'did-finish-load');
});
test('diagnostic write failure cannot stop application startup',()=>{const logger=createStartupDiagnostics(path.join('/dev/null','unwritable'));assert.doesNotThrow(()=>logger.record('preload-error'));});
