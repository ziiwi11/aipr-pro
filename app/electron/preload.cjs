const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("aiprDesktop", {
  getBootstrap: () => ipcRenderer.invoke("aipr:get-bootstrap"),
  getRealtimeCreatorFlow: () => ipcRenderer.invoke("aipr:get-realtime-creator-flow"),
  getPlatformReadiness: () => ipcRenderer.invoke("aipr:get-platform-readiness"),
  listTasks: () => ipcRenderer.invoke("aipr:list-tasks"),
  createTask: (task) => ipcRenderer.invoke("aipr:create-task", task),
  selectTask: (taskId) => ipcRenderer.invoke("aipr:select-task", taskId),
  saveTask: (task) => ipcRenderer.invoke("aipr:save-task", task),
  importFile: () => ipcRenderer.invoke("aipr:import-file"),
  importBrief: () => ipcRenderer.invoke("aipr:import-brief"),
  importDelivery: () => ipcRenderer.invoke("aipr:import-delivery"),
  loadDeliveryPath: (target) => ipcRenderer.invoke("aipr:load-delivery-path", target),
  launchBrowsers: () => ipcRenderer.invoke("aipr:launch-browsers"),
  layoutEmbeddedShop: (payload) => ipcRenderer.invoke("aipr:layout-embedded-shop", payload),
  hideEmbeddedShops: () => ipcRenderer.invoke("aipr:hide-embedded-shops"),
  controlEmbeddedShop: (payload) => ipcRenderer.invoke("aipr:control-embedded-shop", payload),
  probeLogin: () => ipcRenderer.invoke("aipr:probe-login"),
  startCollection: (task, strategy) => ipcRenderer.invoke("aipr:start-collection", { task, strategy }),
  startWorker: (task) => ipcRenderer.invoke("aipr:start-worker", task),
  pauseWorker: () => ipcRenderer.invoke("aipr:pause-worker"),
  exportOriginal: (task) => ipcRenderer.invoke("aipr:export-original", task),
  openPath: (target) => ipcRenderer.invoke("aipr:open-path", target),
  getDeliveryCenter: (target) => ipcRenderer.invoke("aipr:get-delivery-center", target),
  previewRobotHandoff: (target) => ipcRenderer.invoke("aipr:preview-robot-handoff", target),
  copyText: (value) => ipcRenderer.invoke("aipr:copy-text", value),
  exportRules: (task) => ipcRenderer.invoke("aipr:export-rules", task),
  importRules: () => ipcRenderer.invoke("aipr:import-rules"),
  queueOutreach: (payload) => ipcRenderer.invoke("aipr:queue-outreach", payload),
  getIntegrationPaths: () => ipcRenderer.invoke("aipr:get-integration-paths"),
  getOutreachState: () => ipcRenderer.invoke("aipr:get-outreach-state"),
  previewOutreachAuthorization: (selectedIds) => ipcRenderer.invoke("aipr:preview-outreach-authorization", { selectedIds }),
  authorizeOutreachBatch: (previewId) => ipcRenderer.invoke("aipr:authorize-outreach-batch", previewId),
  syncOutreachBatch: (batchId) => ipcRenderer.invoke("aipr:sync-outreach-batch", batchId),
  startOutreachBatch: (batchId) => ipcRenderer.invoke("aipr:start-outreach-batch", { batchId, explicitUiClick: true }),
  getRunHistory: (taskId, limit = 100) => ipcRenderer.invoke("aipr:get-run-history", { taskId, limit }),
  onWorkerEvent: (listener) => {
    const handler = (_event, payload) => listener(payload);
    ipcRenderer.on("aipr:worker-event", handler);
    return () => ipcRenderer.removeListener("aipr:worker-event", handler);
  },
  onShopBrowserEvent: (listener) => {
    const handler = (_event, payload) => listener(payload);
    ipcRenderer.on("aipr:shop-browser-event", handler);
    return () => ipcRenderer.removeListener("aipr:shop-browser-event", handler);
  },
});
