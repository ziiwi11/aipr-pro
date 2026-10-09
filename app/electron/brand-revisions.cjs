const crypto=require('node:crypto');
const FIELDS=['brandName','productName','sellingPoints','brief','criteria','exclusions','category','contentType','creatorType','contentPresentation'];
function withBrandRevision(previous,next,now=new Date().toISOString()){
 const config=Object.fromEntries(FIELDS.map(key=>[key,next.collectionStrategy?.[key]??(key==='exclusions'?[]:'')]));
 const fingerprint=crypto.createHash('sha256').update(JSON.stringify(config)).digest('hex');
 const history=Array.isArray(previous?.brandRevisions)?previous.brandRevisions:[];
 if(history.at(-1)?.fingerprint===fingerprint)return {...next,brandRevisions:history};
 return {...next,brandRevisions:[...history,{version:(history.at(-1)?.version||0)+1,createdAt:now,fingerprint,config}]};
}
module.exports={withBrandRevision};
