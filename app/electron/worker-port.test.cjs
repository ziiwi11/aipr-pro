const test = require('node:test');
const assert = require('node:assert/strict');
const {buildWorkerCommand}=require('./worker-runner.cjs');
test('all browser workers use the app browser port instead of an existing Chrome session',()=>{
 for(const action of ['probe-login','collect-creators','contact-icons']){
  const command=buildWorkerCommand(action,{queuePath:'/test/queue',strategyPath:'/test/strategy'},
   {pythonExe:'/test/python',backendDir:'/test/backend',internalCdpPort:19367});
  assert.ok(command.args.includes('http://127.0.0.1:19367?shop=A'));
  assert.ok(command.args.includes('http://127.0.0.1:19367?shop=B'));
  assert.ok(!command.args.some(a=>a.includes(':9222')));
 }
});

test('saved-list delivery uses only the strict finalizer, without browser endpoints',()=>{
 const command=buildWorkerCommand('deliver-current',{id:'t', outputDir:'/saved', strategyPath:'/saved/rules',robotQueuePath:'/saved/queue'}, {pythonExe:'/py',backendDir:'/backend',internalCdpPort:19367});
 assert.ok(command.args[0].endsWith('finalize_creator_delivery.py'));
 assert.ok(command.args.includes('--deliver-current'));
 assert.ok(command.args.includes('--require-strict-highwater'));
 assert.ok(!command.args.some(a=>a.includes('http://')));
});

test('saved screenshot review is bounded and stays on the app sessions',()=>{
 const command=buildWorkerCommand('review-saved',{outputDir:'/saved',collectionStrategy:{keywords:['唇护理']}},{pythonExe:'/py',backendDir:'/backend',internalCdpPort:19367});
 assert.ok(command.args[0].endsWith('verify_creator_evidence_cdp.py'));
 assert.ok(command.args.includes('--review-saved'));
 assert.equal(command.args[command.args.indexOf('--limit')+1],'20');
 assert.ok(command.args.includes('/saved/aipr_strict_contact_highwater.json'));
 assert.ok(command.args.includes('http://127.0.0.1:19367?shop=A'));
 assert.ok(!command.args.some(arg=>arg.includes('collect_and_contact') || arg==='--robot-queue'));
});

 test("batch delivery uses a separate output and queue without changing cumulative source",()=>{
 const task={id:"t",outputDir:"/saved",strategyPath:"/saved/rules",robotQueuePath:"/global/queue",batchScope:{baselinePath:"/saved/batches/b/baseline.json",outputDir:"/saved/batches/b"}};
 const c=buildWorkerCommand("deliver-current",task,{pythonExe:"/py",backendDir:"/backend",internalCdpPort:19367});
 assert.equal(c.args[c.args.indexOf("--input")+1],"/saved/aipr_strict_contact_highwater.json");
 assert.equal(c.args[c.args.indexOf("--out-dir")+1],"/saved/batches/b");
 assert.equal(c.args[c.args.indexOf("--robot-queue")+1],"/saved/batches/b/outreach-queue.ndjson");
 assert.equal(task.outputDir,"/saved");
 });

test('saved list audit uses only saved task files and no browser endpoint',()=>{
 const c=buildWorkerCommand('audit-saved-list',{outputDir:'/saved',strategyPath:'/saved/rules'}, {pythonExe:'/python',backendDir:'/backend',internalCdpPort:19367});
 assert.ok(c.args.includes('--saved-task-dir'));
 assert.ok(c.args.includes('/saved'));
 assert.ok(c.args.includes('--strategy'));
 assert.equal(c.args.some(arg=>arg.includes('http://')||arg.includes('--shop-')),false);
});
