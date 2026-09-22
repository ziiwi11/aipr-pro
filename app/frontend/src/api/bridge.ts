/**
 * IPC 桥接层
 *
 * 对齐 electron/preload.cjs 暴露的 window.aiprDesktop。
 * 浏览器环境下（无 Electron）提供降级实现，便于前端独立开发。
 */

import type {
  Bootstrap,
  DeliveryCenter,
  OutreachBatch,
  OutreachState,
  PlatformReadiness,
  RealtimeFlow,
  RunHistoryEntry,
  ShopBrowserEvent,
  Task,
  WorkerEvent,
} from "../types";

interface AiprDesktopApi {
  getBootstrap(): Promise<Bootstrap>;
  getRealtimeCreatorFlow(): Promise<RealtimeFlow>;
  getPlatformReadiness(): Promise<PlatformReadiness>;
  listTasks(): Promise<{ currentTaskId: string; tasks: Task[] }>;
  createTask(task: Partial<Task>): Promise<Task>;
  selectTask(taskId: string): Promise<unknown>;
  saveTask(task: Partial<Task>): Promise<Task>;
  importFile(): Promise<unknown>;
  importBrief(): Promise<unknown>;
  importDelivery(): Promise<unknown>;
  loadDeliveryPath(target: string): Promise<unknown>;
  launchBrowsers(): Promise<unknown>;
  layoutEmbeddedShop(payload: unknown): Promise<unknown>;
  hideEmbeddedShops(): Promise<unknown>;
  controlEmbeddedShop(payload: unknown): Promise<unknown>;
  probeLogin(): Promise<unknown>;
  startCollection(task: Partial<Task>, strategy?: unknown): Promise<unknown>;
  startWorker(task: Partial<Task>): Promise<unknown>;
  pauseWorker(): Promise<unknown>;
  exportOriginal(task: Partial<Task>): Promise<unknown>;
  openPath(target: string): Promise<unknown>;
  getDeliveryCenter(target?: string): Promise<DeliveryCenter>;
  previewRobotHandoff(target?: string): Promise<unknown>;
  copyText(value: string): Promise<unknown>;
  exportRules(task: Partial<Task>): Promise<unknown>;
  importRules(): Promise<unknown>;
  queueOutreach(payload: unknown): Promise<unknown>;
  getIntegrationPaths(): Promise<Record<string, string>>;
  getOutreachState(): Promise<OutreachState>;
  previewOutreachAuthorization(selectedIds: string[]): Promise<unknown>;
  authorizeOutreachBatch(previewId: string): Promise<OutreachBatch>;
  syncOutreachBatch(batchId: string): Promise<OutreachBatch>;
  startOutreachBatch(batchId: string): Promise<unknown>;
  getRunHistory(taskId: string, limit?: number): Promise<RunHistoryEntry[]>;
  onWorkerEvent(listener: (payload: WorkerEvent) => void): () => void;
  onShopBrowserEvent(listener: (payload: ShopBrowserEvent) => void): () => void;
}

declare global {
  interface Window {
    aiprDesktop?: AiprDesktopApi;
  }
}

/** 是否运行在 Electron 中 */
export const isElectron = (): boolean =>
  typeof window !== "undefined" && Boolean(window.aiprDesktop);

function api(): AiprDesktopApi {
  const bridge = typeof window !== "undefined" ? window.aiprDesktop : undefined;
  if (!bridge) {
    throw new Error("aiprDesktop 桥接不可用：请通过 Electron 启动，或在 dev 模式下使用 mock");
  }
  return bridge;
}

// ---------- 任务 ----------

export const getBootstrap = (): Promise<Bootstrap> => api().getBootstrap();
export const listTasks = () => api().listTasks();
export const createTask = (task: Partial<Task>) => api().createTask(task);
export const selectTask = (taskId: string) => api().selectTask(taskId);
export const saveTask = (task: Partial<Task>) => api().saveTask(task);

// ---------- 平台 ----------

export const getPlatformReadiness = (): Promise<PlatformReadiness> =>
  api().getPlatformReadiness();
export const probeLogin = () => api().probeLogin();

// ---------- 浏览器 ----------

export const launchBrowsers = () => api().launchBrowsers();
export const controlEmbeddedShop = (payload: unknown) =>
  api().controlEmbeddedShop(payload);
export const layoutEmbeddedShop = (payload: unknown) =>
  api().layoutEmbeddedShop(payload);
export const hideEmbeddedShops = () => api().hideEmbeddedShops();

// ---------- 采集 ----------

export const startCollection = (task: Partial<Task>, strategy?: unknown) =>
  api().startCollection(task, strategy);
export const startWorker = (task: Partial<Task>) => api().startWorker(task);
export const pauseWorker = () => api().pauseWorker();

// ---------- 实时流 ----------

export const getRealtimeCreatorFlow = (): Promise<RealtimeFlow> =>
  api().getRealtimeCreatorFlow();

// ---------- 交付 ----------

export const getDeliveryCenter = (target?: string): Promise<DeliveryCenter> =>
  api().getDeliveryCenter(target);
export const previewRobotHandoff = (target?: string) =>
  api().previewRobotHandoff(target);
export const exportOriginal = (task: Partial<Task>) => api().exportOriginal(task);

// ---------- 规则 ----------

export const exportRules = (task: Partial<Task>) => api().exportRules(task);
export const importRules = () => api().importRules();

// ---------- 文件 ----------

export const importFile = () => api().importFile();
export const importBrief = () => api().importBrief();
export const importDelivery = () => api().importDelivery();
export const loadDeliveryPath = (target: string) => api().loadDeliveryPath(target);
export const openPath = (target: string) => api().openPath(target);
export const copyText = (value: string) => api().copyText(value);

// ---------- 外联 ----------

export const queueOutreach = (payload: unknown) => api().queueOutreach(payload);
export const getOutreachState = (): Promise<OutreachState> => api().getOutreachState();
export const getIntegrationPaths = () => api().getIntegrationPaths();
export const previewOutreachAuthorization = (selectedIds: string[]) =>
  api().previewOutreachAuthorization(selectedIds);
export const authorizeOutreachBatch = (previewId: string) =>
  api().authorizeOutreachBatch(previewId);
export const syncOutreachBatch = (batchId: string) => api().syncOutreachBatch(batchId);
export const startOutreachBatch = (batchId: string) =>
  api().startOutreachBatch(batchId);

// ---------- 历史 ----------

export const getRunHistory = (taskId: string, limit = 100): Promise<RunHistoryEntry[]> =>
  api().getRunHistory(taskId, limit);

// ---------- 事件订阅 ----------

export function onWorkerEvent(listener: (payload: WorkerEvent) => void): () => void {
  if (!isElectron()) return () => {};
  return api().onWorkerEvent(listener);
}

export function onShopBrowserEvent(
  listener: (payload: ShopBrowserEvent) => void,
): () => void {
  if (!isElectron()) return () => {};
  return api().onShopBrowserEvent(listener);
}
