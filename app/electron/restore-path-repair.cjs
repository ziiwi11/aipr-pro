const fs=require('node:fs');
// Repair only the exact double-prefix defect from 1.0.24 restore imports.
// Never redirect an original task or a path to a file that does not exist.
function repairRestoredTasks(state){
 let repaired=0;
 const tasks=state.tasks.map(task=>{
  if(!String(task.id).includes('-restored'))return task;
  let changed=false;const next={...task};
  for(const [key,value] of Object.entries(task)){
   if(typeof value!=='string')continue;
   const match=value.match(/^(.*\/恢复-([0-9]+)\/brand-tasks)\/恢复-\2\/brand-tasks(\/.*)$/);
   if(!match)continue;
   const fixed=match[1]+match[3];if(key==="outputDir" && fs.existsSync(match[1]))fs.mkdirSync(fixed,{recursive:true});if(!fs.existsSync(fixed))continue;
   next[key]=fixed;changed=true;
  }
  if(changed){repaired++;next.restorePathRepairedAt=new Date().toISOString();}
  return next;
 });
 return {state:{...state,tasks},repaired};
}
module.exports={repairRestoredTasks};
