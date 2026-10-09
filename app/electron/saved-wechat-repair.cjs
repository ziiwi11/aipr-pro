function savedWechatRepairs(rawRows=[],effectiveRows=[]) {
 const effective=new Map(effectiveRows.map(row=>[String(row.id||row.identity||""),row]));
 const repairs=[];
 for(const raw of rawRows){
  const id=String(raw.identity||raw.buyin_uid||""), row=effective.get(id);
  if(!row||row.contactCorrectionRevision)continue;
  const old=String(row.wechat||"").trim();
  if(!/^1[3-9]\d{9}$/.test(old))continue;
  const matches=(Array.isArray(raw.ui_contact_items_after)?raw.ui_contact_items_after:[]).map(text=>String(text).match(/^\s*达人微信号\s*[:：]\s*([A-Za-z][A-Za-z0-9_-]{5,19})\s*$/)).filter(Boolean).map(match=>match[1]);
  const observed=[...new Set(matches)];
  if(observed.length!==1||!observed[0].includes(old)||observed[0].toLowerCase()===old.toLowerCase())continue;
  repairs.push({creatorId:id,wechat:observed[0],phone:String(row.phone||""),email:String(row.email||""),source:"historical_platform_ui_prefix_repair",reason:"修复软件把含手机号数字串的微信号截断：按该达人原始平台微信标签展示恢复完整值；原名单保留，实际可达性未验证"});
 }
 return repairs;
}
function reconcileContactReview(report, effectiveRows=[]){
 if(!report)return report;
 const rows=new Map(effectiveRows.map(row=>[String(row.id||row.identity||""),row]));
 return {...report,records:(report.records||[]).map(record=>{
  const row=rows.get(record.identity), verification=record.contact_verification;
  if(!row?.contactCorrectionRevision||!verification?.observed_channels)return record;
  const channels={};for(const key of ['wechat','phone','email']){
   const saved=String(row[key]||'').trim(),observed=String(verification.observed_channels[key]||'').trim();
   channels[key]=saved&&observed?(saved===observed?'platform_match':'platform_mismatch'):'not_visible';
  }
  return {...record,contact_verification:{...verification,channels,compared_contact_revision:row.contactCorrectionRevision}};
 })};
}
module.exports={savedWechatRepairs,reconcileContactReview};
