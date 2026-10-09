const fs=require('node:fs'),path=require('node:path');
const FIELDS=['wechat','phone','email'];
function identityKeys(row={}) {
 const groups={account:[row.id,row.identity,row.buyin_uid],public:[row.douyinId,row.douyin_id,row['抖音号']],douyin:[row.douyinHomepage,row.douyin_homepage,row['抖音主页']],buyin:[row.buyinHomepage,row.buyin_profile_url,row['精选联盟主页']]};
 return new Set(Object.entries(groups).flatMap(([group,values])=>values.map(v=>String(v||'').trim().toLowerCase()).filter(Boolean).map(v=>group+':'+v)));
}
const sameIdentity=(a,b)=>[...identityKeys(a)].some(v=>identityKeys(b).has(v));
function createIdentityResolver(rows=[]) {
 const byKey=new Map();
 for(const row of rows)for(const key of identityKeys(row)){const found=byKey.get(key)||new Set();found.add(row);byKey.set(key,found);}
 return row=>{const found=new Set();for(const key of identityKeys(row))for(const candidate of byKey.get(key)||[])found.add(candidate);return found.size===1 ? [...found][0] : undefined;};
}
const values=row=>FIELDS.map(k=>String(row[k]||'').trim().toLowerCase().replace(/^\+/, '')).filter(Boolean);
function normalizeContacts(input={}){
 const result=Object.fromEntries(FIELDS.map(k=>[k,String(input[k]||'').trim()]));
 if(result.wechat&&(!/^[^\s@*]{1,64}$/.test(result.wechat)))throw Error('微信号格式无效；数字微信号可以保留，不能填入掩码');
 if(result.phone&&!/^\+?[0-9]{7,15}$/.test(result.phone))throw Error('手机号格式无效，填写明文数字或带国际区号号码');
 if(result.email&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(result.email))throw Error('邮箱格式无效');
 if(!values(result).length)throw Error('至少保留一种明文联系方式；缺证据请记录待复核');
 return result;
}
function applyContactCorrections(rows,records=[],identityRows=rows){
 const references=new Map(identityRows.map(r=>[String(r.id||r.identity||''),r]));

 return rows.map(row=>{const record=[...records].reverse().find(r=>{if(r.creatorId===String(row.id||row.identity||''))return true;const reference=references.get(r.creatorId);return reference&&sameIdentity(reference,row);});if(!record)return row;const channels=normalizeContacts(record.after);return {...row,...channels,plainContact:channels.wechat||channels.phone||channels.email,contactSource:record.source,contactCorrectedAt:record.recordedAt,contactCorrectionRevision:record.revision,contactCorrectionCreatorId:record.creatorId,contactVerification:'尚未验证可达性'};});
}
class ContactCorrectionStore {
 constructor(userData){this.dir=path.join(userData,'reviews');fs.mkdirSync(this.dir,{recursive:true});}
 file(taskId){if(!/^[a-zA-Z0-9_-]{1,120}$/.test(taskId))throw Error('任务标识无效');return path.join(this.dir,`${taskId}-contact-corrections.json`);}
 read(taskId){const file=this.file(taskId);if(!fs.existsSync(file))return {schema:'qianxun-contact-corrections-v1',taskId,records:[]};const data=JSON.parse(fs.readFileSync(file,'utf8'));if(data.schema!=='qianxun-contact-corrections-v1'||data.taskId!==taskId||!Array.isArray(data.records))throw Error('联系人修订记录损坏，原文件已保留');return data;}
 restore(source,oldTaskId,newTaskId){if(!fs.existsSync(source))return;const data=JSON.parse(fs.readFileSync(source,"utf8"));if(data.schema!=="qianxun-contact-corrections-v1"||data.taskId!==oldTaskId||!Array.isArray(data.records))throw Error("备份联系人修订记录无效");data.records.forEach(r=>normalizeContacts(r.after));data.taskId=newTaskId;const file=this.file(newTaskId);fs.writeFileSync(`${file}.tmp`,JSON.stringify(data,null,2),{mode:0o600});fs.renameSync(`${file}.tmp`,file);}
 apply(taskId,rows,identityRows=rows){return applyContactCorrections(rows,this.read(taskId).records,identityRows);}
 save(taskId,payload,rows,allFormal=rows){
 const creatorId=String(payload.creatorId||'');const data=this.read(taskId),effective=applyContactCorrections(rows,data.records),before=effective.find(r=>String(r.id||r.identity||'')===creatorId);if(!before)throw Error('请切换到达人所属批次后修订');
 const after=normalizeContacts(payload),source=String(payload.source||'').trim(),reason=String(payload.reason||'').trim();
 if(!source||source.length>500||!reason||reason.length>2000)throw Error('请填写来源（500字内）和修订理由（2000字内）');
 if(FIELDS.every(k=>String(before[k]||'')===after[k])&&before.contactSource===source)throw Error('联系方式和来源没有变化，无需保存');
 const updatedValues=new Set(values(after));
 if(applyContactCorrections(allFormal,data.records).some(r=>!sameIdentity(r,before)&&values(r).some(v=>updatedValues.has(v))))throw Error('联系方式与其他达人重复，请核对归属；系统不会自动合并不同身份');
 const record={creatorId,before:Object.fromEntries(FIELDS.map(k=>[k,String(before[k]||'')])),after,source,reason,recordedAt:new Date().toISOString(),revision:data.records.filter(r=>r.creatorId===creatorId).length+1,reachability:'unverified',admissionChanged:false};
 data.records.push(record);const file=this.file(taskId);fs.writeFileSync(`${file}.tmp`,JSON.stringify(data,null,2),{mode:0o600});fs.renameSync(`${file}.tmp`,file);return record;
 }
}
module.exports={ContactCorrectionStore,applyContactCorrections,normalizeContacts,sameIdentity,createIdentityResolver};
