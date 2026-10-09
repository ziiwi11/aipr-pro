const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const {partitionBatch,importBatchBaseline,readBatchScope}=require("./batch-scope.cjs");
test("batch scope excludes baseline across encrypted identity rotation, retains new creators",()=>{
 const rows=[{id:"rotated",douyinId:"same"},{id:"fresh",douyinId:"new"}];
 assert.deepEqual(partitionBatch(rows,[{identity:"old",douyin_id:"same"}]).current,[rows[1]]);
});
test("baseline saves separately and leaves production and delivery snapshots intact",t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),"batch-scope-"));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const original=path.join(dir,"old.json");fs.writeFileSync(original,"original");
 const task={id:"t",outputDir:dir,deliveryPath:original};const updated=importBatchBaseline(task,"/baseline.json",{candidates:[{identity:"u",douyin_id:"dy"}]},[{id:"u",douyinId:"dy"}]);
 assert.equal(fs.readFileSync(original,"utf8"),"original");assert.equal(readBatchScope(updated).rows.length,1);assert.equal(task.batchScope,undefined);
 assert.throws(()=>importBatchBaseline(task,"/other",{candidates:[{identity:"alien"}]},[{id:"u"}]),/未保存/);
});
