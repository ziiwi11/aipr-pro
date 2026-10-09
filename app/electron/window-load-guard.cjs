function guardWindowLoad(window, showMessageBox, {timeoutMs=20000,setTimer=setTimeout,clearTimer=clearTimeout}={}) {
 let timer,complete=false,prompting=false,disposed=false;
 const contents=window.webContents;
 const alive=()=>!disposed&&!window.isDestroyed()&&!contents.isDestroyed();
 const cancelTimer=()=>{if(timer!==undefined){clearTimer(timer);timer=undefined;}};
 const arm=()=>{cancelTimer();if(alive()&&!complete)timer=setTimer(()=>{timer=undefined;void failed();},timeoutMs);};
 async function failed(){
  if(!alive()||complete||prompting)return;
  prompting=true;cancelTimer();
  try {
   const result=await showMessageBox(window,{type:'error',title:'千寻页面未完成加载',message:'软件页面暂时无法打开',detail:'已保存的任务和名单仍保留在本机。可以重试打开页面；这不会重新启动采集作业。',buttons:['重试打开页面','保留窗口'],defaultId:0,cancelId:1});
   if(result.response===0&&alive()&&!complete){contents.reload();arm();}
  }catch{}finally{prompting=false;}
 }
 const loaded=()=>{complete=true;cancelTimer();};
 const loadFailed=(_event,code,_description,_url,isMainFrame)=>{if(isMainFrame&&code!==-3)void failed();};
 contents.on('did-finish-load',loaded);contents.on('did-fail-load',loadFailed);arm();
 const dispose=()=>{disposed=true;cancelTimer();contents.removeListener('did-finish-load',loaded);contents.removeListener('did-fail-load',loadFailed);};
 window.once('closed',dispose);
 return {dispose};
}
module.exports={guardWindowLoad};
