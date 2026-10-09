const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {remapPaths,migrateRestoredReferences}=require('./restore-paths.cjs');
test('restored artifacts follow the new directory while unrelated strings stay intact',async()=>{
 const target=await fs.mkdtemp(path.join(os.tmpdir(),'qianxun-restore-paths-'));
 try{
 const roots=[{key:'brand-tasks',source:'/old/品牌任务'}];const source={meta:{final_xlsx:'/old/品牌任务/batch/final.xlsx',count:584},rows:[{identity:'one',contact:'12345',screenshot:'/old/品牌任务/batch/proof.png'}],unknown:'/old/品牌任务-other/file'};
 await fs.mkdir(path.join(target,'brand-tasks/batch'),{recursive:true});const json=path.join(target,'brand-tasks/batch/final.json'),nd=path.join(target,'brand-tasks/batch/queue.ndjson');await fs.writeFile(json,JSON.stringify(source));await fs.writeFile(nd,JSON.stringify(source.rows[0])+'\n');
 const files=[{root:'brand-tasks',path:'batch/final.json'},{root:'brand-tasks',path:'batch/queue.ndjson'}];assert.equal(await migrateRestoredReferences(target,{roots,files}),2);
 const result=JSON.parse(await fs.readFile(json));assert.equal(result.meta.final_xlsx,path.join(target,'brand-tasks/batch/final.xlsx'));assert.equal(result.meta.count,584);assert.equal(result.rows[0].contact,'12345');assert.equal(result.unknown,source.unknown);assert.equal(JSON.parse(await fs.readFile(nd)).screenshot,path.join(target,'brand-tasks/batch/proof.png'));
 assert.equal(remapPaths('/old/品牌任务-other',roots,target),'/old/品牌任务-other');
 assert.deepEqual(remapPaths(remapPaths(source,roots,target),roots,target),remapPaths(source,roots,target));
 }finally{await fs.rm(target,{recursive:true,force:true});}
});

test('path migration is idempotent when the recovery directory is inside the original data root',()=>{
 const roots=[{key:'brand-tasks',source:'/data/brands'}],target='/data/brands/恢复-123';
 const first=remapPaths('/data/brands/task/final.json',roots,target);
 assert.equal(first,'/data/brands/恢复-123/brand-tasks/task/final.json');
 assert.equal(remapPaths(first,roots,target),first);
});

test('cross-platform restore remaps Windows source paths and multi-image lists to Mac',()=>{
 const roots=[{key:'brand-tasks',source:'C:\\Users\\甲方\\Documents\\品牌任务'}];
 const rows={images:'C:\\Users\\甲方\\Documents\\品牌任务\\batch\\a.png\nC:\\Users\\甲方\\Documents\\品牌任务\\batch\\b.png',queue:'c:\\users\\甲方\\documents\\品牌任务\\batch\\queue.ndjson',contact:'wx123',outside:'C:\\Users\\甲方\\Documents\\品牌任务-other\\file'};
 const mapped=remapPaths(rows,roots,'/new/恢复');
 assert.equal(mapped.images,'/new/恢复/brand-tasks/batch/a.png\n/new/恢复/brand-tasks/batch/b.png');
 assert.equal(mapped.queue,'/new/恢复/brand-tasks/batch/queue.ndjson');
 assert.equal(mapped.contact,'wx123');assert.equal(mapped.outside,rows.outside);
 assert.deepEqual(remapPaths(mapped,roots,'/new/恢复'),mapped);
});
test('Mac source exports and pipe-separated evidence map to a Windows destination',()=>{
 const roots=[{key:'brand-tasks',source:'/Users/mac/品牌任务'}],target='D:\\千寻数据\\恢复';
 const mapped=remapPaths('/Users/mac/品牌任务/batch/a.png | /Users/mac/品牌任务/batch/b.png',roots,target);
 assert.equal(mapped,'D:\\千寻数据\\恢复\\brand-tasks\\batch\\a.png | D:\\千寻数据\\恢复\\brand-tasks\\batch\\b.png');
 assert.equal(remapPaths(mapped,roots,target),mapped);
});

test('Windows path case differences do not remap an already restored nested path twice',()=>{
 const roots=[{key:'brand-tasks',source:'C:\\Data'}],target='C:\\Data\\恢复';
 const already='c:\\data\\恢复\\brand-tasks\\batch\\final.json';
 assert.equal(remapPaths(already,roots,target),already);
});
