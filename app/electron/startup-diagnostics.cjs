const fs = require('node:fs');
const path = require('node:path');
function createStartupDiagnostics(directory) {
 const file=path.join(directory,'startup-diagnostics.jsonl');
 function record(event,details={}) {
  // Metadata only: never retain page URLs, console text, credentials or creator data.
  const row={at:new Date().toISOString(),event};
  for(const key of ['type','reason','exitCode','errorCode','isMainFrame']) {
   const value=details[key];
   if(typeof value==='number'||typeof value==='boolean')row[key]=value;
   else if(typeof value==='string'&&/^[a-zA-Z0-9_-]{1,60}$/.test(value))row[key]=value;
  }
  try {
   fs.mkdirSync(directory,{recursive:true,mode:0o700});
   if(fs.existsSync(file)&&fs.statSync(file).size>128*1024)fs.renameSync(file,`${file}.previous`);
   fs.appendFileSync(file,JSON.stringify(row)+'\n',{mode:0o600});
  } catch {} // Diagnostics must not prevent startup or overwrite task files.
 }
 function observeApp(app){record('diagnostics-ready');app.on('ready',()=>record('app-ready'));app.on('child-process-gone',(_event,details)=>record('child-process-gone',details));}
 function observeWindow(window){
  record('window-created');
  window.webContents.on('did-start-loading',()=>record('did-start-loading'));
  window.webContents.on('did-fail-load',(_event,errorCode,_description,_url,isMainFrame)=>record('did-fail-load',{errorCode,isMainFrame}));
  window.webContents.on('render-process-gone',(_event,details)=>record('render-process-gone',details));
  window.webContents.on('preload-error',()=>record('preload-error'));
  window.webContents.on('did-finish-load',()=>record('did-finish-load'));
  window.webContents.on('unresponsive',()=>record('renderer-unresponsive'));
 }
 return {record,observeApp,observeWindow,file};
}
module.exports={createStartupDiagnostics};
