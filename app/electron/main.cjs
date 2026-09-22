const { app, BrowserWindow, WebContentsView, clipboard, dialog, ipcMain, shell } = require("electron");
const fs = require("node:fs");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");
const { TaskStore } = require("./task-store.cjs");
const { mergeTaskDeliverySnapshot, mergeTaskHighWater } = require("./task-high-water.cjs");
const { collectDeliveredIdentities } = require("./delivery-exclusions.cjs");
const { mergeRuntimeCollectionStrategy } = require("./collection-strategy-runtime.cjs");
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
  buildPlatformReadiness,
  resolveBrowserExecutable,
  resolvePythonExecutable,
  resolveWorkerCwd,
} = require("./platform-runtime.cjs");

let mainWindow;
let activeWorker;
let activeWorkerTaskId = "";
let store;
let integrations;
let runHistory;
let outreachAuthorizations;
let outreachService;
const embeddedShopViews = { A: null, B: null };
const appRoot = path.resolve(__dirname, "..");
const internalCdpPort = Math.max(1024, Number(process.env.AIPR_INTERNAL_CDP_PORT) || 9222);
const chromeMajorVersion = String(process.versions.chrome || "150").split(".")[0];
const embeddedChromeUserAgent = `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${chromeMajorVersion}.0.0.0 Safari/537.36`;

app.setName("AIPR Pro 达人运营系统");
if (process.env.AIPR_USER_DATA_DIR) app.setPath("userData", path.resolve(process.env.AIPR_USER_DATA_DIR));
app.commandLine.appendSwitch("remote-debugging-address", "127.0.0.1");
app.commandLine.appendSwitch("remote-debugging-port", String(internalCdpPort));
app.whenReady().then(() => {
  const userData = app.getPath("userData");
  store = new TaskStore(userData);
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
app.on("window-all-closed", () => process.platform !== "darwin" && app.quit());
app.on("before-quit", () => terminateProcessTree(activeWorker));

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1480,
    height: 980,
    minWidth: 1080,
    minHeight: 720,
    backgroundColor: "#f2f4f2",
    title: "AIPR Pro 达人运营系统",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      webviewTag: true,
    },
  });
  if (app.isPackaged) mainWindow.loadFile(path.join(appRoot, "dist", "index.html"));
  else mainWindow.loadURL("http://127.0.0.1:4173");
  mainWindow.webContents.once("did-finish-load", () => ensureEmbeddedShopViews());
  mainWindow.on("closed", destroyEmbeddedShopViews);
}

function registerIpc() {
  ipcMain.handle("aipr:get-bootstrap", () => buildBootstrap());
  ipcMain.handle("aipr:get-realtime-creator-flow", () => {
    const task = store.current() || defaultTask();
    return readRealtimeCreatorFlow(task.outputDir || "");
  });
  ipcMain.handle("aipr:get-platform-readiness", () => platformReadiness());
  ipcMain.handle("aipr:list-tasks", () => ({
    currentTaskId: store.read().currentTaskId,
    tasks: store.list(),
  }));
  ipcMain.handle("aipr:create-task", (_event, payload = {}) => {
    ensureTaskChangeAllowed();
    const clean = sanitizeTask({ ...defaultTask(), ...payload });
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
  ipcMain.handle("aipr:save-task", (_event, task) => {
    const saved = store.upsert(withEmbeddedShops(sanitizeTask(task)));
    if (saved.rules) integrations.saveRules(portableBundle(saved));
    return saved;
  });
  ipcMain.handle("aipr:import-file", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ["openFile"],
      filters: [{ name: "达人名单", extensions: ["xlsx", "xls", "csv", "json"] }],
    });
    return result.canceled ? null : result.filePaths[0];
  });
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
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ["openFile"],
      filters: [{ name: "AIPR 交付数据", extensions: ["json"] }],
    });
    if (result.canceled || !result.filePaths[0]) return null;
    const deliveryPath = result.filePaths[0];
    const snapshot = readDeliverySnapshot(deliveryPath);
    if (!snapshot) throw new Error("无法读取所选交付数据");
    const task = mergeTaskDeliverySnapshot(currentTask(), { deliveryPath, ...snapshot.metrics });
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
  ipcMain.handle("aipr:hide-embedded-shops", () => hideEmbeddedShopViews());
  ipcMain.handle("aipr:control-embedded-shop", (_event, payload = {}) => controlEmbeddedShop(payload));
  ipcMain.handle("aipr:probe-login", () => runWorker("probe-login", currentTask()));
  ipcMain.handle("aipr:start-collection", (_event, payload = {}) => {
    ensureEmbeddedShopViews();
    const task = sanitizeTask(payload.task || currentTask());
    const taskDir = resolvePersistentTaskDir(documentsDir(), task.id);
    fs.mkdirSync(taskDir, { recursive: true });
    const strategyPath = path.join(taskDir, "collection-strategy.json");
    let existingStrategy = {};
    try {
      if (fs.existsSync(strategyPath)) existingStrategy = JSON.parse(fs.readFileSync(strategyPath, "utf8"));
    } catch {
      existingStrategy = {};
    }
    const strategy = mergeRuntimeCollectionStrategy({
      base: sanitizeCollectionStrategy(payload.strategy || {}),
      existing: existingStrategy,
      deliveredIdentities: deliveredIdentitiesExcluding(task.id),
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
  ipcMain.handle("aipr:pause-worker", () => {
    persistTaskStatus(activeWorkerTaskId, "paused");
    const stopped = terminateProcessTree(activeWorker);
    activeWorker = null;
    activeWorkerTaskId = "";
    return { ok: stopped, status: stopped ? "paused" : "stop_failed" };
  });
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
      filters: [{ name: "AIPR 规则配置", extensions: ["json"] }],
    });
    if (result.canceled || !result.filePath) return null;
    fs.writeFileSync(result.filePath, JSON.stringify(bundle, null, 2), "utf8");
    integrations.saveRules(bundle);
    return result.filePath;
  });
  ipcMain.handle("aipr:import-rules", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ["openFile"],
      filters: [{ name: "AIPR 规则配置", extensions: ["json"] }],
    });
    if (result.canceled) return null;
    const bundle = JSON.parse(fs.readFileSync(result.filePaths[0], "utf8"));
    integrations.saveRules(bundle);
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
  current = store.upsert(current);
  const deliveryPath = current.deliveryPath && fs.existsSync(current.deliveryPath) ? current.deliveryPath : "";
  const snapshot = readDeliverySnapshot(deliveryPath);
  if (deliveryPath && !snapshot) {
    current = store.upsert({ ...current, deliveryPath: "", lastContactPath: current.lastContactPath || deliveryPath });
  }
  if (snapshot) current = store.upsert(mergeTaskDeliverySnapshot(current, { deliveryPath, ...snapshot.metrics }));
  current = restoreTaskTarget(current);
  if (current.outputDir) runHistory.recover(current.id, current.outputDir);
  const realtimeFlow = readRealtimeCreatorFlow(current.outputDir || "");
  const realtimeCandidates = realtimeFlow.candidateRows.map((row, index) => normalizeCreator(row, index));
  const realtimeFormal = realtimeFlow.formalRows.map((row, index) => normalizeCreator(row, index));
  return {
    task: current,
    tasks: store.list(),
    creators: realtimeFlow.available ? realtimeFormal : snapshot?.creators || [],
    candidateCreators: realtimeFlow.available ? realtimeCandidates : snapshot?.candidateCreators || [],
    realtimeFlow: {
      available: realtimeFlow.available,
      updatedAt: realtimeFlow.updatedAt,
      metrics: realtimeFlow.metrics,
    },
    integrationPaths: integrations.paths,
    deliveryCenter: discoverDeliveryArtifacts(deliveryPath),
    platformReadiness: platformReadiness(),
    runHistory: runHistory.list(current.id, 30),
    outreachBatches: outreachAuthorizations.list(current.id),
  };
}

function formalCreatorsForTask(task = {}) {
  const realtimeFlow = readRealtimeCreatorFlow(task.outputDir || "");
  if (realtimeFlow.available) {
    return realtimeFlow.formalRows.map((row, index) => normalizeCreator(row, index));
  }
  return readDeliverySnapshot(task.deliveryPath)?.creators || [];
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

function deliveredIdentitiesExcluding(taskId) {
  const deliveries = [];
  for (const savedTask of store.list()) {
    if (savedTask.id === taskId || !savedTask.deliveryPath || !fs.existsSync(savedTask.deliveryPath)) continue;
    try {
      deliveries.push(JSON.parse(fs.readFileSync(savedTask.deliveryPath, "utf8")));
    } catch {}
  }
  return collectDeliveredIdentities(deliveries);
}

function readDeliverySnapshot(deliveryPath) {
  if (!deliveryPath || !fs.existsSync(deliveryPath)) return null;
  try {
    const payload = JSON.parse(fs.readFileSync(deliveryPath, "utf8"));
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
      label: `抖店 ${shop}`,
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
    creatorLevels: [...new Set(levels.map(Number).filter((level) => level >= 1 && level <= 4))],
    minimumFollowers: Math.max(0, Number(strategy.minimumFollowers) || 0),
    maximumFollowers: Math.max(0, Number(strategy.maximumFollowers) || 500000),
    minimumMonthlySales: Math.max(0, Number(strategy.minimumMonthlySales) || 0),
    contentType: String(strategy.contentType || "短视频").slice(0, 40),
    requireContact: strategy.requireContact !== false,
    activeShops: activeShops.length ? activeShops : ["A"],
    keywords: [...new Set((strategy.keywords || []).map((item) => String(item).trim()).filter(Boolean))].slice(0, 20),
    exclusions: [...new Set((strategy.exclusions || []).map((item) => String(item).trim()).filter(Boolean))].slice(0, 30),
    targetCount: Math.min(5000, Math.max(1, Number(strategy.targetCount) || 500)),
    autoStart: true,
    applyMode: "next-batch",
  };
  for (const key of ["minimumUnderwearProductSales", "minimumLevel"]) {
    if (strategy[key] !== undefined && strategy[key] !== null && strategy[key] !== "") result[key] = Math.max(0, Number(strategy[key]) || 0);
  }
  for (const key of ["requireBodyMeasurements", "requireShapewearContent", "requirePlainContact"]) {
    if (strategy[key] !== undefined) result[key] = strategy[key] !== false;
  }
  // 发现方式与分页/延时配置：缺失会导致 pipeline 走默认关键词路径，
  // 而类目搜索模式下 keywords 为空 → "collection strategy has no keywords"。
  const discovery = String(strategy.sourceDiscoveryMode || "structured_browse").toLowerCase();
  result.sourceDiscoveryMode = ["browse", "structured_browse", "filter_browse"].includes(discovery)
    ? "structured_browse"
    : "keyword_search";
  for (const key of ["sourceKeywordDelayMs", "sourcePageDelayMs", "sourceMaxPages",
                     "sourceBrowsePagesPerRun", "sourceBrowseMaxPages"]) {
    const n = Number(strategy[key]);
    if (Number.isFinite(n) && n > 0) result[key] = n;
  }
  // 跨批次去重清单：丢失会导致重复交付
  for (const key of ["excludeIdentities", "excludeContacts"]) {
    const list = Array.isArray(strategy[key]) ? strategy[key] : [];
    result[key] = [...new Set(list.map((item) => String(item).trim()).filter(Boolean))];
  }
  // 实时流与去重模式
  result.realtimeCreatorFlow = strategy.realtimeCreatorFlow !== false;
  result.contactDedupMode = String(strategy.contactDedupMode || "strict-any-plaintext-value").slice(0, 60);
  return result;
}

function portableBundle(task) {
  return {
    schemaVersion: "1.0",
    exportedAt: new Date().toISOString(),
    application: "AIPR Pro 达人运营系统",
    task: {
      id: task.id,
      name: task.name,
      targetCount: task.targetCount || 500,
      collectionStrategy: sanitizeCollectionStrategy(task.collectionStrategy || {}),
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
    backendDir: app.isPackaged ? path.join(process.resourcesPath, "backend") : path.join(appRoot, "backend"),
  };
}

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
    documentsDir: docs,
    writable,
  });
}

function runWorker(action, task) {
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
  const workerProcess = spawn(command.command, command.args, {
    shell: false,
    windowsHide: process.platform === "win32",
    // Give each POSIX worker its own process group. The pipeline launches
    // evidence/contact subprocesses, so pause/quit must terminate the whole
    // task group instead of leaving children alive to overwrite high-water data.
    detached: process.platform !== "win32",
    cwd,
  });
  activeWorker = workerProcess;
  activeWorkerTaskId = workerTaskId;
  persistTaskStatus(workerTaskId, "running");
  streamLines(workerProcess.stdout, (line) => emitWorker({ ...classifyWorkerEvent(line), taskId: workerTaskId }));
  streamLines(workerProcess.stderr, (line) => emitWorker({ type: "log", message: line, taskId: workerTaskId }));
  workerProcess.on("error", (error) => {
    emitWorker({ type: "error", message: error.message, taskId: workerTaskId });
    clearWorker(workerProcess, workerTaskId);
  });
  workerProcess.on("exit", (code) => {
    emitWorker({ type: "finished", code, taskId: workerTaskId });
    clearWorker(workerProcess, workerTaskId);
  });
  return { ok: true, status: "running", pid: workerProcess.pid, taskId: workerTaskId };
}

function clearWorker(workerProcess, workerTaskId) {
  if (activeWorker === workerProcess) activeWorker = null;
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
  persistWorkerEvent(payload);
  if (payload.taskId) runHistory?.append(payload.taskId, payload);
  mainWindow?.webContents.send("aipr:worker-event", payload);
}

function persistWorkerEvent(payload = {}) {
  if (!payload.taskId || !store) return;
  const saved = store.list().find((task) => task.id === payload.taskId);
  if (!saved) return;
  let incoming = {};
  if (payload.status === "collection_progress") incoming.collected = payload.candidate_count;
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
        label: `抖店 ${shop}`,
        port: "内置",
        status: result.merchant_logged_in && result.buyin_ready ? "connected" : "disconnected",
      }];
    }));
  }
  if (payload.type === "delivery-ready" && payload.output) incoming.deliveryPath = payload.output;
  if (payload.type === "paused") incoming.status = "paused";
  if (payload.type === "finished") incoming.status = payload.code === 0 ? "completed" : "paused";
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
    // Do not expose the Electron/app product tokens to the commerce platform.
    // The embedded view uses the same Chromium engine, so advertise the
    // matching standard Chrome UA consistently at both session and page level.
    view.webContents.session.setUserAgent(embeddedChromeUserAgent, "zh-CN,zh;q=0.9,en;q=0.8");
    view.webContents.setUserAgent(embeddedChromeUserAgent);
    mainWindow.contentView.addChildView(view);
    view.setVisible(false);
    view.setBounds({ x: 0, y: 0, width: 0, height: 0 });
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
    view.webContents.on("did-stop-loading", () => emit("ready"));
    view.webContents.on("did-navigate", (_event, url) => emit("navigate", { url }));
    view.webContents.on("did-navigate-in-page", (_event, url) => emit("navigate", { url }));
    view.webContents.setWindowOpenHandler(({ url }) => {
      if (/^https?:\/\//i.test(url)) view.webContents.loadURL(url);
      return { action: "deny" };
    });
    view.webContents.on("did-fail-load", (_event, code, description) => {
      if (code !== -3) emit("failed", { code, description });
    });
    view.webContents.on("render-process-gone", (_event, details) => emit("failed", { description: details.reason }));
    view.webContents.loadURL("https://fxg.jinritemai.com/login?from=buyin");
  }
  return embeddedShopViews;
}

function layoutEmbeddedShop(payload = {}) {
  const views = ensureEmbeddedShopViews();
  const shop = payload.shop === "B" ? "B" : "A";
  const bounds = payload.bounds || {};
  const next = {
    x: Math.max(0, Math.round(Number(bounds.x) || 0)),
    y: Math.max(0, Math.round(Number(bounds.y) || 0)),
    width: Math.max(320, Math.round(Number(bounds.width) || 0)),
    height: Math.max(240, Math.round(Number(bounds.height) || 0)),
  };
  for (const key of ["A", "B"]) {
    const active = key === shop;
    views[key]?.setVisible(active);
    views[key]?.setBounds(active ? next : { x: 0, y: 0, width: 0, height: 0 });
  }
  return { ok: true, shop, bounds: next, url: views[shop]?.webContents.getURL() || "" };
}

function hideEmbeddedShopViews() {
  for (const view of Object.values(embeddedShopViews)) {
    view?.setVisible(false);
    view?.setBounds({ x: 0, y: 0, width: 0, height: 0 });
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
