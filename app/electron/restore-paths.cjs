const fs=require('node:fs/promises'),path=require('node:path');
function remapPaths(value,roots,target){
 if(typeof value==='string'){
  // Snapshot paths use the source computer's separators, not this host's.
  // Screenshots can be stored as newline or " | " separated path lists.
  const parts=value.split(/(\r?\n| \| )/);
  if(parts.length>1)return parts.map((part,index)=>index%2?part:remapPaths(part,roots,target)).join('');
  const normalized=value.replace(/\\/g,'/'),normalizedTarget=target.replace(/\\/g,'/');
  const windowsTarget=/^(?:[a-z]:[\\/]|\\\\)/i.test(target);
  const current=windowsTarget?normalized.toLowerCase():normalized,currentTarget=windowsTarget?normalizedTarget.toLowerCase():normalizedTarget;
  if(current===currentTarget||current.startsWith(currentTarget+'/'))return value;
  const targetPath=/^(?:[a-z]:[\\/]|\\\\)/i.test(target)?path.win32:path.posix;
  for(const root of roots){
   const source=root.source.replace(/\\/g,'/').replace(/\/$/,'');
   const windowsSource=/^(?:[a-z]:[\\/]|\\\\)/i.test(root.source);
   const candidate=windowsSource?normalized.toLowerCase():normalized,prefix=windowsSource?source.toLowerCase():source;
   if(candidate===prefix||candidate.startsWith(prefix+'/'))return targetPath.join(target,root.key,...normalized.slice(source.length).split('/').filter(Boolean));
  }
  return value;
 }
 if(Array.isArray(value))return value.map(field=>remapPaths(field,roots,target));
 if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([key,field])=>[key,remapPaths(field,roots,target)]));
 return value;
}
// Change only restored copies after the complete backup has been verified.
// Historical JSON/NDJSON references must follow the files to the new machine.
async function migrateRestoredReferences(target,manifest,onProgress=()=>{}){
 let changed=0,checked=0;
 for(const entry of manifest.files){
  onProgress({files:++checked,message:"正在迁移恢复数据引用（原数据保留）"});
  if(!/\.(json|ndjson)$/i.test(entry.path))continue;
  const file=path.join(target,entry.root,entry.path),before=await fs.readFile(file,'utf8');
  let after;
  try{
   if(/\.ndjson$/i.test(entry.path))after=before.split('\n').map(line=>line.trim()?JSON.stringify(remapPaths(JSON.parse(line),manifest.roots,target)):line).join('\n');
   else after=JSON.stringify(remapPaths(JSON.parse(before),manifest.roots,target),null,2)+'\n';
  }catch{continue;} // Unrelated text diagnostics are preserved byte for byte.
  const originalObjects=/\.ndjson$/i.test(entry.path)?before.split('\n').filter(x=>x.trim()).map(x=>JSON.parse(x)):JSON.parse(before);
  const remapped=remapPaths(originalObjects,manifest.roots,target);
  if(JSON.stringify(originalObjects)===JSON.stringify(remapped))continue;
  const temp=file+'.restore-tmp';await fs.writeFile(temp,after,{mode:0o600});await fs.rename(temp,file);changed++;
 }
 await fs.writeFile(path.join(target,'path-migration.json'),JSON.stringify({schema:'qianxun-restored-paths-v1',changedFiles:changed,createdAt:new Date().toISOString(),originalBackupUnchanged:true},null,2),{mode:0o600});
 return changed;
}
module.exports={remapPaths,migrateRestoredReferences};
