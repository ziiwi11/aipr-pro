/**
 * 9 个页面
 *
 * 每个页面的根类名对齐原版（见 docs/ORIGINAL-UI-SPEC.md）：
 *   .auto-collect-page / .dashboard-grid / .settings-layout /
 *   .panel.list-panel / .contact-layout / .outreach-page /
 *   .delivery-center-page / .settings-page / .shop-browser-page.full
 */

import type { Bootstrap, CollectionStrategy, Creator, OutreachBatch } from "../types";
import { fmtNum, fmtTime, h } from "../store";
import { emptyHint, metric, panel, progressBar, rowItem, statusPill } from "./shell";
import { renderStrategyForm } from "./strategy-form";

export interface PageHandlers {
  onSaveStrategy(s: CollectionStrategy): void;
  onStartCollection(s?: CollectionStrategy): void;
  onStartWorker(): void;
  onPauseWorker(): void;
  onLaunchBrowsers(): void;
  onProbeLogin(): void;
  onHideShops(): void;
  onControlShop(shop: "A" | "B", action: "reload" | "back" | "forward"): void;
  /** 上报视口坐标，让主进程把内置浏览器视图嵌入到 .shop-viewport 位置 */
  onLayoutShop(shop: "A" | "B"): void;
  onOpenPath(target: string): void;
  onExportRules(): void;
  onImportRules(): void;
  onPreviewHandoff(): void;
  onExportOriginal(): void;
  onPreviewOutreach(): void;
  onAuthorizeOutreach(previewId: string): void;
  onSyncOutreach(batchId: string): void;
  onStartOutreach(batchId: string): void;
  onImportBrief(): void;
  onImportFile(): void;
  onRefresh(): void;
}

/** 策略编辑态（跨重渲染保持） */
let strategyEditing = false;

// ---------- 1. 自动采集 ----------

function strategySummary(s: CollectionStrategy | undefined): HTMLElement {
  if (!s || !Object.keys(s).length) {
    return emptyHint("尚未配置采集策略，点击「编辑策略」开始");
  }
  const box = h("div", { class: "strategy-summary" });
  const rows: [string, string][] = [
    ["类目", String(s.category ?? "-")],
    ["发现方式", s.sourceDiscoveryMode === "structured_browse" ? "类目搜索" : "关键词搜索"],
    ["等级", (s.creatorLevels ?? []).map((l) => `LV${l}`).join(" ") || "-"],
    ["粉丝", `${fmtNum(s.minimumFollowers ?? 0)} - ${fmtNum(s.maximumFollowers ?? 0)}`],
    ["店铺", (s.activeShops ?? []).join("+") || "-"],
    ["目标", fmtNum(s.targetCount ?? 0)],
    ["关键词", (s.keywords ?? []).length ? (s.keywords ?? []).join("、").slice(0, 40) : "（类目搜索，无需）"],
  ];
  for (const [k, v] of rows) box.append(rowItem(k, v));
  return box;
}

export function autoCollectPage(state: Bootstrap, handlers: PageHandlers): HTMLElement {
  const t = state.task;
  const editBtn = h("button", {
    type: "button",
    onclick: () => {
      strategyEditing = !strategyEditing;
      handlers.onRefresh();
    },
  }, [strategyEditing ? "收起策略" : "编辑策略"]);

  const strategyArea = strategyEditing
    ? renderStrategyForm(t.collectionStrategy, {
        onSubmit: (s) => {
          strategyEditing = false;
          handlers.onSaveStrategy(s);
        },
        onCancel: () => {
          strategyEditing = false;
          handlers.onRefresh();
        },
      })
    : strategySummary(t.collectionStrategy);

  return h("div", { class: "auto-collect-page" }, [
    panel("采集控制",
      h("div", { class: "button-row" }, [statusPill(t.status)]),
      progressBar(Number(t.collected) || 0, Number(t.targetCount) || 0),
      h("div", { class: "metric-grid" }, [
        metric("目标", t.targetCount),
        metric("已采集", t.collected),
        metric("已处理", t.processed),
        metric("明文联系方式", t.plainContacts),
        metric("微信", t.wechat),
        metric("手机", t.phone),
      ]),
    ),
    panel("采集策略",
      h("div", { class: "strategy-section" }, [
        h("h3", { class: "section-title", text: "当前配置" }),
        strategyArea,
      ]),
      h("div", { class: "button-row" }, [
        editBtn,
        h("button", { class: "primary", type: "button",
          onclick: () => handlers.onStartCollection(t.collectionStrategy) }, ["开始采集"]),
        h("button", { type: "button", onclick: handlers.onStartWorker }, ["采集联系方式"]),
        h("button", { type: "button", onclick: handlers.onPauseWorker }, ["暂停"]),
      ]),
    ),
  ]);
}

// ---------- 2. 任务总览 ----------

export function dashboardPage(state: Bootstrap): HTMLElement {
  const t = state.task;
  const flow = state.realtimeFlow;
  const m = flow.metrics ?? {};
  return h("div", { class: "dashboard-grid" }, [
    panel("任务进度",
      progressBar(Number(t.collected) || 0, Number(t.targetCount) || 0),
      h("div", { class: "metric-grid" }, [
        metric("目标", t.targetCount),
        metric("已采集", t.collected),
        metric("已处理", t.processed),
      ]),
    ),
    panel("实时流程",
      h("div", { class: "metric-grid" }, [
        metric("候选", m.candidates),
        metric("合适", m.suitable),
        metric("取联系方式中", m.contactRevealing),
        metric("明文唯一", m.plaintext, "valid"),
        metric("正式名单", m.listed, "formal"),
      ]),
      h("div", { class: "empty-hint", text: `更新时间：${fmtTime(flow.updatedAt)}` }),
    ),
    panel("联系方式",
      h("div", { class: "metric-grid" }, [
        metric("明文总数", t.plainContacts),
        metric("微信", t.wechat),
        metric("手机", t.phone),
      ]),
    ),
    panel("运行历史",
      ...((state.runHistory ?? []).slice(0, 8).map((r) =>
        rowItem(fmtTime(r.startedAt), `${r.status ?? "-"} · ${fmtNum(r.listedCount)} 人`),
      )),
      ...((state.runHistory ?? []).length ? [] : [emptyHint("暂无运行记录")]),
    ),
  ]);
}

// ---------- 3. 品牌手卡 ----------

export function brandCardPage(state: Bootstrap, handlers: PageHandlers): HTMLElement {
  const s = state.task.collectionStrategy ?? {};
  const brief = String(s.brief ?? "");
  return h("div", { class: "settings-layout" }, [
    panel("品牌任务信息",
      rowItem("任务名称", state.task.name),
      rowItem("任务 ID", state.task.id),
      rowItem("目标数量", fmtNum(state.task.targetCount)),
      rowItem("输出目录", state.task.outputDir || "-"),
    ),
    panel("任务简报",
      brief ? h("pre", { class: "brief-text", text: brief }) : emptyHint("未填写简报"),
      h("div", { class: "button-row" },
        [h("button", { type: "button", onclick: handlers.onImportBrief }, ["导入简报"])]),
    ),
    panel("规则配置",
      h("div", { class: "button-row" }, [
        h("button", { type: "button", onclick: handlers.onExportRules }, ["导出规则"]),
        h("button", { type: "button", onclick: handlers.onImportRules }, ["导入规则"]),
      ]),
    ),
  ]);
}

// ---------- 4. 达人优选（分页表格） ----------

const PAGE_SIZE = 50;
const tableState = new Map<string, { page: number; query: string }>();

function getTableState(key: string) {
  let s = tableState.get(key);
  if (!s) {
    s = { page: 1, query: "" };
    tableState.set(key, s);
  }
  return s;
}

export function creatorTable(
  rows: Creator[],
  title: string,
  key: string,
  rerender: () => void,
): HTMLElement {
  const st = getTableState(key);
  const q = st.query.trim().toLowerCase();
  const filtered = q
    ? rows.filter((c) =>
        [c.nickname, c.douyinId, c.category, c.wechat, c.phone, c.talentLevel]
          .some((v) => String(v ?? "").toLowerCase().includes(q)))
    : rows;

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const page = Math.min(Math.max(1, st.page), totalPages);
  st.page = page;
  const slice = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const table = h("table", { class: "creator-table" });
  table.append(h("tr", {}, [
    h("th", { text: "昵称" }), h("th", { text: "抖音号" }), h("th", { text: "粉丝" }),
    h("th", { text: "等级" }), h("th", { text: "类目" }),
    h("th", { text: "微信" }), h("th", { text: "手机" }),
  ]));
  for (const c of slice) {
    table.append(h("tr", {}, [
      h("td", { text: c.nickname || "-" }),
      h("td", { text: c.douyinId || "-" }),
      h("td", { text: fmtNum(c.fans) }),
      h("td", { text: c.talentLevel || "-" }),
      h("td", { text: (c.category || "-").slice(0, 20) }),
      h("td", { text: c.wechat || "-" }),
      h("td", { text: c.phone || "-" }),
    ]));
  }

  const search = h("input", {
    class: "table-search", type: "search",
    placeholder: "搜索昵称 / 抖音号 / 类目 / 联系方式", value: st.query,
  });
  search.addEventListener("input", () => {
    st.query = (search as HTMLInputElement).value;
    st.page = 1;
    rerender();
  });

  const toolbar = h("div", { class: "table-toolbar" }, [
    search,
    h("span", { class: "pager-info",
      text: `${page} / ${totalPages} 页 · 共 ${fmtNum(filtered.length)} 条` }),
    h("button", { type: "button", disabled: page <= 1 ? "true" : undefined,
      onclick: () => { st.page = Math.max(1, page - 1); rerender(); } }, ["上一页"]),
    h("button", { type: "button", disabled: page >= totalPages ? "true" : undefined,
      onclick: () => { st.page = Math.min(totalPages, page + 1); rerender(); } }, ["下一页"]),
  ]);

  return panel(`${title}（${fmtNum(rows.length)}）`, toolbar,
    slice.length ? table : emptyHint("无匹配记录"));
}

export function creatorsPage(state: Bootstrap, rerender: () => void): HTMLElement {
  return h("div", { class: "panel list-panel" }, [
    creatorTable(state.candidateCreators ?? [], "候选达人", "candidates", rerender),
    creatorTable(state.creators ?? [], "正式名单", "formal", rerender),
  ]);
}

// ---------- 5. 联系方式 ----------

export function contactsPage(state: Bootstrap, rerender: () => void): HTMLElement {
  const withContact = (state.creators ?? []).filter((c) => c.wechat || c.phone);
  return h("div", { class: "contact-layout" }, [
    panel("联系方式统计",
      h("div", { class: "metric-grid" }, [
        metric("正式名单", (state.creators ?? []).length),
        metric("有联系方式", withContact.length),
        metric("微信", (state.creators ?? []).filter((c) => c.wechat).length),
        metric("手机", (state.creators ?? []).filter((c) => c.phone).length),
      ]),
    ),
    creatorTable(withContact, "联系方式明细", "contacts", rerender),
  ]);
}

// ---------- 6. AI 建联 ----------

export function outreachPage(state: Bootstrap, handlers: PageHandlers): HTMLElement {
  const batches: OutreachBatch[] = state.outreachBatches ?? [];
  const list = h("div", {});
  for (const b of batches) {
    const status = String(b.status || "unknown");
    list.append(h("div", { class: "row-item" }, [
      h("span", { class: "row-key", text: String(b.id || "-").slice(0, 20) }),
      statusPill(status),
      h("span", { text: `${fmtNum(b.validCount)} 人` }),
      h("button", { type: "button", onclick: () => handlers.onSyncOutreach(String(b.id)) }, ["同步"]),
      h("button", { class: "primary", type: "button",
        onclick: () => handlers.onStartOutreach(String(b.id)) }, ["启动"]),
    ]));
  }
  if (!batches.length) list.append(emptyHint("暂无外联批次"));

  // 注意：增量脚本 aipr-ai-outreach.js 会在此页注入 .outreach-banner 后方的面板
  return h("div", { class: "outreach-page" }, [
    h("header", { class: "outreach-banner" }, [
      h("h2", { text: "批量选择、授权与 AI 建联" }),
      h("button", { class: "primary", type: "button", onclick: handlers.onPreviewOutreach }, ["生成授权预览"]),
    ]),
    panel("建联批次", list),
  ]);
}

// ---------- 7. 交付中心 ----------

export function deliveryPage(state: Bootstrap, handlers: PageHandlers): HTMLElement {
  const dc = state.deliveryCenter;
  const artifacts = dc?.artifacts ?? {};
  const list = h("div", {});
  for (const [key, value] of Object.entries(artifacts)) {
    if (!value) continue;
    list.append(h("div", { class: "row-item" }, [
      h("span", { class: "row-key", text: key }),
      h("button", { type: "button", onclick: () => handlers.onOpenPath(String(value)) }, ["打开"]),
    ]));
  }
  if (!list.childElementCount) list.append(emptyHint("暂无交付物"));

  return h("div", { class: "delivery-center-page" }, [
    panel("交付操作",
      h("div", { class: "button-row" }, [
        h("button", { type: "button", onclick: handlers.onPreviewHandoff }, ["预览机器人队列"]),
        h("button", { type: "button", onclick: handlers.onExportOriginal }, ["导出原始表格"]),
      ]),
    ),
    panel("交付物清单", list),
  ]);
}

// ---------- 8. 系统设置 ----------

export function settingsPage(state: Bootstrap, handlers: PageHandlers): HTMLElement {
  const p = state.platformReadiness;
  const checks = h("div", {});
  for (const c of p?.checks ?? []) {
    checks.append(rowItem(c.label, `${c.passed ? "✓" : "✗"} ${c.detail || "-"}`));
  }
  const shops = state.task.shops ?? {};
  return h("div", { class: "settings-page" }, [
    panel("平台自检",
      rowItem("平台", `${p?.platform ?? "-"}/${p?.arch ?? "-"}`),
      rowItem("就绪状态", p?.ready ? "就绪" : "未就绪"),
      checks,
    ),
    panel("内置浏览器",
      h("div", { class: "button-row" }, [
        h("button", { class: "primary", type: "button", onclick: handlers.onLaunchBrowsers }, ["启动浏览器"]),
        h("button", { type: "button", onclick: handlers.onProbeLogin }, ["检测登录"]),
        h("button", { type: "button", onclick: handlers.onHideShops }, ["隐藏视图"]),
      ]),
      rowItem("抖店 A", shops.A?.status || "unknown"),
      rowItem("抖店 B", shops.B?.status || "unknown"),
    ),
    panel("数据导入",
      h("div", { class: "button-row" }, [
        h("button", { type: "button", onclick: handlers.onImportBrief }, ["导入简报"]),
        h("button", { type: "button", onclick: handlers.onImportFile }, ["导入文件"]),
        h("button", { type: "button", onclick: handlers.onImportRules }, ["导入规则"]),
      ]),
    ),
  ]);
}

// ---------- 9. 抖店浏览器 ----------

let activeShop: "A" | "B" = "A";

export function browserPage(handlers: PageHandlers): HTMLElement {
  const tab = (shop: "A" | "B"): HTMLElement =>
    h("button", {
      class: `shop-tab${activeShop === shop ? " active" : ""}`,
      type: "button",
      onclick: () => {
        activeShop = shop;
        handlers.onLayoutShop(shop);
        handlers.onRefresh();
      },
    }, [`抖店 ${shop}`]);

  // 视口占位：渲染后把屏幕坐标上报给主进程，由 layoutEmbeddedShop 定位内置视图
  const viewport = h("div", { class: "shop-viewport", dataset: { aiprShopViewport: activeShop } });
  window.setTimeout(() => handlers.onLayoutShop(activeShop), 0);

  return h("div", { class: "shop-browser-page full" }, [
    h("div", { class: "shop-browser-toolbar" }, [
      tab("A"), tab("B"),
      h("span", { class: "spacer" }),
      h("button", { class: "primary", type: "button", onclick: handlers.onLaunchBrowsers }, ["启动浏览器"]),
      h("button", { type: "button", onclick: handlers.onProbeLogin }, ["检测登录"]),
      h("button", { type: "button", onclick: handlers.onHideShops }, ["隐藏视图"]),
    ]),
    h("div", { class: "address-bar" }, [
      h("button", { type: "button", onclick: () => handlers.onControlShop(activeShop, "back") }, ["←"]),
      h("button", { type: "button", onclick: () => handlers.onControlShop(activeShop, "forward") }, ["→"]),
      h("button", { type: "button", onclick: () => handlers.onControlShop(activeShop, "reload") }, ["↻"]),
      h("input", { type: "text", readonly: "true", value: `当前窗口：抖店 ${activeShop}` }),
    ]),
    viewport,
  ]);
}

// ---------- 页面路由 ----------

export function renderPage(
  pageId: string,
  state: Bootstrap,
  handlers: PageHandlers,
  rerender: () => void,
): HTMLElement {
  switch (pageId) {
    case "auto-collect": return autoCollectPage(state, handlers);
    case "dashboard": return dashboardPage(state);
    case "brand-card": return brandCardPage(state, handlers);
    case "creators": return creatorsPage(state, rerender);
    case "contacts": return contactsPage(state, rerender);
    case "outreach": return outreachPage(state, handlers);
    case "delivery": return deliveryPage(state, handlers);
    case "settings": return settingsPage(state, handlers);
    case "browser": return browserPage(handlers);
    default: return autoCollectPage(state, handlers);
  }
}
