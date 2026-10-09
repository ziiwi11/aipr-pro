const test=require('node:test'),assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{once}=require('node:events');
const {terminateProcessTree}=require('./process-tree.cjs');
test('pause terminates detached descendant sessions as well as the pipeline parent',{skip:process.platform==='win32'},async t=>{
 const script="const {spawn}=require('node:child_process');const c=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{detached:true,stdio:'ignore'});console.log(c.pid);setInterval(()=>{},1000);";
 const parent=spawn(process.execPath,['-e',script],{detached:true,stdio:['ignore','pipe','ignore']});
 let descendant; t.after(()=>{try{process.kill(-parent.pid,'SIGKILL');}catch{}if(descendant)try{process.kill(descendant,'SIGKILL');}catch{}});
 descendant=Number(String((await once(parent.stdout,'data'))[0]).trim());assert(descendant>0);
 const closed=once(parent,'close');assert.equal(terminateProcessTree(parent),true);await closed;
 let alive=true;for(let i=0;i<30;i++){try{process.kill(descendant,0);}catch{alive=false;break;}await new Promise(r=>setTimeout(r,50));}
 assert.equal(alive,false,'detached collector must not remain alive after pause');
});
