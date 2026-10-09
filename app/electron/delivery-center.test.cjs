const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {discoverDeliveryArtifacts}=require('./delivery-center.cjs');
test('explicitly absent original workbook never selects another historical export',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qianxun-center-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));const final=path.join(dir,'final.json');fs.writeFileSync(path.join(dir,'旧批次_原格式补联系方式.xlsx'),'old');
 fs.writeFileSync(final,JSON.stringify({rows:[{id:'a'}],artifacts:{originalXlsx:''}}));const center=discoverDeliveryArtifacts(final);
 assert.equal(center.files.originalXlsx.path,'');assert.equal(center.metrics.exportedCount,1);assert.ok(!Object.keys(center.artifacts).includes('原格式补联系方式'));
});
