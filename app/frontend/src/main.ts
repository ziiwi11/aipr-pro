import { replaceDeliverySection } from "./delivery-refresh";
import { deliveryPage } from "./views/pages";
import { showMaintenanceProgress } from "./maintenance-progress";
import { createExclusiveAction, readableError } from "./exclusive-action";
import { createRefreshController } from "./refresh-controller";
import { mayRefresh } from "./refresh-policy";
import { getCurrentPage } from "./views/shell";
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
  toast.textContent = tone === "error" ? readableError(message) : message;
  document.body.append(toast);
  window.setTimeout(() => toast.remove(), 4000);
}

let deliveryRefreshRequested=false;
let suppressPageRender=false;
let taskSwitchPending=false;
let deliveryPendingTaskId="";
function paintDeliveryBusy(){const button=root?.querySelector<HTMLButtonElement>("[data-delivery-generation]");if(button&&deliveryPendingTaskId){button.disabled=true;button.textContent="正在生成交付包，请稍候…";}}
function refreshDelivery(){deliveryRefreshRequested=true;return refresh();}
let navigationEpoch=0;
let shopViewsHidden=true;
const handlers: ViewHandlers = {
  async onImportDelivery(){try{const imported=await api.importDelivery();if(imported)notify("历史交付已导入；未重新核验或发送，请检查来源与名单");await refresh();}catch(e){notify(e instanceof Error?e.message:"交付导入失败","error");}},
  onValidateDelivery: createExclusiveAction(async ()=>{try {await api.validateDelivery();}catch(e){notify(e instanceof Error?e.message:"校验失败","error");}finally{await refreshDelivery();}}, busy=>{const button=document.querySelector<HTMLButtonElement>("[data-delivery-validation]");if(button){button.disabled=busy;button.textContent=busy ? "正在校验文件，请稍候…" : "校验 JSON / Excel / 待发送队列";}}),
  async onBackupData() {try {const result=await api.backupData();if(result)notify("备份完成");await refresh();}catch(e){notify(e instanceof Error?e.message:"备份失败","error");}},
  async onRestoreData() {try {const result=await api.restoreData();if(result)notify("已恢复到新目录，原数据保留，任务不会自动运行");await refresh();}catch(e){notify(e instanceof Error?e.message:"恢复失败","error");}},
  async onExportDiagnostics() {try {const result=await api.exportDiagnostics();if(result)notify("去敏诊断报告已保存");}catch(e){notify(e instanceof Error?e.message:"诊断报告保存失败","error");}},
  async onSaveShopLabels(labels) {
    const task = store.get().bootstrap?.task;
    if (!task) return;
    await api.saveTask({...task,shops:Object.fromEntries(["A","B"].map(shop=>[shop,{...task.shops?.[shop],label:labels[shop] || `抖店 ${shop}`,port:"内置",status:task.shops?.[shop]?.status || "unknown"}]))});
    await refresh();
    notify("店铺备注已保存，登录会话保持原样");
  },
  async onSaveBrandCard(payload) {
    const task=store.get().bootstrap?.task;if(!task)return;
    await api.saveTask({...task,name:payload.taskName,collectionStrategy:{...task.collectionStrategy,brief:payload.brief,brandName:payload.brandName,productName:payload.productName,sellingPoints:payload.sellingPoints,criteria:payload.criteria,exclusions:payload.exclusions}});
    notify("品牌手卡已保存，后续分析使用新版配置；已交付历史不改写");await refresh();
  },
  async onSaveContactCorrection(payload){await api.saveContactCorrection(payload);notify("联系人修订已保存，请重新生成交付包；历史交付不改写");await refresh();},
  async onSaveReviewNote(payload) {
    await api.saveReviewNote(payload); notify("复核记录已保存，不会直接改变准入或发送状态"); await refresh();
  },
  async onTestJevConnection() {
    try {const result=await api.testJevConnection();if(!result.cancelled)notify(result.message || "测试完成",result.ok ? "info" : "error");await refresh();}
    catch(error){notify(error instanceof Error ? error.message : "模型测试失败","error");}
  },
  async onOpenJevConsole() {
    try { await api.openJevConsole(); } catch { notify("无法打开 Jev 官网，请访问 console.typesafe.ai", "error"); }
  },
  async onSaveJevSettings(apiKey, model) {
    try {
      await api.saveJevSettings({ apiKey, model });
      notify("Jev 配置已保存", "info");
      await refresh();
    } catch (error) { notify(error instanceof Error ? error.message : "Jev 配置保存失败", "error"); throw error; }
  },
  async onUnderstandBrief(text){return api.understandBrief(text);},
  async onReadBrief() {return await api.importBrief() as {text?:string}|null;},
  async onCreateTask(name, targetCount, strategy) {
    await api.createTask({ name, targetCount, remaining: targetCount, ...(strategy ? {collectionStrategy:strategy} : {}) });
    try { await refresh(); } catch { notify("任务已保存，页面刷新失败，请重新打开任务；无需重复创建", "info"); }
  },
  onSelectTask: createExclusiveAction(async (taskId:string) => {
    try {await api.selectTask(taskId);await refresh();}
    catch(error){notify(error instanceof Error?error.message:"任务切换失败，请重试","error");await refresh();}
  },busy=>{
    taskSwitchPending=busy;
    if(busy){renderLoading(root);return;}
    const state=store.get();
    if(state.error)renderError(root,state.error);
    else if(state.bootstrap)renderBootstrap(root,state.bootstrap,handlers);
    else renderLoading(root);
  }),
  async onLaunchBrowsers() {
    shopViewsHidden=getCurrentPage() !== "browser";
    await api.launchBrowsers();
    scheduleShopLayout();
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
  async onCopyContact(value) { await api.copyText(value); notify("联系方式已复制"); },
  async onEndCollection() {
    try { await api.endCollection(); notify("本批已结束，名单与断点已保留"); await refresh(); }
    catch (error) { notify(error instanceof Error ? error.message : "结束失败", "error"); }
  },
  async onPauseWorker() {
    const result = await api.pauseWorker() as { ok?: boolean };
    notify(result?.ok ? "采集已暂停，进度已保留" : "暂停未完成，请检查运行进程", result?.ok ? "info" : "error");
    await refresh();
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
    const bootstrap = store.get().bootstrap;
    if (bootstrap) renderBootstrap(root!, bootstrap, handlers);
    await refresh();
  },
  async onSaveStrategy(strategy) {
    const task = store.get().bootstrap?.task;
    if (!task) return;
    await api.saveTask({ ...task, targetCount: strategy.targetCount || task.targetCount, remaining: Math.max(0, (strategy.targetCount || task.targetCount) - task.plainContacts), collectionStrategy: strategy });
    notify("策略已保存", "info");
    await refresh();
  },
  async onControlShop(shop, action) {
    await api.controlEmbeddedShop({ shop, action });
  },
  async onHideShops() {
    shopViewsHidden=true;
    await api.hideEmbeddedShops({epoch:navigationEpoch});
  },
  async onPreviewHandoff() {
    const task = store.get().bootstrap?.task;
    await api.previewRobotHandoff(task?.deliveryPath);
    notify("已打开机器人队列预览", "info");
  },
  async onRepairSavedWechat(scope="current") {
    const result=await api.repairSavedWechat(scope);
    notify(`微信完整值已恢复 ${result.corrected} 条；待核实 ${result.errors.length} 条。请重新生成交付包`,result.errors.length ? "error" : "info");
    await refresh(false);
  },
  async onVerifySavedContacts() {
    const result = await api.verifySavedContacts();
    notify(result.ok ? "软件正在核验原20条平台联系方式，不发送消息" : result.error || "无法启动", result.ok ? "info" : "error");
  },
  async onApplySavedAudit(){const result=await api.applySavedAudit();notify(result.ok ? "正在应用已确认复核名单，原名单已备份" : result.error||"无法应用",result.ok ? "info":"error");},
  async onAuditSavedList() {
    const result=await api.auditSavedList();
    notify(result.ok ? "正在核对已保存名单，不采集或付费分析" : result.error || "无法启动核对",result.ok ? "info" : "error");
  },
  async onReviewSaved() {
    const result = await api.reviewSaved();
    notify(result.ok ? "软件正在补核缺失截图，进度可在运行记录查看" : result.error || "无法启动补核", result.ok ? "info" : "error");
  },
  async onOpenSavedReview() { await api.openSavedReview(); },
  async onImportBatchBaseline(){const result=await api.importBatchBaseline();if(!result.canceled){notify(`已将 ${result.count} 人设为往期基线；当前联系与交付只展示本轮新增`,"info");await refresh();}},
  async onDeliverCurrent() {
    const task = store.get().bootstrap?.task;
    if (!task || deliveryPendingTaskId) return;
    deliveryPendingTaskId=task.id;paintDeliveryBusy();
    try {
      const result=await api.deliverCurrent(task) as {ok?:boolean;error?:string};
      if(!result?.ok)throw new Error(result?.error || "无法启动交付生成");
      notify("正在生成已保存名单交付包，不新增采集或发送", "info");
    }catch(error){deliveryPendingTaskId="";notify(error instanceof Error?error.message:"交付生成失败","error");await refreshDelivery();}
  },
  async onExportOriginal() {
    const task = store.get().bootstrap?.task;
    if (!task) return;
    const result=await api.exportOriginal(task) as {ok?:boolean;error?:string};
    notify(result?.ok ? "正在导出原格式表格，完成后可在交付中心打开" : result?.error || "无法启动导出",result?.ok ? "info" : "error");
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
      notify("授权预览已生成，请核对后在工作台单独确认授权", "info");
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
  async onNavigate(pageId) {
    navigationEpoch++;shopViewsHidden=pageId !== "browser";
    // Hide native content before any asynchronous refresh can finish.
    await api.hideEmbeddedShops({epoch:navigationEpoch});
    await refresh();
  },
  async onImportBrief() {
    const imported=await api.importBrief() as {text?:string}|null;
    const task=store.get().bootstrap?.task;
    if(imported?.text && task){await api.saveTask({...task,collectionStrategy:{...task.collectionStrategy,brief:imported.text.slice(0,20000)}});notify("简报已导入并保存");}
    await refresh();
  },
  async onImportFile() {
    const file=await api.importFile() as string|null;
    const task=store.get().bootstrap?.task;
    if(file && task){await api.saveTask({...task,originalWorkbookPath:file});notify("原始表格已导入");}
    await refresh();
  },
  async onLayoutShop(shop) {
    // 计算 .shop-viewport 在窗口中的坐标，交给主进程定位内置 BrowserView
    const el = document.querySelector<HTMLElement>(".shop-viewport");
    if (!el || getCurrentPage() !== "browser" || shopViewsHidden) return;
    const r = el.getBoundingClientRect(),clip=document.querySelector(".page-body")?.getBoundingClientRect();
    const top=Math.max(r.top,clip?.top ?? 0),bottom=Math.min(r.bottom,clip?.bottom ?? window.innerHeight);
    if(bottom <= top){await api.hideEmbeddedShops({epoch:navigationEpoch});return;}
    await api.layoutEmbeddedShop({
      shop,epoch:navigationEpoch,
      bounds: {
        x: Math.round(r.left),
        y: Math.round(top),
        width: Math.round(r.width),
        height: Math.round(bottom-top),
      },
    });
  },
};

let layoutFrame=0;
function scheduleShopLayout(): void {
 if(layoutFrame || getCurrentPage()!=="browser" || shopViewsHidden)return;
 layoutFrame=requestAnimationFrame(()=>{layoutFrame=0;const shop=document.querySelector<HTMLElement>(".shop-viewport")?.dataset.aiprShopViewport;if(shop==="A"||shop==="B")void handlers.onLayoutShop(shop);});
}
window.addEventListener("resize",scheduleShopLayout);
document.addEventListener("scroll",scheduleShopLayout,true);

let lastBootstrap = "";
const refresh = createRefreshController(api.getBootstrap, bootstrap => {
  const serialized=JSON.stringify(bootstrap);
  if(serialized!==lastBootstrap || store.get().error || deliveryRefreshRequested){
    const scoped=deliveryRefreshRequested;deliveryRefreshRequested=false;
    lastBootstrap=serialized;
    if(scoped){replaceDeliverySection(root,()=>deliveryPage(bootstrap,handlers));suppressPageRender=true;}
    try{store.set({bootstrap,error:""});}finally{suppressPageRender=false;}
    paintDeliveryBusy();
  }
}, err=>store.set({error:err instanceof Error?err.message:String(err)}));

store.subscribe((state) => {
  if(suppressPageRender||taskSwitchPending)return;
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
  if(event.status==="maintenance_progress"){const progress=event.maintenance as Bootstrap["maintenance"];if(progress)showMaintenanceProgress(root,progress,store.get().bootstrap?.task.status==="running");return;}
  if(event.status==="original_export_finished"){notify("原格式导出完成，可在交付中心打开文件");void refreshDelivery();return;}
  if(event.type==="delivery-ready" || event.status==="delivery_ready"){notify("交付包已生成，请校验新版文件");void refreshDelivery();return;}
  if(event.workerAction==="deliver-current" && ["finished","error"].includes(String(event.type))){
    if(event.taskId===deliveryPendingTaskId)deliveryPendingTaskId="";
    if(event.type==="error" || (event.type==="finished" && event.code!==0))notify(String(event.message||"交付生成失败，请查看运行记录"),"error");
    void refreshDelivery();return;
  }
  if (event.status && /progress|finished|paused/.test(event.status)) {
    if (mayRefresh()) void refresh(false);
  }
});

// 初始加载 + 定时刷新
renderLoading(root);
void refresh();
window.setInterval(() => { if (mayRefresh()) void refresh(false); }, 5000);
for (const eventName of ["input", "change"]) document.addEventListener(eventName, (event) => {
  const element = event.target as HTMLElement;
  const form = element.closest("form, [data-preserve-input]") as HTMLElement | null;
  if (form) form.dataset.editingDraft = "true";
});

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
  // 从文档目录加载，兼容打包后的 file:// 与开发环境。
  injectStylesheet(new URL("./aipr-ai-outreach.css", document.baseURI).href);
  injectStylesheet(new URL("./aipr-realtime-flow.css", document.baseURI).href);
  const scripts = ["./aipr-ai-outreach.js", "./aipr-realtime-flow.js"].map(src => new URL(src, document.baseURI).href);
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
