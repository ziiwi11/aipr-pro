const fs=require('node:fs');
const cache=new Map();
function read(file,kind){
 const stat=fs.statSync(file,{bigint:true});const key=kind+':'+file,signature=[stat.ino,stat.size,stat.mtimeNs,stat.ctimeNs].join(':');
 const saved=cache.get(key);if(saved?.signature===signature)return saved.value;
 const text=fs.readFileSync(file,'utf8');
 const value=kind==='json'?JSON.parse(text):text.split(/\r?\n/).filter(Boolean).flatMap(line=>{try{const record=JSON.parse(line);return record&&typeof record==='object'?[record]:[];}catch{return [];}});
 cache.delete(key);cache.set(key,{signature,value});while(cache.size>64)cache.delete(cache.keys().next().value);
 return value; // Callers only read; normalization makes its own records.
}
module.exports={readCachedJson:file=>read(file,'json'),readCachedNdjson:file=>read(file,'ndjson')};
