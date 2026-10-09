const fs=require('node:fs');
const path=require('node:path');
const authorizedCache=new WeakMap();
function available(provider){try{return Boolean(provider?.isEncryptionAvailable());}catch{return false;}}
function writeCredential(dir,key,provider){
 if(!available(provider)) throw new Error('系统凭据加密暂不可用，原配置已保留');
 const encrypted=provider.encryptString(key);
 if(provider.decryptString(encrypted)!==key) throw new Error('凭据加密校验失败，原配置已保留');
 const file=path.join(dir,'aipr-pro.credential');fs.mkdirSync(dir,{recursive:true,mode:0o700});
 fs.writeFileSync(`${file}.tmp`,encrypted,{mode:0o600});fs.chmodSync(`${file}.tmp`,0o600);fs.renameSync(`${file}.tmp`,file);
}
function readCredential(dir,provider){
 if(!available(provider)) throw new Error('操作系统凭据保护暂不可用，已保存配置保留，请稍后重试');
 try{
  const encrypted=fs.readFileSync(path.join(dir,'aipr-pro.credential'));
  const fingerprint=encrypted.toString('base64');
  const cache=authorizedCache.get(provider);
  if(cache?.fingerprint===fingerprint)return cache.key;
  const key=provider.decryptString(encrypted);
  authorizedCache.set(provider,{fingerprint,key});return key;
 }catch{throw new Error('无法解密 Jev 已保存凭据；请检查系统现有访问授权后重试，原配置未修改，无需重新设置密钥');}
}
module.exports={available,writeCredential,readCredential};
