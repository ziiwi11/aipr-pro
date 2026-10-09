import type {Creator} from './types';
export function filterCreators(rows:Creator[],query:string,channel:string,evidence:string,sort:string):Creator[]{
 const q=query.trim().toLowerCase();
 const filtered=rows.filter(c=>{
  if(q&&![c.nickname,c.douyinId,c.category,c.wechat,c.phone,c.email,c.plainContact,c.talentLevel].some(v=>String(v??'').toLowerCase().includes(q)))return false;
  if(channel!=='all'&&!String(c[channel]||'').trim())return false;
  const has=Boolean(String(c.evidenceScreenshot||'').trim());
  return evidence==='all'||(evidence==='has'?has:!has);
 });
 if(sort==='name')filtered.sort((a,b)=>String(a.nickname||'').localeCompare(String(b.nickname||''),'zh-CN'));
 if(sort==='fans'||sort==='score')filtered.sort((a,b)=>{
  const av=Number(a[sort]),bv=Number(b[sort]);const ak=Number.isFinite(av)&&av>0,bk=Number.isFinite(bv)&&bv>0;
  return ak!==bk?(ak?-1:1):ak?bv-av:0;
 });
 return filtered;
}
