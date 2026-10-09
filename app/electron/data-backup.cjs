const fs=require('node:fs'), path=require('node:path'), crypto=require('node:crypto');
const fsp=fs.promises;
const ROOT_KEYS=new Set(['brand-tasks','tasks','reviews','run-history','integrations']);
const inside=(child,parent)=>child===parent||child.startsWith(parent+path.sep);
function backupWriteError(error){
 const messages={EACCES:'备份位置没有写入权限，请选择文稿或其他可写目录',EPERM:'备份位置没有写入权限，请选择文稿或其他可写目录',EROFS:'备份位置为只读目录，请选择其他可写目录',ENOSPC:'备份位置空间不足，请释放空间或选择其他磁盘',EDQUOT:'备份位置存储额度不足，请选择其他磁盘',EEXIST:'备份目录已存在，请重新选择保存位置'};
 return messages[error?.code]?new Error(messages[error.code],{cause:error}):error;
}
async function hash(file){const digest=crypto.createHash('sha256');for await(const chunk of fs.createReadStream(file))digest.update(chunk);return digest.digest('hex');}
async function list(dir,prefix='',skipped=[]){
 const entries=[];
 for(const item of await fsp.readdir(dir,{withFileTypes:true})){
  const rel=path.join(prefix,item.name),file=path.join(dir,item.name);
  if(/\.(app|framework)$/i.test(item.name) || item.name.toLowerCase()==='node_modules'){skipped.push({path:rel.split(path.sep).join('/'),reason:'软件包或构建依赖，不属于业务数据'});continue;}
  if(item.isSymbolicLink())throw new Error('备份源包含符号链接，请先核对数据位置');
  if(item.isDirectory())entries.push(...await list(file,rel,skipped));else if(item.isFile())entries.push(rel);
 }
 return entries;
}
async function createBackup(roots,target,onProgress=()=>{}){
 target=path.resolve(target);
 if(roots.some(root=>inside(target,path.resolve(root.source))))throw new Error('备份位置不能放在源数据目录中');
 try{await fsp.mkdir(target,{mode:0o700});}catch(error){throw backupWriteError(error);}
 let copiedBytes=0;
 const manifest={schema:'qianxun-backup-v1',createdAt:new Date().toISOString(),roots:[],files:[],skipped:[],excludes:['凭据','登录会话','发送授权']};
 try{
  for(const root of roots){
   if(!ROOT_KEYS.has(root.key))throw new Error('备份根目录无效');
   if(!fs.existsSync(root.source))continue;
   manifest.roots.push({key:root.key,source:path.resolve(root.source)});
   const skipped=[];const files=await list(root.source,'',skipped);manifest.skipped.push(...skipped.map(entry=>({...entry,root:root.key})));
   for(const rel of files){
    const destination=path.join(target,'files',root.key,rel);await fsp.mkdir(path.dirname(destination),{recursive:true,mode:0o700});
    await fsp.copyFile(path.join(root.source,rel),destination,fs.constants.COPYFILE_FICLONE);await fsp.chmod(destination,0o600);
    const stat=await fsp.stat(destination);manifest.files.push({root:root.key,path:rel.split(path.sep).join('/'),size:stat.size,sha256:await hash(destination)});
    copiedBytes+=stat.size;onProgress({files:manifest.files.length,bytes:copiedBytes});
   }
  }
  await fsp.writeFile(path.join(target,'manifest.json'),JSON.stringify(manifest,null,2),{mode:0o600});return {path:target,files:manifest.files.length,bytes:manifest.files.reduce((sum,f)=>sum+f.size,0)};
 }catch(error){await fsp.writeFile(path.join(target,'INCOMPLETE.txt'),'备份未完成，不可恢复。',{mode:0o600}).catch(()=>{});throw backupWriteError(error);}
}
function safePath(root,relative){
 if(typeof relative!=='string'||!relative||relative.includes('\\')||relative.includes('\0')||relative.split('/').some(part=>part==='..'||part===''||part==='.')||path.isAbsolute(relative))throw new Error('备份包含不安全路径');
 const resolved=path.resolve(root,relative);if(!inside(resolved,root))throw new Error('备份路径越界');return resolved;
}
async function validateBackup(source,onProgress=()=>{}){
 if(fs.existsSync(path.join(source,'INCOMPLETE.txt')))throw new Error('备份未完成，不能恢复');
 let manifest;
 try{manifest=JSON.parse(await fsp.readFile(path.join(source,'manifest.json'),'utf8'));}
 catch(error){
  if(error.code==='ENOENT')throw new Error('未找到备份清单，请选择包含 manifest.json 的完整千寻备份目录');
  if(error.code==='EACCES'||error.code==='EPERM')throw new Error('无法读取备份清单，请选择有读取权限的备份目录');
  if(error instanceof SyntaxError)throw new Error('备份清单损坏，不能恢复；请重新选择完整备份');
  throw error;
 }
 if(manifest.schema!=='qianxun-backup-v1'||!Array.isArray(manifest.roots)||!Array.isArray(manifest.files)||manifest.files.length>1000000)throw new Error('备份格式无效');
 const roots=new Set();for(const root of manifest.roots){if(!ROOT_KEYS.has(root.key)||roots.has(root.key)||typeof root.source!=='string')throw new Error('备份目录声明无效');roots.add(root.key);}
 const seen=new Set();let checked=0;
 for(const entry of manifest.files){
  if(!roots.has(entry.root))throw new Error('备份文件根目录无效');
  const base=path.resolve(source,'files',entry.root),file=safePath(base,entry.path),key=entry.root+'/'+entry.path;
  if(seen.has(key))throw new Error('备份包含重复文件');seen.add(key);
  if(!/^[a-f0-9]{64}$/.test(entry.sha256)||!Number.isSafeInteger(entry.size)||entry.size<0)throw new Error('备份校验数据无效');
  const realSource=await fsp.realpath(source),realBase=await fsp.realpath(base);
  if(realBase!==path.join(realSource,"files",entry.root))throw new Error("备份根目录包含链接");
  const real=await fsp.realpath(file);if(!inside(real,realBase))throw new Error('备份存在越界链接');
  const stat=await fsp.stat(file);if(!stat.isFile()||stat.size!==entry.size||await hash(file)!==entry.sha256)throw new Error(`备份文件校验失败：${entry.path}`);
  onProgress({files:++checked,bytes:0});
 }
 return manifest;
}
async function restoreBackup(source,target,onProgress=()=>{}){
 const manifest=await validateBackup(source,progress=>onProgress({...progress,message:"正在校验备份完整性"}));
 target=path.resolve(target);await fsp.mkdir(target,{mode:0o700});let count=0;
 try{
  for(const entry of manifest.files){const destination=safePath(path.join(target,entry.root),entry.path);await fsp.mkdir(path.dirname(destination),{recursive:true,mode:0o700});await fsp.copyFile(path.join(source,'files',entry.root,entry.path),destination,fs.constants.COPYFILE_FICLONE);await fsp.chmod(destination,0o600);if(await hash(destination)!==entry.sha256)throw new Error("恢复期间文件发生变化，原数据未覆盖");onProgress({files:++count,bytes:0,message:"正在恢复到独立目录"});}
  await fsp.writeFile(path.join(target,'restore-manifest.json'),JSON.stringify(manifest,null,2),{mode:0o600});
  return {path:target,manifest,files:count};
 }catch(error){await fsp.writeFile(path.join(target,'INCOMPLETE.txt'),'恢复未完成，原数据未覆盖。').catch(()=>{});throw error;}
}
module.exports={createBackup,restoreBackup,validateBackup,backupWriteError};
