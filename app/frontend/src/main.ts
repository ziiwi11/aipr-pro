/**
 * AIPR Pro 前端入口
 *
 * 挂载点：#root（与现有 index.html 一致）
 * IPC 契约：electron/preload.cjs 暴露的 window.aiprDesktop
 */

import * as api from "./api/bridge";
import { Store } from "./store";
import type { Bootstrap } from "./types";
import {
  renderBootstrap,
  renderError,
  renderLoading,
  type ViewHandlers,
} from "./views/main";
import "./styles/app.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("缺少 #root 挂载点");
}

const store = new Store<{ bootstrap: Bootstrap | null; error: string }>({
  bootstrap: null,
  error: "",
});

/** 轻量提示条 */
function notify(message: string, tone: "info" | "error" = "info"): void {
  const existing = document.querySelector(".aipr-toast");
  existing?.remove();
  const toast = document.createElement("div");
  toast.className = `aipr-toast tone-${tone}`;
  toast.textContent = message;
  document.body.append(toast);
  window.setTimeout(() => toast.remove(), 4000);
}

const handlers: ViewHandlers = {
  async onCreateTask(name, targetCount) {
    await api.createTask({ name, targetCount, remaining: targetCount });
    await refresh();
  },
  async onSelectTask(taskId) {
    await api.selectTask(taskId);
    await refresh();
  },
  async onLaunchBrowsers() {
    await api.launchBrowsers();
    await refresh();
  },
  async onProbeLogin() {
    await api.probeLogin();
    await refresh();
  },
  async onStartCollection(strategy) {
    const task = store.get().bootstrap?.task;
    if (!task) return;
    if (!strategy || !Object.keys(strategy).length) {
      notify("请先配置采集策略（点击「编辑策略」）", "error");
      return;
    }
    // runWorker 失败时返回 { ok: false, error }，必须检查，否则会误报成功
    const result = await api.startCollection(task, strategy);
    const r = result as { ok?: boolean; error?: string } | undefined;
    if (r && r.ok === false) {
      notify(`采集启动失败：${r.error ?? "未知原因"}`, "error");
    } else {
      notify("采集已启动", "info");
    }
    await refresh();
  },
  async onStartWorker() {
    const task = store.get().bootstrap?.task;
    if (!task) return;
    const result = await api.startWorker(task);
    const r = result as { ok?: boolean; error?: string } | undefined;
    if (r && r.ok === false) {
      notify(`联系方式采集启动失败：${r.error ?? "未知原因"}`, "error");
    } else {
      notify("联系方式采集已启动", "info");
    }
    await refresh();
  },
  async onPauseWorker() {
    await api.pauseWorker();
    notify("已请求暂停", "info");
  },
  async onOpenPath(target) {
    await api.openPath(target);
  },
  async onExportRules() {
    const task = store.get().bootstrap?.task;
    if (!task) return;
    await api.exportRules(task);
  },
  async onImportRules() {
    await api.importRules();
    await refresh();
  },
  async onRefresh() {
    await refresh();
  },
  async onSaveStrategy(strategy) {
    const task = store.get().bootstrap?.task;
    if (!task) return;
    await api.saveTask({ ...task, collectionStrategy: strategy });
    notify("策略已保存", "info");
    await refresh();
  },
  async onControlShop(shop, action) {
    await api.controlEmbeddedShop({ shop, action });
  },
  async onHideShops() {
    await api.hideEmbeddedShops();
  },
  async onPreviewHandoff() {
    const task = store.get().bootstrap?.task;
    await api.previewRobotHandoff(task?.deliveryPath);
    notify("已打开机器人队列预览", "info");
  },
  async onExportOriginal() {
    const task = store.get().bootstrap?.task;
    if (!task) return;
    await api.exportOriginal(task);
  },
  async onPreviewOutreach() {
    const state = store.get().bootstrap;
    const ids = (state?.creators ?? [])
      .map((c) => String(c.id ?? c.identity ?? ""))
      .filter(Boolean);
    if (!ids.length) {
      notify("正式名单为空，无法预览授权", "error");
      return;
    }
    const result = await api.previewOutreachAuthorization(ids);
    const previewId = (result as { id?: string })?.id;
    if (previewId) {
      await api.authorizeOutreachBatch(previewId);
      notify("已授权批次", "info");
      await refresh();
    }
  },
  async onAuthorizeOutreach(previewId) {
    await api.authorizeOutreachBatch(previewId);
    await refresh();
  },
  async onSyncOutreach(batchId) {
    await api.syncOutreachBatch(batchId);
    notify("批次已同步", "info");
    await refresh();
  },
  async onStartOutreach(batchId) {
    await api.startOutreachBatch(batchId);
    notify("外联已启动", "info");
    await refresh();
  },
  async onNavigate() {
    // 页面切换由 views/shell.ts 维护，这里只需触发一次刷新
    await refresh();
  },
  async onImportBrief() {
    await api.importBrief();
    await refresh();
  },
  async onImportFile() {
    await api.importFile();
    await refresh();
  },
  async onLayoutShop(shop) {
    // 计算 .shop-viewport 在窗口中的坐标，交给主进程定位内置 BrowserView
    const el = document.querySelector<HTMLElement>(".shop-viewport");
    if (!el) return;
    const r = el.getBoundingClientRect();
    await api.layoutEmbeddedShop({
      shop,
      bounds: {
        x: Math.round(r.left),
        y: Math.round(r.top),
        width: Math.round(r.width),
        height: Math.round(r.height),
      },
    });
  },
};

async function refresh(): Promise<void> {
  try {
    const bootstrap = await api.getBootstrap();
    store.set({ bootstrap, error: "" });
  } catch (err) {
    store.set({ error: err instanceof Error ? err.message : String(err) });
  }
}

store.subscribe((state) => {
  if (state.error) {
    renderError(root, state.error);
  } else if (state.bootstrap) {
    renderBootstrap(root, state.bootstrap, handlers);
  } else {
    renderLoading(root);
  }
});

// 实时流事件：收到 worker 事件后刷新
api.onWorkerEvent((event) => {
  if (event.status && /progress|finished|paused/.test(event.status)) {
    void refresh();
  }
});

// 初始加载 + 定时刷新
renderLoading(root);
void refresh();
window.setInterval(() => void refresh(), 5000);

// 暴露给增量脚本（aipr-ai-outreach.js / aipr-realtime-flow.js）
(window as unknown as Record<string, unknown>).__AIPR_REFRESH__ = refresh;

/**
 * 加载增量脚本
 *
 * 这两个脚本通过 DOM 注入方式增强界面（AI 建联工作台、实时流程面板），
 * 需要主界面先渲染完成。用动态 import 避免 Vite 在构建时解析它们
 * （它们位于 dist 根目录，由 publicDir 复制，不属于模块图）。
 */
function injectStylesheet(href: string): void {
  if (document.querySelector(`link[href="${href}"]`)) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  document.head.append(link);
}

async function loadIncrementalScripts(): Promise<void> {
  // 增量脚本的样式（绝对路径，避免被解析到 /assets/ 下）
  injectStylesheet("/aipr-ai-outreach.css");
  injectStylesheet("/aipr-realtime-flow.css");
  const scripts = ["/aipr-ai-outreach.js", "/aipr-realtime-flow.js"];
  for (const src of scripts) {
    try {
      // 用 /* @vite-ignore */ 跳过 Vite 的静态分析
      await import(/* @vite-ignore */ src);
    } catch (err) {
      console.warn(`[aipr] 增量脚本加载失败: ${src}`, err);
    }
  }
}

// 等首次渲染完成后再挂载增量面板
void refresh().then(() => loadIncrementalScripts());
