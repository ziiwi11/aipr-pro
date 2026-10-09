const fs=require('node:fs'),path=require('node:path');
class ReviewStore {
 constructor(userData){this.dir=path.join(userData,'reviews');fs.mkdirSync(this.dir,{recursive:true});}
 file(taskId){if(!/^[a-zA-Z0-9_-]{1,120}$/.test(taskId))throw new Error('任务标识无效');return path.join(this.dir,`${taskId}.json`);}
 read(taskId){const file=this.file(taskId);if(!fs.existsSync(file))return {version:1,records:[]};try{const value=JSON.parse(fs.readFileSync(file,'utf8'));if(!Array.isArray(value.records))throw new Error();return value;}catch{throw new Error('复核记录无法读取，原文件已保留');}}
 save(taskId,payload){
  const creatorId=String(payload?.creatorId||'').trim(),note=String(payload?.note||'').trim(),disposition=String(payload?.disposition||'');
  if(!creatorId||creatorId.length>300)throw new Error('达人标识无效');
  if(!note||note.length>2000)throw new Error('请填写1–2000字复核说明');
  if(!['needs_evidence','reviewed_note','exclude_requested'].includes(disposition))throw new Error('复核处理方式无效');
  const data=this.read(taskId),file=this.file(taskId);
  const record={creatorId,note,disposition,recordedAt:new Date().toISOString(),revision:data.records.filter(r=>r.creatorId===creatorId).length+1,admissionChanged:false};
  data.records.push(record);fs.writeFileSync(`${file}.tmp`,JSON.stringify(data,null,2),{mode:0o600});fs.renameSync(`${file}.tmp`,file);return record;
 }
}
module.exports={ReviewStore};
