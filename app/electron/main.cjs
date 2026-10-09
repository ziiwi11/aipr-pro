const {partitionBatch,importBatchBaseline,readBatchScope}=require("./batch-scope.cjs");
const {savedWechatRepairs,reconcileContactReview}=require("./saved-wechat-repair.cjs");
const {ContactCorrectionStore,createIdentityResolver}=require("./contact-corrections.cjs");
const {createBootstrapPerformance}=require("./bootstrap-performance.cjs");
const bootstrapPerformance=createBootstrapPerformance();
const {withBrandRevision}=require("./brand-revisions.cjs");
const {repairRestoredTasks}=require("./restore-path-repair.cjs");
const { readCachedJson } = require("./cached-file.cjs");
const { resolveUserDataPath } = require("./product-identity.cjs");
const { setShopViewLayout } = require("./shop-view-layout.cjs");
const { createShopCrashRecovery } = require("./shop-crash-recovery.cjs");
const { preserveMacWindow, activateWindow } = require("./window-lifecycle.cjs");
const { stopWorker, taskWorkerStatus, collectionWorkerRunning } = require("./worker-lifecycle.cjs");
const { collectionEventStatus } = require("./collection-event-status.cjs");
const jevSettings = require("./jev-settings.cjs");
const { buildCreatorLibrary } = require("./creator-library.cjs");
const { safeStorage, app, BrowserWindow, WebContentsView, clipboard, dialog, ipcMain, shell } = require("electron");
const fs = require("node:fs");
const path = require("node:path");
const { spawn, spawnSync, execFile } = require("node:child_process");
const { remapPaths, migrateRestoredReferences } = require("./restore-paths.cjs");
const { createBackup, restoreBackup } = require("./data-backup.cjs");
let maintenance = {busy:false,message:"",files:0,bytes:0,lastBackup:""};
let maintenancePublishedAt=0;
function publishMaintenance(progress={},force=false){Object.assign(maintenance,progress);const now=Date.now();if(force||now-maintenancePublishedAt>=200){maintenancePublishedAt=now;mainWindow?.webContents.send("aipr:worker-event",{status:"maintenance_progress",maintenance:{...maintenance}});}}
const { ReviewStore } = require("./review-store.cjs");
const { TaskStore } = require("./task-store.cjs");
const { mergeTaskDeliverySnapshot, mergeTaskHighWater } = require("./task-high-water.cjs");
const { collectDeliveredIdentities, collectDeliveredContacts, taskLineage, deliveryExclusionTasks } = require("./delivery-exclusions.cjs");
const { mergeRuntimeCollectionStrategy, savedStartStrategy, preserveContentFitCategory } = require("./collection-strategy-runtime.cjs");
const { IntegrationAdapter } = require("./integration-adapter.cjs");
const { RunHistoryStore } = require("./run-history-store.cjs");
const { OutreachAuthorizationStore } = require("./outreach-authorization-store.cjs");
const { LeiShenClient } = require("./leishen-client.cjs");
const { OutreachIpcService } = require("./outreach-ipc-service.cjs");
const { terminateProcessTree } = require("./process-tree.cjs");
const { buildWorkerCommand, classifyWorkerEvent } = require("./worker-runner.cjs");
const { normalizeDelivery, normalizeCreator } = require("./delivery-normalizer.cjs");
const { readRealtimeCreatorFlow } = require("./realtime-flow-reader.cjs");
const { discoverDeliveryArtifacts, resolvePersistentTaskDir } = require("./delivery-center.cjs");
const {
  buildBrowserLaunch,
  buildEmbeddedUserAgent,
  buildPlatformReadiness,
  resolveBrowserExecutable,
  resolvePythonExecutable,
  resolveWorkerCwd,
} = require("./platform-runtime.cjs");

let modelTestRunning=false;
let mainWindow;
let shopLayoutEpoch=-1;
let activeWorker;
let activeWorkerTaskId = "";
let activeWorkerAction = "";
let activeWorkerSession = "";
let store;
let reviews;
let contactCorrections;
let integrations;
let runHistory;
let outreachAuthorizations;
let outreachService;
const embeddedShopViews = { A: null, B: null };
let embeddedStartupProbeScheduled = false;
const appRoot = path.resolve(__dirname, "..");
const {createStartupDiagnostics}=require("./startup-diagnostics.cjs");
const {guardWindowLoad}=require("./window-load-guard.cjs");
let startupDiagnostics;
const internalCdpPort = Math.max(1024, Number(process.env.AIPR_INTERNAL_CDP_PORT) || 19367);
const embeddedChromeUserAgent = buildEmbeddedUserAgent({platform:process.platform,chromeVersion:process.versions.chrome});

// Signed application resources must remain immutable after launch.
process.env.PYTHONDONTWRITEBYTECODE = "1";
app.setName("千寻");
// Keep the established storage path so the rename retains tasks and shop sessions.
app.setPath("userData", resolveUserDataPath(app.getPath("appData"), process.env.AIPR_USER_DATA_DIR));
startupDiagnostics=createStartupDiagnostics(app.getPath("userData"));
startupDiagnostics.observeApp(app);
app.commandLine.appendSwitch("remote-debugging-address", "127.0.0.1");
app.commandLine.appendSwitch("remote-debugging-port", String(internalCdpPort));
app.whenReady().then(() => {
  jevSettings.configureEncryption(safeStorage);
  try { jevSettings.migrate(); } catch { console.warn("Jev 凭据加密迁移未完成，现有配置已保留"); }
  const userData = app.getPath("userData");
  store = new TaskStore(userData);
  const restoreRepair=repairRestoredTasks(store.read());
  if(restoreRepair.repaired){store.write(restoreRepair.state);fs.writeFileSync(path.join(userData,"restore-path-repair.json"),JSON.stringify({repaired:restoreRepair.repaired,at:new Date().toISOString(),originalTasksUnchanged:true}),{mode:0o600});}
  reviews = new ReviewStore(userData);
  contactCorrections=new ContactCorrectionStore(userData);
  integrations = new IntegrationAdapter(userData);
  runHistory = new RunHistoryStore(userData);
  outreachAuthorizations = new OutreachAuthorizationStore(userData);
  outreachService = new OutreachIpcService({
    history: runHistory,
    authorizations: outreachAuthorizations,
    leishen: new LeiShenClient({
      ...(process.env.AIPR_LEISHEN_BASE_URL
        ? { baseUrl: process.env.AIPR_LEISHEN_BASE_URL }
        : { baseUrls: ["http://127.0.0.1:19628", "http://127.0.0.1:19627"] }),
      projectId: process.env.AIPR_LEISHEN_PROJECT_ID || "brand-referral",
    }),
  });
  registerIpc();
  createWindow();
});
app.on("activate", () => activateWindow(mainWindow, createWindow));
app.on("window-all-closed", () => process.platform !== "darwin" && app.quit());
let sessionQuitReady = false;
let sessionQuitPending = false;
app.on("before-quit", (event) => {
  terminateProcessTree(activeWorker);
  if (sessionQuitReady) return;
  event.preventDefault();
  if (sessionQuitPending) return;
  sessionQuitPending = true;
  Promise.allSettled(Object.values(embeddedShopViews).filter(Boolean).map((view) =>
    flushShopSession(view.webContents.session)
  )).then(() => { sessionQuitReady = true; app.quit(); });
});

async function flushShopSession(shopSession) {
  shopSession.flushStorageData();
  await shopSession.cookies.flushStore();
}


function createWindow() {
  shopLayoutEpoch=-1;
  mainWindow = new BrowserWindow({
    width: 1480,
    height: 980,
    minWidth: 1080,
    minHeight: 720,
    backgroundColor: "#f2f4f2",
    title: "千寻",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      webviewTag: true,
    },
  });
  startupDiagnostics.observeWindow(mainWindow);
  guardWindowLoad(mainWindow,(window,options)=>dialog.showMessageBox(window,options));
  if (app.isPackaged) mainWindow.loadFile(path.join(appRoot, "dist", "index.html"));
  else mainWindow.loadURL("http://127.0.0.1:4173");
  mainWindow.webContents.once("did-finish-load", () => ensureEmbeddedShopViews());
  mainWindow.on("close", (event) => preserveMacWindow(event, mainWindow, { quitting: sessionQuitPending }));
  mainWindow.on("closed", destroyEmbeddedShopViews);
}

function registerIpc() {
  ipcMain.handle("aipr:open-jev-console", () => shell.openExternal("https://console.typesafe.ai/"));
  ipcMain.handle("aipr:save-jev-settings", (_event, payload) => {
    ensureTaskChangeAllowed();
    return jevSettings.save(payload);
  });
  ipcMain.handle("aipr:test-jev-connection", async () => {
    ensureTaskChangeAllowed();
    if(modelTestRunning) throw Error("模型测试正在进行，请等待结果");
    modelTestRunning=true;
    try {
      const confirmation=await dialog.showMessageBox(mainWindow,{type:"question",buttons:["运行一次测试","取消"],defaultId:1,cancelId:1,title:"单次 Jev 模型测试",message:"调用云端模型一次，可能产生少量费用",detail:"只发送合成数字样例，不发送达人资料；最多一次请求、不自动重试、不启动采集或发送。实际金额以 Jev 官方账单为准。"});
      if(confirmation.response!==0)return {cancelled:true};
      const token=jevSettings.getApiKey();
      if(!token)throw Error("请先保存 Jev API Key");
      const paths=appPaths();
      const result=await new Promise((resolve,reject)=>execFile(paths.pythonExe,[path.join(paths.backendDir,"jev_connection_test.py")],{cwd:paths.backendDir,env:{...process.env,AIPR_JEV_API_KEY:token,AIPR_TASK_ID:"model-connection-test",PYTHONDONTWRITEBYTECODE:"1"},timeout:30000,maxBuffer:65536},(error,stdout)=>{
        if(error)return reject(Error("模型测试进程失败或超时，请检查网络与运行环境"));
        try{resolve(JSON.parse(stdout.trim()));}catch{reject(Error("模型测试结果格式无效"));}
      }));
      const record={...result,checkedAt:new Date().toISOString()};
      const file=path.join(app.getPath("userData"),"jev-connection-test.json");
      fs.writeFileSync(`${file}.tmp`,JSON.stringify(record,null,2),{mode:0o600});fs.renameSync(`${file}.tmp`,file);
      return record;
    } finally { modelTestRunning=false; }
  });
  ipcMain.handle("aipr:get-bootstrap", () => bootstrapPerformance.measure(buildBootstrap));
  ipcMain.handle("aipr:get-realtime-creator-flow", () => {
    const task = store.current() || defaultTask();
    return { ...readRealtimeCreatorFlow(task.outputDir || ""),
      workerRunning: collectionWorkerRunning(task, activeWorker, activeWorkerTaskId, activeWorkerAction),
      taskStatus: task.status };
  });
  ipcMain.handle("aipr:get-platform-readiness", () => platformReadiness());
  ipcMain.handle("aipr:list-tasks", () => ({
    currentTaskId: store.read().currentTaskId,
    tasks: store.list(),
  }));
  ipcMain.handle("aipr:create-task", (_event, payload = {}) => {
    ensureTaskChangeAllowed();
    const clean = sanitizeTask({ ...defaultTask(), ...payload });
    clean.collectionStrategy = sanitizeCollectionStrategy({ ...clean.collectionStrategy, targetCount: clean.targetCount });
    const created = store.create({
      ...clean,
      collected: 0,
      processed: 0,
      plainContacts: 0,
      wechat: 0,
      phone: 0,
      remaining: clean.targetCount,
      status: "idle",
      outputDir: "",
      deliveryPath: "",
      queuePath: "",
      originalWorkbookPath: "",
      strategyPath: "",
    });
    const outputDir = resolvePersistentTaskDir(documentsDir(), created.id);
    fs.mkdirSync(outputDir, { recursive: true });
    const saved = store.upsert({ ...created, outputDir });
    return buildTaskBootstrap(saved);
  });
  ipcMain.handle("aipr:select-task", (_event, taskId) => {
    ensureTaskChangeAllowed();
    return buildTaskBootstrap(store.select(String(taskId || "")));
  });
  ipcMain.handle("aipr:validate-delivery", async () => {
    if(maintenance.busy)throw new Error("数据维护正在进行");
    const task=currentTask();if(!task.deliveryPath)throw new Error("当前任务没有交付文件");
    maintenance={...maintenance,busy:true,message:"正在只读校验交付文件",files:0,bytes:0};
    try{
      const paths=appPaths();
      const stdout=await new Promise((resolve,reject)=>execFile(paths.pythonExe,[path.join(paths.backendDir,"validate_delivery.py"),"--source",task.deliveryPath],{encoding:"utf8",timeout:60000,maxBuffer:2000000,env:{...process.env,JEV_INTEGRATION:"0",AIPR_JEV_API_KEY:""}},(error,out)=>error?reject(new Error("交付校验无法完成，请检查文件是否可读取")):resolve(out)));
      const report=JSON.parse(String(stdout).trim());
      const directory=path.join(app.getPath("userData"),"delivery-validation");fs.mkdirSync(directory,{recursive:true});fs.writeFileSync(path.join(directory,task.id+".json"),JSON.stringify(report,null,2),{mode:0o600});
      maintenance.message=report.ok ? `交付校验通过：${report.rowCount} 人，队列 ${report.queueCount} 人` : "交付校验未通过，请查看交付中心原因";return report;
    }catch(error){maintenance.message="交付校验失败，原文件未修改";throw error;}finally{maintenance.busy=false;publishMaintenance({},true);}
  });
  ipcMain.handle("aipr:backup-data", async () => {
    ensureTaskChangeAllowed();if(maintenance.busy)throw new Error("数据维护正在进行");
    const choice=await dialog.showOpenDialog(mainWindow,{title:"选择备份保存位置",properties:["openDirectory","createDirectory"]});
    if(choice.canceled)return null;
    ensureTaskChangeAllowed();if(maintenance.busy)throw new Error("数据维护正在进行");
    const target=path.join(choice.filePaths[0],`千寻备份-${Date.now()}`),userData=app.getPath("userData");
    maintenance={...maintenance,busy:true,message:"正在备份名单、证据和任务数据",files:0,bytes:0};publishMaintenance({},true);
    try{
      const roots=[{key:"brand-tasks",source:path.join(documentsDir(),"AIPR Pro","品牌任务")},...[["tasks","tasks"],["reviews","reviews"],["run-history","history"],["integrations","integrations"]].map(([key,folder])=>({key,source:path.join(userData,folder)}))];
      const result=await createBackup(roots,target,progress=>publishMaintenance(progress));maintenance.lastBackup=result.path;maintenance.message=`备份完成：${result.files} 个文件`;return result;
    }catch(error){maintenance.message=`备份失败：${error.message||"请检查保存位置"}。未完成备份不能恢复，原数据保留`;throw error;}finally{maintenance.busy=false;publishMaintenance({},true);}
  });
  ipcMain.handle("aipr:restore-data", async () => {
    ensureTaskChangeAllowed();if(maintenance.busy)throw new Error("数据维护正在进行");
    const choice=await dialog.showOpenDialog(mainWindow,{title:"选择千寻备份目录（含manifest.json）",properties:["openDirectory"]});if(choice.canceled)return null;
    ensureTaskChangeAllowed();if(maintenance.busy)throw new Error("数据维护正在进行");
    maintenance={...maintenance,busy:true,message:"校验备份，恢复到独立目录",files:0,bytes:0};publishMaintenance({},true);
    const priorTaskIndex=store.read();
    try{
      const target=path.join(documentsDir(),"AIPR Pro","品牌任务",`恢复-${Date.now()}`);
      const result=await restoreBackup(choice.filePaths[0],target,progress=>publishMaintenance(progress));
      await migrateRestoredReferences(target,result.manifest,progress=>publishMaintenance(progress));
      const taskFile=path.join(target,"tasks","tasks.json");let imported=0;
      if(fs.existsSync(taskFile)){
        const restored=JSON.parse(fs.readFileSync(taskFile,"utf8"));if(!Array.isArray(restored.tasks) || restored.tasks.some(t=>!t || typeof t!=="object" || !/^[a-zA-Z0-9_-]{1,120}$/.test(String(t.id||""))))throw new Error("备份任务索引无效，恢复文件已保留");
        const selected=store.current()?.id;
        for(const original of restored.tasks){
          if(!original || typeof original!=="object" || !/^[a-zA-Z0-9_-]{1,120}$/.test(String(original.id||"")))throw new Error("备份任务标识无效，原任务未覆盖");
          const task=remapPaths(original,result.manifest.roots,target);task.id=String(task.id||"task")+"-restored";task.name=String(task.name||"恢复任务")+"（恢复）";
          task.status="ended";task.endedAt=new Date().toISOString();task.endedReason="从备份恢复，等待用户显式续跑";
          task.outputDir=path.resolve(String(task.outputDir||path.join(target,"brand-tasks",task.id)));
          if(!task.outputDir.startsWith(target+path.sep))task.outputDir=path.join(target,"brand-tasks",task.id);
          fs.mkdirSync(task.outputDir,{recursive:true});
          for(const field of ["deliveryPath","queuePath","originalWorkbookPath","strategyPath","robotQueuePath","lastContactPath"])if(task[field]){task[field]=path.resolve(String(task[field]));if(!task[field].startsWith(target+path.sep))task[field]="";}
          if(!fs.existsSync(task.outputDir) || task.deliveryPath && !fs.existsSync(task.deliveryPath))throw new Error("恢复引用不可用，原任务索引已保留");
          const saved=store.create(sanitizeTask(task));imported++;
          contactCorrections.restore(path.join(target,"reviews",String(original.id)+"-contact-corrections.json"),original.id,saved.id);
          const reviewFile=path.join(target,"reviews",String(original.id)+".json");if(fs.existsSync(reviewFile))fs.copyFileSync(reviewFile,reviews.file(saved.id));
        }
        if(selected)store.select(selected);
      }
      maintenance.message=`恢复完成，导入 ${imported} 个停止状态的任务；原数据未覆盖`;return {path:target,files:result.files,imported};
    }catch(error){store.write(priorTaskIndex);maintenance.message=`恢复失败：${error.message||"请检查备份完整性"}。原任务索引已保留，原数据未覆盖`;throw error;}finally{maintenance.busy=false;publishMaintenance({},true);}
  });
  ipcMain.handle("aipr:export-diagnostics", async () => {
    const choice=await dialog.showSaveDialog(mainWindow,{title:"保存去敏诊断报告",defaultPath:"千寻诊断报告.json",filters:[{name:"诊断报告",extensions:["json"]}]});if(choice.canceled)return null;
    const report={version:app.getVersion(),createdAt:new Date().toISOString(),platform:process.platform,arch:process.arch,bootstrapPerformance:bootstrapPerformance.summary(),taskCount:store.list().length,tasks:store.list().map(t=>({id:t.id,status:t.status,target:t.targetCount,candidates:t.collected,formal:t.plainContacts})),workerRunning:Boolean(activeWorker),jevConfigured:jevSettings.status().configured,excludes:["API Key","联系方式","作品和提示词","登录会话","完整日志与路径"]};
    fs.writeFileSync(choice.filePath,JSON.stringify(report,null,2),{mode:0o600});return choice.filePath;
  });
  ipcMain.handle("aipr:repair-saved-wechat", (_event, scope="current") => {
    if(!["current","history"].includes(scope))throw Error("联系人修复范围无效");
    ensureTaskChangeAllowed();
    if(maintenance.busy||outreachAuthorizations.list(currentTask().id).some(b=>b.status==="running"))throw Error("请在作业停止后修复");
    const state=buildTaskBootstrap(currentTask());
    const raw=readCachedJson(path.join(state.task.outputDir,"aipr_strict_contact_highwater.json"));
    const formal=formalCreatorsForTask(state.task), baseline=readBatchScope(state.task);
    const batch=baseline ? partitionBatch(formal,baseline.rows) : null;
    const rows=scope==="history" ? contactCorrections.apply(state.task.id,batch?.historical||[]) : state.creators;
    const suggestions=savedWechatRepairs(raw?.candidates||[],rows);
    let corrected=0;const errors=[];
    for(const payload of suggestions){try{contactCorrections.save(state.task.id,payload,rows,state.creatorLibrary.creators);corrected++;}catch(error){errors.push({creatorId:payload.creatorId,message:error.message});}}
    const result={checkedAt:new Date().toISOString(),suggested:suggestions.length,corrected,errors,historicalSourcesChanged:false,messagesSent:0,reachability:"unverified"};
    fs.writeFileSync(path.join(state.task.outputDir,"aipr_saved_wechat_repair_result.json"),JSON.stringify(result,null,2),{mode:0o600});
    return result;
  });
  ipcMain.handle("aipr:save-contact-correction", (_event,payload={})=>{
    if(maintenance.busy||activeWorker||outreachAuthorizations.list(currentTask().id).some(b=>b.status==="running"))throw Error("请在作业停止后修订联系方式");
    const state=buildTaskBootstrap(currentTask());
    return contactCorrections.save(state.task.id,payload,formalCreatorsForTask(state.task),state.creatorLibrary.creators);
  });
  ipcMain.handle("aipr:save-review-note", (_event,payload={}) => {
    if(maintenance.busy)throw new Error("数据维护正在进行");
    const state=buildTaskBootstrap(currentTask());
    const ids=new Set([...formalCreatorsForTask(state.task),...state.candidateCreators].map(c=>String(c.id||c.identity||"")));
    if(!ids.has(String(payload.creatorId||"")))throw new Error("请切换到达人所属批次后记录复核");
    return reviews.save(state.task.id,payload);
  });
  ipcMain.handle("aipr:save-task", (_event, task) => {
    if(maintenance.busy)throw new Error("数据维护正在进行");
    const previous=store.list().find(item=>item.id===task.id);
    const sanitized = withEmbeddedShops(sanitizeTask(task));
    if (previous && activeWorker && activeWorkerTaskId === task.id) {
      for (const key of ["status","processed","collected","scored","plainContacts","wechat","phone","remaining","endedAt","endedReason"]) sanitized[key] = previous[key];
    }
    const saved = store.upsert(withBrandRevision(previous,sanitized));
    if (saved.rules) integrations.saveRules(portableBundle(saved));
    return saved;
  });
  ipcMain.handle("aipr:import-file", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ["openFile"],
      filters: [{ name: "原始 Excel 名单（仅XLSX）", extensions: ["xlsx"] }],
    });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle("aipr:understand-brief", (_event,text) => require("./qwen-brief.cjs").understand(text));
  ipcMain.handle("aipr:import-brief", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ["openFile"],
      filters: [{ name: "品牌手卡", extensions: ["docx", "pdf", "xlsx", "xlsm", "txt", "md", "csv", "json"] }],
    });
    if (result.canceled || !result.filePaths[0]) return null;
    const paths = appPaths();
    const worker = spawnSync(paths.pythonExe, [path.join(paths.backendDir, "extract_brief.py"), "--file", result.filePaths[0]], {
      encoding: "utf8", windowsHide: true, timeout: 60000,
    });
    if (worker.status !== 0) throw new Error((worker.stderr || worker.stdout || "手卡解析失败").trim());
    const line = worker.stdout.split(/\r?\n/).filter(Boolean).pop();
    return JSON.parse(line);
  });
  ipcMain.handle("aipr:import-delivery", async () => {
    ensureTaskChangeAllowed();
    const taskId=currentTask().id;
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ["openFile"],
      filters: [{ name: "千寻交付数据", extensions: ["json"] }],
    });
    if (result.canceled || !result.filePaths[0]) return null;
    ensureTaskChangeAllowed();
    if(currentTask().id!==taskId)throw new Error("任务已切换，请重新导入交付数据");
    const deliveryPath = result.filePaths[0];
    const snapshot = readDeliverySnapshot(deliveryPath);
    if (!snapshot) throw new Error("无法读取所选交付数据");
    const task = {...mergeTaskDeliverySnapshot(currentTask(), { deliveryPath, ...snapshot.metrics }), importedDeliveryPath:deliveryPath};
    store.upsert(task);
    return { task, creators: snapshot.creators, candidateCreators: snapshot.candidateCreators, metrics: snapshot.metrics, deliveryCenter: discoverDeliveryArtifacts(deliveryPath) };
  });
  ipcMain.handle("aipr:load-delivery-path", (_event, deliveryPath) => {
    const resolved = path.resolve(String(deliveryPath || ""));
    const snapshot = readDeliverySnapshot(resolved);
    if (!snapshot) throw new Error("无法读取自动交付结果");
    const task = mergeTaskDeliverySnapshot(currentTask(), { deliveryPath: resolved, ...snapshot.metrics });
    store.upsert(task);
    return { task, creators: snapshot.creators, candidateCreators: snapshot.candidateCreators, metrics: snapshot.metrics, deliveryCenter: discoverDeliveryArtifacts(resolved) };
  });
  ipcMain.handle("aipr:launch-browsers", () => launchDualBrowsers());
  ipcMain.handle("aipr:layout-embedded-shop", (_event, payload = {}) => layoutEmbeddedShop(payload));
  ipcMain.handle("aipr:hide-embedded-shops", (_event,payload) => hideEmbeddedShopViews(payload));
  ipcMain.handle("aipr:control-embedded-shop", (_event, payload = {}) => controlEmbeddedShop(payload));
  ipcMain.handle("aipr:probe-login", () => runWorker("probe-login", currentTask()));
  ipcMain.handle("aipr:start-collection", (_event, payload = {}) => {
    ensureEmbeddedShopViews();
    const suppliedTask = payload.task || currentTask();
    const savedTask = store.list().find(item => item.id === suppliedTask.id);
    const task = sanitizeTask(savedTask || suppliedTask);
    const taskDir = task.outputDir || resolvePersistentTaskDir(documentsDir(), task.id);
    fs.mkdirSync(taskDir, { recursive: true });
    const strategyPath = path.join(taskDir, "collection-strategy.json");
    let existingStrategy = {};
    try {
      if (fs.existsSync(strategyPath)) existingStrategy = JSON.parse(fs.readFileSync(strategyPath, "utf8"));
    } catch {
      existingStrategy = {};
    }
    const strategy = mergeRuntimeCollectionStrategy({
      base: preserveContentFitCategory(sanitizeCollectionStrategy(savedStartStrategy(savedTask, payload.strategy || {})), readBatchScope(task)?.strategy || {}),
      preferSavedDiscovery: Boolean(savedTask?.collectionStrategy?.sourceDiscoveryMode),
      existing: existingStrategy,
      ownDeliveredIdentities: ownLineageDeliveryValues(task.id, false),
      ownDeliveredContacts: ownLineageDeliveryValues(task.id, true),
      deliveredIdentities: deliveredIdentitiesExcluding(task.id),
      deliveredContacts: deliveredIdentitiesExcluding(task.id, true),
    });
    fs.writeFileSync(strategyPath, JSON.stringify(strategy, null, 2), "utf8");
    const saved = store.upsert({
      ...task,
      targetCount: strategy.targetCount,
      collectionStrategy: strategy,
      strategyPath,
      outputDir: taskDir,
      robotQueuePath: integrations.paths.outreachQueue,
    });
    return runWorker("collect-creators", saved);
  });
  ipcMain.handle("aipr:start-worker", (_event, task) => runWorker("contact-icons", sanitizeTask(task)));
  ipcMain.handle("aipr:pause-worker", async () => {
    const worker = activeWorker;
    const taskId = activeWorkerTaskId;
    const stopped = await stopWorker(worker);
    if (stopped) {
      persistTaskStatus(taskId, "paused");
      clearWorker(worker, taskId);
    }
    return { ok: stopped, status: stopped ? "paused" : "stop_failed" };
  });
  ipcMain.handle("aipr:end-collection", async () => {
    const task = currentTask();
    if (activeWorker && activeWorkerTaskId !== task.id) throw new Error("其他任务正在运行，无法结束当前批次");
    if (activeWorker) {
      const worker = activeWorker;
      if (!await stopWorker(worker)) throw new Error("作业尚未停止，不能标记为已结束");
      clearWorker(worker, task.id);
    }
    const saved = store.current();
    return store.upsert({ ...saved, status: "ended", endedAt: new Date().toISOString(), endedReason: "用户结束本批，已保存名单和断点，原目标保留" });
  });
  ipcMain.handle("aipr:verify-saved-contacts", () => runWorker("verify-saved-contacts", currentTask()));
  ipcMain.handle("aipr:apply-saved-audit", async () => {
    if (activeWorker) return {ok:false,error:"已有作业正在运行，请等待完成"};
    const task=currentTask();
    let pending;
    try { pending=readCachedJson(path.join(task.outputDir,"aipr_saved_list_audit_pending_review.json")); }
    catch { return {ok:false,error:"没有可应用的复核差异，请先重新核对已保存名单"}; }
    if(pending.baseline_missing_count) return {ok:false,error:"原往期名单仍有差异，不能应用"};
    const confirmation=await dialog.showMessageBox(mainWindow,{type:"warning",title:"核对名单差异",message:"应用已复核的保存名单？",detail:`原正式 ${task.plainContacts} 人 → 建议 ${pending.strict_selected_count} 人；${pending.removed_previous_count} 位当前身份会移出正式名单。原往期身份已完整保留，严格联系人去重。应用前备份原名单，原始证据保留，不采集、不付费分析、不发送。`,buttons:["保留当前名单","应用已复核名单"],defaultId:0,cancelId:0});
    return confirmation.response===1 ? runWorker("apply-saved-audit",task) : {ok:false,error:"已保留当前名单"};
  });
  ipcMain.handle("aipr:audit-saved-list", () => runWorker("audit-saved-list", currentTask()));
  ipcMain.handle("aipr:review-saved", () => runWorker("review-saved", currentTask()));
  ipcMain.handle("aipr:open-saved-review", () => shell.openPath(path.join(currentTask().outputDir, "aipr_saved_evidence_review.json")));
  ipcMain.handle("aipr:import-batch-baseline", async () => {
    ensureTaskChangeAllowed();const task=store.current();
    const result=await dialog.showOpenDialog(mainWindow,{title:"选择本轮开始前的名单作为往期基线",properties:["openFile"],filters:[{name:"名单 JSON",extensions:["json"]}]});
    if(result.canceled)return {canceled:true};
    const source=result.filePaths[0],payload=JSON.parse(fs.readFileSync(source,"utf8"));
    const updated=importBatchBaseline(task,source,payload,formalCreatorsForTask(task));store.upsert(updated);return {count:updated.batchScope.baselineCount};
  });
  ipcMain.handle("aipr:deliver-current", (_event, task) => runWorker("deliver-current", sanitizeTask(store.list().find(t=>t.id===task.id)||task)));
  ipcMain.handle("aipr:export-original", (_event, task) => runWorker("export-original", sanitizeTask(task)));
  ipcMain.handle("aipr:open-path", (_event, target) => shell.openPath(String(target || "")));
  ipcMain.handle("aipr:get-delivery-center", (_event, target) => {
    const deliveryPath = String(target || currentTask().deliveryPath || "");
    return discoverDeliveryArtifacts(deliveryPath);
  });
  ipcMain.handle("aipr:preview-robot-handoff", (_event, target) => integrations.previewOutreachBatch(target));
  ipcMain.handle("aipr:copy-text", (_event, value) => {
    clipboard.writeText(String(value || ""));
    return { ok: true };
  });
  ipcMain.handle("aipr:export-rules", async (_event, task) => {
    const bundle = portableBundle(sanitizeTask(task));
    const result = await dialog.showSaveDialog(mainWindow, {
      defaultPath: `${task.id || "brand-task"}-aipr-rules.json`,
      filters: [{ name: "千寻规则配置", extensions: ["json"] }],
    });
    if (result.canceled || !result.filePath) return null;
    fs.writeFileSync(result.filePath, JSON.stringify(bundle, null, 2), "utf8");
    integrations.saveRules(bundle);
    return result.filePath;
  });
  ipcMain.handle("aipr:import-rules", async () => {
    ensureTaskChangeAllowed();
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ["openFile"],
      filters: [{ name: "千寻规则配置", extensions: ["json"] }],
    });
    if (result.canceled) return null;
    const bundle = JSON.parse(fs.readFileSync(result.filePaths[0], "utf8"));
    if (!bundle || typeof bundle !== "object" || !bundle.rules || typeof bundle.rules !== "object") {
      throw new Error("所选文件不是有效的品牌规则配置");
    }
    const task = store.current() || defaultTask();
    const importedTarget = Number(bundle.task?.targetCount) || Number(bundle.task?.collectionStrategy?.targetCount) || task.targetCount;
    const strategy = sanitizeCollectionStrategy({ ...(bundle.task?.collectionStrategy || task.collectionStrategy || {}), targetCount: importedTarget });
    const saved = store.upsert(sanitizeTask({ ...task, rules: bundle.rules,
      collectionStrategy: strategy, targetCount: strategy.targetCount || task.targetCount }));
    integrations.saveRules(portableBundle(saved));
    return bundle;
  });
  ipcMain.handle("aipr:queue-outreach", (_event, payload) => integrations.enqueueOutreach(payload));
  ipcMain.handle("aipr:get-integration-paths", () => integrations.paths);
  ipcMain.handle("aipr:get-outreach-state", async () => {
    const task = currentTask();
    return outreachService.getState(task, task.outputDir || "");
  });
  ipcMain.handle("aipr:preview-outreach-authorization", (_event, payload = {}) => {
    const task = currentTask();
    return outreachService.preview(task, formalCreatorsForTask(task), payload.selectedIds || []);
  });
  ipcMain.handle("aipr:authorize-outreach-batch", (_event, previewId) => outreachService.authorize(String(previewId || "")));
  ipcMain.handle("aipr:sync-outreach-batch", (_event, batchId) => outreachService.sync(String(batchId || "")));
  ipcMain.handle("aipr:start-outreach-batch", (_event, payload = {}) => outreachService.start(String(payload.batchId || ""), {
    explicitUiClick: payload.explicitUiClick === true,
  }));
  ipcMain.handle("aipr:get-run-history", (_event, payload = {}) => {
    const taskId = String(payload.taskId || currentTask().id || "");
    return outreachService.getHistory(taskId, payload.limit || 100);
  });
}

function buildBootstrap() {
  let current = store.current() || defaultTask();
  if (!store.list().length) current = store.upsert(current);
  return buildTaskBootstrap(current);
}

function buildTaskBootstrap(selectedTask) {
  let current = restoreTaskTarget(withEmbeddedShops(selectedTask));
  current = { ...current, status: taskWorkerStatus(current, activeWorker, activeWorkerTaskId) };
  current = store.upsert(current);
  const deliveryPath = current.deliveryPath && fs.existsSync(current.deliveryPath) ? current.deliveryPath : "";
  const snapshot = readDeliverySnapshot(deliveryPath);
  if (deliveryPath && !snapshot) {
    current = store.upsert({ ...current, deliveryPath: "", lastContactPath: current.lastContactPath || deliveryPath });
  }
  if (snapshot) current = store.upsert(mergeTaskDeliverySnapshot(current,
    { deliveryPath, ...snapshot.metrics }, { preserveTarget: true }));
  current = restoreTaskTarget(current);
  if (current.endedAt && !collectionWorkerRunning(current, activeWorker, activeWorkerTaskId, activeWorkerAction)) current = store.upsert({...current, status: "ended"});
  if (current.outputDir) runHistory.recover(current.id, current.outputDir);
  const realtimeFlow = readRealtimeCreatorFlow(current.outputDir || "");
  const realtimeCandidates = realtimeFlow.candidateRows.map((row, index) => normalizeCreator(row, index));
  const realtimeFormal = realtimeFlow.formalRows.map((row, index) => normalizeCreator(row, index));
  if (realtimeFlow.available) {
    current = store.upsert({ ...current,
      collected: realtimeFlow.metrics.candidates,
      scored: realtimeFlow.metrics.suitable,
      plainContacts: realtimeFormal.length,
      wechat: realtimeFlow.metrics.wechat,
      phone: realtimeFlow.metrics.phone,
      status: current.status === "completed" && realtimeFormal.length < current.targetCount ? "paused" : current.status,
      remaining: Math.max(0, current.targetCount - realtimeFormal.length),
    });
  }
  let savedEvidenceReview;
  try { savedEvidenceReview = readCachedJson(path.join(current.outputDir, "aipr_saved_evidence_review.json")); } catch {}
  const effectiveFormal=contactCorrections.apply(current.id,realtimeFlow.available ? realtimeFormal : snapshot?.creators || []);
  const corrections=contactCorrections.read(current.id).records;
  const library=buildCreatorLibrary(store.list(), readDeliverySnapshot, task => {
    const live=readRealtimeCreatorFlow(task.outputDir || "");
    return live.available ? contactCorrections.apply(task.id,live.formalRows.map(normalizeCreator)) : null;
  });
  const findCurrentOwner=createIdentityResolver(effectiveFormal);
  library.creators=contactCorrections.apply(current.id,library.creators,effectiveFormal).map(row=>{const owner=findCurrentOwner(row);return owner ? {...row,canonicalTaskCreatorId:String(owner.id||owner.identity||""),contactCorrectionCreatorId:row.contactCorrectionCreatorId||String(owner.id||owner.identity||"")} : row;});
  const batchScope=readBatchScope(current);
  const batch= batchScope ? partitionBatch(effectiveFormal,batchScope.rows) : null;
  if(batch){
    const id=`${current.id}-batch-baseline`;
    library.batches.push({id,name:`${current.name} · 往期基线`,count:batch.historical.length,status:"ended",deliveryPath:batchScope.previousDeliveryPath,baselinePath:batchScope.baselinePath});
    const byIdentity=new Map();
    for(const row of library.creators)for(const identity of require("./batch-scope.cjs").identities(row))byIdentity.set(identity,row);
    for(const baseline of contactCorrections.apply(current.id,batch.historical)){
      const existing=[...require("./batch-scope.cjs").identities(baseline)].map(v=>byIdentity.get(v)).find(Boolean);
      if(existing){existing.libraryTaskIds=[...new Set([...(existing.libraryTaskIds||[]),id])];existing.libraryTaskNames=[...new Set([...(existing.libraryTaskNames||[]),`${current.name} · 往期基线`])];}
      else library.creators.push({...baseline,libraryTaskIds:[id],libraryTaskNames:[`${current.name} · 往期基线`]});
    }
  }

  return {
    savedEvidenceReview:reconcileContactReview(savedEvidenceReview,effectiveFormal),
    historicalWechatRepairCount: (()=>{try{return savedWechatRepairs(readCachedJson(path.join(current.outputDir,"aipr_strict_contact_highwater.json"))?.candidates||[],contactCorrections.apply(current.id,batch?.historical||[])).length;}catch{return 0;}})(),
    savedWechatRepairCount: (()=>{try{return savedWechatRepairs(readCachedJson(path.join(current.outputDir,"aipr_strict_contact_highwater.json"))?.candidates||[],batch ? batch.current : effectiveFormal).length;}catch{return 0;}})(),
    contactCorrections:corrections,
    contactRevisionPending:corrections.length>Number((snapshot ? readCachedJson(deliveryPath)?.contact_corrections_revision : 0)||0),
    appVersion: app.getVersion(),
    maintenance: {...maintenance},
    task: {...current,wechat:effectiveFormal.filter(c=>c.wechat).length,phone:effectiveFormal.filter(c=>c.phone).length},
    reviewRecords: reviews.read(current.id).records,
    tasks: store.list(),
    creatorLibrary: library,
    creators: batch ? batch.current : effectiveFormal,
    currentBatch:batchScope ? {id:batchScope.id,baselineCount:batchScope.baselineCount,newCount:batch.current.length,baselinePath:batchScope.baselinePath}:null,
    candidateCreators: contactCorrections.apply(current.id,realtimeFlow.available ? realtimeCandidates : snapshot?.candidateCreators || []),
    realtimeFlow: {
      available: realtimeFlow.available,
      updatedAt: realtimeFlow.updatedAt,
      metrics: realtimeFlow.metrics,
    },
    integrationPaths: integrations.paths,
    deliveryCenter: {...discoverDeliveryArtifacts(batchScope && !deliveryPath.startsWith(batchScope.outputDir+path.sep) ? "" : deliveryPath),validation:batchScope && !deliveryPath.startsWith(batchScope.outputDir+path.sep) ? null : readDeliveryValidation(current)},
    platformReadiness: platformReadiness(),
    jevStatus: jevStatus(),
    qwenStatus: require("./qwen-brief.cjs").status(),
    runHistory: runHistory.list(current.id, 30),
    runtimeMetrics: runHistory.timing(current.id,activeWorkerTaskId===current.id?activeWorkerSession:"",effectiveFormal.length),
    outreachBatches: outreachAuthorizations.list(current.id),
  };
}

function formalCreatorsForTask(task = {}) {
  const realtimeFlow = readRealtimeCreatorFlow(task.outputDir || "");
  if (realtimeFlow.available) {
    return contactCorrections.apply(task.id,realtimeFlow.formalRows.map((row, index) => normalizeCreator(row, index)));
  }
  return contactCorrections.apply(task.id,readDeliverySnapshot(task.deliveryPath)?.creators || []);
}

function restoreTaskTarget(task = {}) {
  const raw = Number(task.targetCount);
  const nameMatch = String(task.name || "").match(/(\d{1,5})\s*人/);
  const briefMatch = String(task.collectionStrategy?.brief || "").match(/(?:最终目标|目标|需要|跑)\s*(\d{1,5})\s*(?:个|人)/);
  const restored = Math.max(
    1,
    ...[
      raw,
      Number(nameMatch?.[1]),
      Number(briefMatch?.[1]),
      Number(task.collectionStrategy?.deliveryTargetCount),
      Number(task.collectionStrategy?.targetCount),
    ].filter((value) => Number.isFinite(value) && value > 0),
  );
  const targetCount = Math.min(5000, Math.max(1, restored || 500));
  if (raw === targetCount) return task;
  return store.upsert({
    ...task,
    targetCount,
    remaining: Math.max(0, targetCount - Number(task.plainContacts || 0)),
    collectionStrategy: task.collectionStrategy ? { ...task.collectionStrategy, targetCount } : task.collectionStrategy,
  });
}

function ensureTaskChangeAllowed() {
  if (activeWorker) throw new Error("任务运行中不能创建或切换品牌，请先暂停当前任务");
}

function deliveredIdentitiesExcluding(taskId, contacts = false) {
  const deliveries = [];
  const current=store.list().find(task=>task.id===taskId)||{id:taskId};
  const ownDeliveries=store.list().filter(task=>taskLineage(task)===taskLineage(current)&&task.deliveryPath&&fs.existsSync(task.deliveryPath)).map(task=>readCachedJson(task.deliveryPath));
  for (const savedTask of deliveryExclusionTasks(store.list(),taskId)) {
    if (savedTask.id === taskId || !savedTask.deliveryPath || !fs.existsSync(savedTask.deliveryPath)) continue;
    try {
      const data=readCachedJson(savedTask.deliveryPath);
      const relative=path.relative(savedTask.outputDir||"",savedTask.deliveryPath);
      const imported=savedTask.importedDeliveryPath===savedTask.deliveryPath || relative.startsWith(".."+path.sep) || path.isAbsolute(relative);
      deliveries.push(imported ? require("./delivery-exclusions.cjs").filterImportedCopies(data,ownDeliveries) : data);
    } catch {}
  }
  return contacts ? collectDeliveredContacts(deliveries) : collectDeliveredIdentities(deliveries);
}

function ownLineageDeliveryValues(taskId, contacts=false) {
  const current=store.list().find(task=>task.id===taskId)||{id:taskId};
  const deliveries=[];
  for(const task of store.list()){
    if(taskLineage(task)!==taskLineage(current)||!task.deliveryPath||!fs.existsSync(task.deliveryPath))continue;
    try{deliveries.push(readCachedJson(task.deliveryPath));}catch{}
  }
  return contacts?collectDeliveredContacts(deliveries):collectDeliveredIdentities(deliveries);
}

function readDeliverySnapshot(deliveryPath) {
  if (!deliveryPath || !fs.existsSync(deliveryPath)) return null;
  try {
    const payload = readCachedJson(deliveryPath);
    if (!Array.isArray(payload.rows)) return null;
    return normalizeDelivery(payload);
  } catch (error) {
    console.error(`Failed to read delivery snapshot: ${error.message}`);
    return null;
  }
}

function currentTask() {
  return buildBootstrap().task;
}

function defaultTask() {
  const outputDir = resolvePersistentTaskDir(documentsDir(), "brand-task");
  return {
    id: "brand-task",
    name: "新品牌达人任务",
    targetCount: 500,
    collected: 0,
    processed: 0,
    plainContacts: 0,
    wechat: 0,
    phone: 0,
    remaining: 500,
    contactDelayMs: 3200,
    status: "idle",
    rules: {
      threshold: 78,
      exclusions: ["母婴", "男性", "美食", "探店", "品牌店铺", "宠物"],
      weights: { persona: 28, content: 24, sales: 22, scene: 14, price: 12 },
    },
    outputDir,
    deliveryPath: "",
    queuePath: "",
    originalWorkbookPath: "",
    shops: {
      A: { label: "抖店 A", port: "内置", status: "unknown" },
      B: { label: "抖店 B", port: "内置", status: "unknown" },
    },
  };
}

function withEmbeddedShops(task = {}) {
  return {
    ...task,
    shops: Object.fromEntries(["A", "B"].map((shop) => [shop, {
      ...(task.shops?.[shop] || {}),
      label: String(task.shops?.[shop]?.label || `抖店 ${shop}`).slice(0, 60),
      port: "内置",
    }])),
  };
}

function documentsDir() {
  return process.env.AIPR_DOCUMENTS_DIR
    ? path.resolve(process.env.AIPR_DOCUMENTS_DIR)
    : app.getPath("documents");
}

function sanitizeTask(task = {}) {
  const safe = { ...task };
  safe.id = String(safe.id || `task-${Date.now()}`).replace(/[^a-zA-Z0-9_-]/g, "-");
  safe.name = String(safe.name || "未命名品牌任务").slice(0, 80);
  safe.contactDelayMs = Math.max(3000, Number(safe.contactDelayMs) || 3200);
  return safe;
}

function sanitizeCollectionStrategy(strategy = {}) {
  const levels = Array.isArray(strategy.creatorLevels) ? strategy.creatorLevels : [];
  const activeShops = [...new Set((Array.isArray(strategy.activeShops) ? strategy.activeShops : ["A", "B"])
    .map((shop) => String(shop).toUpperCase())
    .filter((shop) => shop === "A" || shop === "B") )];
  const result = {
    sourceType: String(strategy.sourceType || "brief").slice(0, 40),
    brief: String(strategy.brief || "").slice(0, 20000),
    viralExamples: String(strategy.viralExamples || "").slice(0, 10000),
    category: String(strategy.category || "泛生活好物").slice(0, 80),
    ...(strategy.contentFitCategory ? {contentFitCategory:String(strategy.contentFitCategory).slice(0,80)} : {}),
    creatorLevels: [...new Set(levels.map(Number).filter((level) => level >= 1 && level <= 4))],
    minimumFollowers: Math.max(0, Number(strategy.minimumFollowers) || 0),
    maximumFollowers: Math.max(0, strategy.maximumFollowers == null ? 500000 : Number(strategy.maximumFollowers) || 0),
    minimumMonthlySales: Math.max(0, Number(strategy.minimumMonthlySales) || 0),
    contentType: String(strategy.contentType || "短视频").slice(0, 40),
    requireContact: strategy.requireContact !== false,
    activeShops: activeShops.length ? activeShops : ["A"],
    keywords: [...new Set((strategy.keywords || []).map((item) => String(item).trim()).filter(Boolean))].slice(0, 200),
    exclusions: [...new Set((strategy.exclusions || []).map((item) => String(item).trim()).filter(Boolean))].slice(0, 30),
    targetCount: Math.min(5000, Math.max(1, Number(strategy.targetCount) || 500)),
    autoStart: true,
    applyMode: "next-batch",
  };
  for (const key of ["brandName", "productName", "sellingPoints", "criteria", "creatorType"]) if(strategy[key] !== undefined) result[key] = String(strategy[key]).slice(0,2000);
  result.contentPresentation = ["any","real_person","hands_only","product_only"].includes(strategy.contentPresentation) ? strategy.contentPresentation : "any";
  result.platformContentTopic = String(strategy.platformContentTopic || "").slice(0,80);
  result.contactCollectionMode = strategy.contactCollectionMode === "primary_wechat" ? "primary_wechat" : "all_channels";
  result.setupConfirmed = strategy.setupConfirmed === true;
  if(result.brandName)result.brand=result.brandName;
  if(result.productName)result.product_name=result.productName;
  for (const key of ["minimumUnderwearProductSales", "minimumLevel"]) {
    if (strategy[key] !== undefined && strategy[key] !== null && strategy[key] !== "") result[key] = Math.max(0, Number(strategy[key]) || 0);
  }
  for (const key of ["requireBodyMeasurements", "requireShapewearContent", "requirePlainContact", "requireFemale"]) {
    if (strategy[key] !== undefined) result[key] = strategy[key] !== false;
  }
  // 发现方式与分页/延时配置：缺失会导致 pipeline 走默认关键词路径，
  // 而类目搜索模式下 keywords 为空 → "collection strategy has no keywords"。
  const discovery = String(strategy.sourceDiscoveryMode || "structured_browse").toLowerCase();
  result.sourceDiscoveryMode = ["browse", "structured_browse", "filter_browse"].includes(discovery)
    ? "structured_browse"
    : "keyword_search";
  for (const key of ["sourceKeywordDelayMs", "sourcePageDelayMs", "sourceMaxPages",
                     "sourceBrowsePagesPerRun", "sourceBrowseMaxPages", "profileVisitIntervalMs",
                     "contactRevealIntervalMs", "contactDelayMs"]) {
    const n = Number(strategy[key]);
    if (Number.isFinite(n) && n > 0) result[key] = n;
  }
  // 跨批次去重清单：丢失会导致重复交付
  for (const key of ["excludeIdentities", "excludeContacts"]) {
    const list = Array.isArray(strategy[key]) ? strategy[key] : [];
    result[key] = [...new Set(list.map((item) => String(item).trim()).filter(Boolean))];
  }
  if (strategy.threshold != null) result.threshold = Math.min(100, Math.max(0, Number(strategy.threshold) || 0));
  for (const key of ["product_name", "brand"]) if (strategy[key]) result[key] = String(strategy[key]).slice(0, 200);
  // 实时流与去重模式
  result.realtimeCreatorFlow = strategy.realtimeCreatorFlow !== false;
  result.contactDedupMode = String(strategy.contactDedupMode || "strict-any-plaintext-value").slice(0, 60);
  return result;
}

function portableBundle(task) {
  return {
    schemaVersion: "1.0",
    exportedAt: new Date().toISOString(),
    application: "千寻",
    task: {
      id: task.id,
      name: task.name,
      targetCount: task.targetCount || 500,
      collectionStrategy: sanitizeCollectionStrategy({ ...(task.collectionStrategy || {}), targetCount: task.targetCount || 500 }),
    },
    rules: {
      ...(task.rules || {}),
      minimumContactDelayMs: Math.max(3000, Number(task.contactDelayMs) || 3200),
      requireVerifiedHomepage: true,
      requireVisualEvidence: true,
      preserveContactHighWater: true,
      exactFeeOnly: true,
    },
  };
}

function appPaths() {
  const resourcesPath = app.isPackaged ? process.resourcesPath : appRoot;
  const pythonExe = resolvePythonExecutable({
    platform: process.platform,
    arch: process.arch,
    resourcesPath,
    env: process.env,
    existsSync: fs.existsSync,
  });
  return {
    pythonExe,
    internalCdpPort,
    backendDir: app.isPackaged ? path.join(process.resourcesPath, "backend") : path.join(appRoot, "backend"),
  };
}

function jevStatus() { let connectionTest;try{connectionTest=readCachedJson(path.join(app.getPath("userData"),"jev-connection-test.json"));}catch{}return {...jevSettings.status(),connectionTest}; }

function platformReadiness() {
  const docs = documentsDir();
  let writable = false;
  try {
    fs.mkdirSync(docs, { recursive: true });
    fs.accessSync(docs, fs.constants.W_OK);
    writable = true;
  } catch {}
  return buildPlatformReadiness({
    platform: process.platform,
    arch: process.arch,
    pythonExe: appPaths().pythonExe,
    browserExe: resolveBrowserExecutable({ platform: process.platform, env: process.env, existsSync: fs.existsSync }),
    embeddedBrowserAvailable: Boolean(embeddedShopViews.A && !embeddedShopViews.A.webContents.isDestroyed() && embeddedShopViews.B && !embeddedShopViews.B.webContents.isDestroyed()),
    documentsDir: docs,
    writable,
  });
}

function runWorker(action, task) {
  if(maintenance.busy)return {ok:false,error:"数据维护正在进行，请稍后启动作业"};
  if (activeWorker) return { ok: false, error: "已有任务正在运行" };
  let command;
  try {
    command = buildWorkerCommand(action, task, appPaths());
  } catch (error) {
    return { ok: false, error: error.message };
  }
  const cwd = resolveWorkerCwd(task.outputDir, app.getPath("userData"));
  fs.mkdirSync(cwd, { recursive: true });
  const workerTaskId = task.id || "brand-task";
  let apiKey = "";
  try { if (["collect-creators", "contact-icons"].includes(action)) apiKey = jevSettings.getApiKey(); }
  catch (error) { return {ok:false,error:error.message}; }
  const workerProcess = spawn(command.command, command.args, {
    shell: false,
    env: {...process.env, AIPR_TASK_ID: workerTaskId, AIPR_CONTACT_CORRECTIONS: ["apply-saved-audit", "audit-saved-list","deliver-current","collect-creators","contact-icons"].includes(action) ? contactCorrections.file(workerTaskId) : "", AIPR_JEV_API_KEY: apiKey, ...(["review-saved", "verify-saved-contacts"].includes(action) ? {JEV_INTEGRATION:"0",AIPR_JEV_SAVED_ONLY:"1"} : {}), ...(["deliver-current", "audit-saved-list", "apply-saved-audit"].includes(action) ? {AIPR_JEV_SAVED_ONLY:"1"} : {})},
    windowsHide: process.platform === "win32",
    // Give each POSIX worker its own process group. The pipeline launches
    // evidence/contact subprocesses, so pause/quit must terminate the whole
    // task group instead of leaving children alive to overwrite high-water data.
    detached: process.platform !== "win32",
    cwd,
  });
  activeWorker = workerProcess;
  activeWorkerTaskId = workerTaskId;
  activeWorkerAction = action;
  activeWorkerSession=`${Date.now()}-${workerProcess.pid}`;
  emitWorker({type:"worker-started",timingVersion:1,listedBaseline:(()=>{const live=readRealtimeCreatorFlow(task.outputDir || "");return require("./runtime-metrics.cjs").collectionBaseline({liveFormal:live.available?live.formalRows.length:0,savedFormal:task.plainContacts,deliveredFormal:readDeliverySnapshot(task.deliveryPath)?.metrics?.plainContacts});})(),taskId:workerTaskId});
  if (["collect-creators", "contact-icons"].includes(action)) {
    const saved = store.current();
    store.upsert({...saved, endedAt: "", endedReason: ""});
  }
  if (["audit-saved-list", "apply-saved-audit"].includes(action)) persistTaskStatus(workerTaskId, "running");
  if (!["apply-saved-audit", "audit-saved-list", "probe-login", "export-original", "deliver-current", "review-saved", "verify-saved-contacts"].includes(action)) persistTaskStatus(workerTaskId, "running");
  streamLines(workerProcess.stdout, (line) => emitWorker({ ...classifyWorkerEvent(line), taskId: workerTaskId }));
  streamLines(workerProcess.stderr, (line) => emitWorker({ type: "log", message: line, taskId: workerTaskId }));
  workerProcess.on("error", (error) => {
    emitWorker({ type: "error", workerAction: action, message: error.message, taskId: workerTaskId });
    clearWorker(workerProcess, workerTaskId);
  });
  workerProcess.on("close", (code) => {
    if (activeWorker !== workerProcess) return;
    emitWorker({ type: "finished", code, workerAction: action, taskId: workerTaskId });
    clearWorker(workerProcess, workerTaskId);
  });
  return { ok: true, status: "running", pid: workerProcess.pid, taskId: workerTaskId };
}

function clearWorker(workerProcess, workerTaskId) {
  if (activeWorker !== workerProcess) return;
  activeWorker = null;
  activeWorkerAction = "";
  activeWorkerSession = "";
  if (activeWorkerTaskId === workerTaskId) activeWorkerTaskId = "";
}

function persistTaskStatus(taskId, status) {
  if (!taskId || !store) return;
  const saved = store.list().find((task) => task.id === taskId);
  if (saved) store.upsert({ ...saved, status, updatedAt: new Date().toISOString() });
}

function streamLines(stream, listener) {
  if (!stream) return;
  let buffer = "";
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    buffer += chunk;
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || "";
    lines.filter(Boolean).forEach(listener);
  });
}

function emitWorker(payload) {
  payload={workerAction:activeWorkerAction,workerSession:activeWorkerSession,...payload};
  persistWorkerEvent(payload);
  if (payload.taskId) runHistory?.append(payload.taskId, payload);
  mainWindow?.webContents.send("aipr:worker-event", payload);
}

function persistWorkerEvent(payload = {}) {
  if (!payload.taskId || !store) return;
  const saved = store.list().find((task) => task.id === payload.taskId);
  if (!saved) return;
  let incoming = {};
  if(payload.status==="original_export_finished" && payload.workerAction==="export-original" && payload.output){
    incoming.originalExport={path:String(payload.output),deliveryPath:saved.deliveryPath,sourceWorkbookPath:saved.originalWorkbookPath,createdAt:new Date().toISOString()};
  }
  if (["collection_progress", "collection_browse_progress"].includes(payload.status)) incoming.collected = payload.candidate_count;
  if (payload.status === "realtime_creator_progress") {
    incoming.collected = payload.discovered_count;
    incoming.processed = payload.terminal_count;
    incoming.scored = payload.suitable_count;
    incoming.plainContacts = payload.listed_count;
  }
  if (payload.status === "evidence_progress") {
    incoming.processed = payload.evidence_highwater_count || payload.processed;
    incoming.scored = payload.evidence_verified_count;
  }
  if (payload.type === "contact-summary") {
    incoming = {
      ...incoming,
      processed: payload.candidate_count,
      plainContacts: payload.qualified_plain_contact_count ?? payload.plain_contact_count,
      wechat: payload.qualified_wechat_contact_count ?? payload.wechat_contact_count,
      phone: payload.qualified_phone_contact_count ?? payload.phone_contact_count,
      lastContactPath: payload.output || saved.lastContactPath,
    };
  }
  if (payload.type === "login-summary" && payload.shops) {
    incoming.shops = Object.fromEntries(["A", "B"].map((shop) => {
      const result = payload.shops[shop] || {};
      return [shop, {
        label: saved.shops?.[shop]?.label || `抖店 ${shop}`,
        checkedAt: new Date().toISOString(),
        port: "内置",
        status: result.merchant_logged_in && result.buyin_ready ? "connected" : "disconnected",
      }];
    }));
  }
  if (["audit-saved-list", "apply-saved-audit"].includes(payload.workerAction) && ["finished", "error"].includes(payload.type)) incoming.status = "paused";
  if (payload.type === "delivery-ready" && payload.output) incoming.deliveryPath = payload.output;
  if (["paused","error"].includes(payload.type) && !["apply-saved-audit", "audit-saved-list", "probe-login", "export-original", "deliver-current", "review-saved", "verify-saved-contacts"].includes(payload.workerAction)) incoming.status = "paused";
  const continuingCollectionStatus = collectionEventStatus(payload, Boolean(activeWorker && activeWorkerTaskId === payload.taskId && activeWorker.exitCode == null && activeWorker.signalCode == null));
  if (continuingCollectionStatus) incoming.status = continuingCollectionStatus;
  if (payload.type === "finished" && !["apply-saved-audit", "audit-saved-list", "probe-login", "export-original", "deliver-current", "review-saved", "verify-saved-contacts"].includes(payload.workerAction)) {
    incoming.status = payload.code === 0 ? "completed" : "paused";
  }
  if (Object.keys(incoming).length) store.upsert(mergeTaskHighWater(saved, incoming));
}

function launchDualBrowsers() {
  ensureEmbeddedShopViews();
  return {
    ok: true,
    mode: "embedded",
    endpoint: `http://127.0.0.1:${internalCdpPort}`,
    shops: { A: "embedded", B: "embedded" },
  };
}

function ensureEmbeddedShopViews() {
  if (!mainWindow || mainWindow.isDestroyed()) return embeddedShopViews;
  const startupLoads = [];
  for (const shop of ["A", "B"]) {
    if (embeddedShopViews[shop] && !embeddedShopViews[shop].webContents.isDestroyed()) continue;
    const view = new WebContentsView({
      webPreferences: {
        partition: `persist:aipr-shop-${shop.toLowerCase()}`,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
      },
    });
    embeddedShopViews[shop] = view;
    const shopSession = view.webContents.session;
    let saveTimer;
    shopSession.cookies.on("changed", () => {
      clearTimeout(saveTimer);
      saveTimer = setTimeout(() => flushShopSession(shopSession).catch(() => {}), 500);
      saveTimer.unref?.();
    });
    // Do not expose the Electron/app product tokens to the commerce platform.
    // The embedded view uses the same Chromium engine, so advertise the
    // matching standard Chrome UA consistently at both session and page level.
    view.webContents.session.setUserAgent(embeddedChromeUserAgent, "zh-CN,zh;q=0.9,en;q=0.8");
    view.webContents.setUserAgent(embeddedChromeUserAgent);
    mainWindow.contentView.addChildView(view);
    setShopViewLayout(view, false);
    const emit = (type, extra = {}) => mainWindow?.webContents.send("aipr:shop-browser-event", {
      shop,
      type,
      url: view.webContents.getURL(),
      ...extra,
    });
    view.webContents.on("did-start-loading", () => emit("loading"));
    view.webContents.on("did-finish-load", () => {
      view.webContents.executeJavaScript(`window.name = ${JSON.stringify(`AIPR_SHOP_${shop}`)}`).catch(() => {});
    });
    view.webContents.on("did-stop-loading", () => {
      flushShopSession(shopSession).catch(() => {});
      emit("ready");
    });
    view.webContents.on("did-navigate", (_event, url) => emit("navigate", { url }));
    view.webContents.on("did-navigate-in-page", (_event, url) => emit("navigate", { url }));
    view.webContents.setWindowOpenHandler(({ url }) => {
      if (/^https?:\/\//i.test(url)) view.webContents.loadURL(url);
      return { action: "deny" };
    });
    view.webContents.on("did-fail-load", (_event, code, description) => {
      if (code !== -3) emit("failed", { code, description });
    });
    const recoverCrash = createShopCrashRecovery(view.webContents, { emit });
    view.webContents.on("render-process-gone", (_event, details) => {
      if (!sessionQuitPending) void recoverCrash(details);
    });
    startupLoads.push((async () => {
      const route = await shopSession.resolveProxy("https://lianmengapi.snssdk.com");
      if (/^PROXY 127\.0\.0\.1:7897(?:;|$)/.test(route)) {
        await shopSession.setProxy({ mode: "fixed_servers", proxyRules: "127.0.0.1:7897", proxyBypassRules: "<local>;127.0.0.1;192.168.0.0/16;10.0.0.0/8;172.16.0.0/12;*.local;*.crashlytics.com;lianmengapi.snssdk.com" });
      }
      return view.webContents.loadURL("https://fxg.jinritemai.com/ffa/mshop/homepage/index");
    })());
  }
  if (startupLoads.length && !embeddedStartupProbeScheduled) {
    embeddedStartupProbeScheduled = true;
    Promise.allSettled(startupLoads).then(() => {
      if (!sessionQuitPending && !activeWorker && mainWindow && !mainWindow.isDestroyed()) {
        try { runWorker("probe-login", currentTask()); } catch (error) {
          console.warn("Startup login verification could not start:", error.message);
        }
      }
    });
  }
  return embeddedShopViews;
}

function layoutEmbeddedShop(payload = {}) {
  if(!Number.isSafeInteger(payload.epoch) || payload.epoch < shopLayoutEpoch)return {ok:false,error:"stale_layout"};
  shopLayoutEpoch=payload.epoch;
  const views = ensureEmbeddedShopViews();
  const shop = payload.shop === "B" ? "B" : "A";
  const bounds = payload.bounds || {};
  const next = {
    x: Math.max(0, Math.round(Number(bounds.x) || 0)),
    y: Math.max(0, Math.round(Number(bounds.y) || 0)),
    width: Math.max(1, Math.round(Number(bounds.width) || 0)),
    height: Math.max(1, Math.round(Number(bounds.height) || 0)),
  };
  for (const key of ["A", "B"]) {
    const active = key === shop;
    setShopViewLayout(views[key], active, next);
  }
  return { ok: true, shop, bounds: next, url: views[shop]?.webContents.getURL() || "" };
}

function hideEmbeddedShopViews(payload = {}) {
  if(Number.isSafeInteger(payload.epoch)){if(payload.epoch < shopLayoutEpoch)return {ok:false,error:"stale_layout"};shopLayoutEpoch=payload.epoch;}
  for (const view of Object.values(embeddedShopViews)) {
    setShopViewLayout(view, false);
  }
  return { ok: true };
}

function controlEmbeddedShop(payload = {}) {
  const shop = payload.shop === "B" ? "B" : "A";
  const view = ensureEmbeddedShopViews()[shop];
  if (!view) return { ok: false, error: "embedded_shop_unavailable" };
  const action = String(payload.action || "");
  if (action === "back" && view.webContents.canGoBack()) view.webContents.goBack();
  else if (action === "forward" && view.webContents.canGoForward()) view.webContents.goForward();
  else if (action === "reload") view.webContents.reload();
  else if (action === "navigate") {
    const raw = String(payload.url || "").trim();
    if (raw) view.webContents.loadURL(raw.startsWith("http") ? raw : `https://${raw}`);
  }
  return { ok: true, url: view.webContents.getURL() };
}

function destroyEmbeddedShopViews() {
  for (const shop of ["A", "B"]) {
    const view = embeddedShopViews[shop];
    if (!view) continue;
    try { view.webContents.close(); } catch {}
    embeddedShopViews[shop] = null;
  }
}

function readDeliveryValidation(task) {
 try{
  const report=JSON.parse(fs.readFileSync(path.join(app.getPath("userData"),"delivery-validation",task.id+".json"),"utf8"));
  if(report.sourcePath!==task.deliveryPath)return null;
  return {...report,stale:(report.files||[]).some(file=>{try{const stat=fs.statSync(file.path,{bigint:true});return String(stat.mtimeNs)!==file.modified_ns||Number(stat.size)!==file.size;}catch{return true;}})};
 }catch{return null;}
}
