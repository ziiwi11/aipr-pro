import {it,expect} from 'vitest';import {filterCreators} from './creator-filters';
it('combines text, channel and screenshot filters while retaining unknown fans and source order',()=>{
 const rows=[{id:'unknown',nickname:'唇护理',phone:'123'},{id:'known',nickname:'唇护理达人',wechat:'wx',fans:100,evidenceScreenshot:'/proof.png'},{id:'other',nickname:'其他',wechat:'other',fans:200}];
 expect(filterCreators(rows,'唇','wechat','has','fans').map(x=>x.id)).toEqual(['known']);
 expect(filterCreators(rows,'','all','all','fans').map(x=>x.id)).toEqual(['other','known','unknown']);
 expect(rows.map(x=>x.id)).toEqual(['unknown','known','other']);
 expect(filterCreators(rows,'','all','missing','default').map(x=>x.id)).toEqual(['unknown','other']);
});
