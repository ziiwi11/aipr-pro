const fs=require("node:fs"),path=require("node:path");
const {normalizeCreator}=require("./delivery-normalizer.cjs");
function identities(row={}){
 return new Set([row.id,row.identity,row.buyin_uid,row.douyinId,row.douyin_id,row["主页身份ID"],row["抖音号"],row.douyinHomepage,row.douyin_homepage,row["抖音主页"],row.buyinHomepage,row.buyin_profile_url,row["精选联盟主页"]].map(v=>String(v||"").trim().toLowerCase()).filter(Boolean));
}
function partitionBatch(rows=[],baseline=[]){
 const seen=new Set(baseline.flatMap(r=>[...identities(r)]));
 return {current:rows.filter(r=>![...identities(r)].some(v=>seen.has(v))),historical:baseline.map(normalizeCreator)};
}
function importBatchBaseline(task,source,payload,currentRows){
 const rows=Array.isArray(payload.candidates)?payload.candidates:payload.rows;
 if(!Array.isArray(rows)||!rows.length||rows.length>5000)throw Error("请选择有达人名单的基线 JSON");
 const known=new Set(currentRows.flatMap(r=>[...identities(r)]));
 if(rows.some(r=>!identities(r).size||![...identities(r)].some(v=>known.has(v))))throw Error("基线包含当前任务未保存的达人，不能据此划分批次");
 const batchDir=path.join(task.outputDir,"batches",`batch-${Date.now()}`);fs.mkdirSync(batchDir,{recursive:true});
 const baselinePath=path.join(batchDir,"baseline.json");fs.writeFileSync(baselinePath,JSON.stringify(payload,null,2));
 return {...task,batchScope:{id:path.basename(batchDir),baselinePath,sourcePath:source,baselineCount:rows.length,outputDir:batchDir,previousDeliveryPath:task.deliveryPath||"",createdAt:new Date().toISOString()}};
}
function readBatchScope(task){if(!task.batchScope)return null;const payload=JSON.parse(fs.readFileSync(task.batchScope.baselinePath,"utf8"));return {...task.batchScope,rows:payload.candidates||payload.rows||[],strategy:payload.strategy||{}};}
module.exports={identities,partitionBatch,importBatchBaseline,readBatchScope};
