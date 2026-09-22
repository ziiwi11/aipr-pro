/**
 * 应用外壳：侧边栏导航 + 工作区
 *
 * 严格对齐原版结构（见 docs/ORIGINAL-UI-SPEC.md）：
 *   .app-shell > aside.sidebar + main.workspace
 *   aside.sidebar > .brand-lockup / .context-label / .task-switch-wrap / nav / .sidebar-foot
 *   main.workspace > header.topbar + .page-body
 */

import type { Bootstrap, ShopState, Task } from "../types";
import { fmtNum, h, mount } from "../store";

/** 9 个页面（标签与根类名对齐原版） */
export interface PageDef {
  id: string;
  label: string;
  /** 页面根元素类名（对齐原版） */
  rootClass: string;
}

export const PAGES: PageDef[] = [
  { id: "auto-collect", label: "自动采集", rootClass: "auto-collect-page" },
  { id: "dashboard", label: "任务总览", rootClass: "dashboard-grid" },
  { id: "brand-card", label: "品牌手卡", rootClass: "settings-layout" },
  { id: "creators", label: "达人优选", rootClass: "panel list-panel" },
  { id: "contacts", label: "联系方式", rootClass: "contact-layout" },
  { id: "outreach", label: "AI 建联", rootClass: "outreach-page" },
  { id: "delivery", label: "交付中心", rootClass: "delivery-center-page" },
  { id: "settings", label: "系统设置", rootClass: "settings-page" },
  { id: "browser", label: "抖店浏览器", rootClass: "shop-browser-page full" },
];

/** 当前页面（跨重渲染保持） */
let currentPageId = "auto-collect";

export function getCurrentPage(): string {
  return currentPageId;
}

export function setCurrentPage(id: string): void {
  if (PAGES.some((p) => p.id === id)) currentPageId = id;
}

export interface ShellHandlers {
  onNavigate(pageId: string): void;
  onSelectTask(taskId: string): void;
  onRefresh(): void;
  onProbeLogin(): void;
}

// ---------- 侧边栏 ----------

function brandLockup(): HTMLElement {
  return h("div", { class: "brand-lockup" }, [
    h("span", { class: "brand-mark", text: "A" }),
    h("div", { class: "brand-text" }, [
      h("strong", { text: "AIPR Pro" }),
      h("span", { text: "达人运营系统" }),
    ]),
  ]);
}

function taskSwitcher(task: Task, handlers: ShellHandlers): HTMLElement {
  const btn = h("button", {
    class: "task-switch active",
    type: "button",
    onclick: () => handlers.onRefresh(),
  }, [
    h("span", { class: "task-switch-name", text: task.name || "未命名任务" }),
    h("span", { class: "task-switch-meta",
      text: `切换任务 · ${fmtNum(task.targetCount)} 人` }),
  ]);
  return h("div", { class: "task-switch-wrap" }, [btn]);
}

function navList(state: Bootstrap, handlers: ShellHandlers): HTMLElement {
  // 联系方式页显示正式名单数量角标（对齐原版）
  const contactCount = (state.creators ?? []).length;
  const nav = h("nav", {});
  for (const page of PAGES) {
    const active = page.id === currentPageId;
    const children: (Node | string)[] = [h("span", { text: page.label })];
    if (page.id === "contacts" && contactCount > 0) {
      children.push(h("span", { class: "nav-badge", text: String(contactCount) }));
    }
    nav.append(
      h("button", {
        class: active ? "active" : "",
        type: "button",
        onclick: () => handlers.onNavigate(page.id),
      }, children),
    );
  }
  return nav;
}

function sidebarFoot(state: Bootstrap): HTMLElement {
  const ready = state.platformReadiness?.ready === true;
  return h("div", { class: "sidebar-foot" }, [
    h("div", { class: "system-state" }, [
      h("span", { class: `dot${ready ? "" : " bad"}` }),
      h("div", {}, [
        h("span", { text: ready ? "本机服务正常" : "服务未就绪" }),
        h("small", { text: ready ? "数据已保存" : "请检查系统设置" }),
      ]),
    ]),
    h("div", { class: "user" }, [
      h("span", { class: "avatar", text: "运" }),
      h("div", {}, [
        h("span", { text: "运营管理员" }),
        h("small", { text: "全部权限" }),
      ]),
    ]),
  ]);
}

export function renderSidebar(state: Bootstrap, handlers: ShellHandlers): HTMLElement {
  return h("aside", { class: "sidebar" }, [
    brandLockup(),
    h("div", { class: "context-label", text: "当前品牌任务" }),
    taskSwitcher(state.task, handlers),
    navList(state, handlers),
    sidebarFoot(state),
  ]);
}

// ---------- 顶栏 ----------

function shopChip(shop: string, info: ShopState | undefined): HTMLElement {
  const loggedIn = info?.status === "connected" || info?.status === "logged_in";
  return h("div", { class: "shop-chip" }, [
    h("span", { class: `dot${loggedIn ? "" : " unknown"}` }),
    h("div", {}, [
      h("span", { text: info?.label || `抖店 ${shop}` }),
      h("small", { text: loggedIn ? "已登录 · 端口 内置" : "未登录 · 端口 内置" }),
    ]),
  ]);
}

export function renderTopbar(state: Bootstrap, handlers: ShellHandlers): HTMLElement {
  const page = PAGES.find((p) => p.id === currentPageId);
  const shops = state.task.shops ?? {};
  return h("header", { class: "topbar" }, [
    h("div", { class: "topbar-title" }, [
      h("span", { class: "crumb",
        text: `${state.task.name} / ${fmtNum(state.task.targetCount)} 人提报` }),
      h("h1", { text: page?.label ?? "AIPR Pro" }),
    ]),
    h("div", { class: "top-actions" }, [
      shopChip("A", shops.A),
      shopChip("B", shops.B),
      h("button", { type: "button", title: "刷新", onclick: handlers.onRefresh }, ["刷新"]),
    ]),
  ]);
}

// ---------- 外壳组装 ----------

export function renderShell(
  root: HTMLElement,
  state: Bootstrap,
  handlers: ShellHandlers,
  pageBody: HTMLElement,
): void {
  mount(
    root,
    h("div", { class: "app-shell" }, [
      renderSidebar(state, handlers),
      h("main", { class: "workspace" }, [
        renderTopbar(state, handlers),
        h("div", { class: "page-body" }, [pageBody]),
      ]),
    ]),
  );
}

// ---------- 通用小组件 ----------

export function panel(title: string, ...children: Node[]): HTMLElement {
  return h("section", { class: "panel" }, [
    h("h2", { class: "panel-title", text: title }),
    ...children,
  ]);
}

export function metric(label: string, value: unknown, tone = ""): HTMLElement {
  return h("div", { class: `metric ${tone}`.trim() }, [
    h("span", { class: "metric-label", text: label }),
    h("strong", { class: "metric-value", text: fmtNum(value) }),
  ]);
}

export function progressBar(current: number, total: number): HTMLElement {
  const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;
  const fill = h("div", { class: "progress-fill" });
  fill.style.width = `${pct}%`;
  return h("div", { class: "progress-wrap" }, [
    h("div", { class: "progress-track" }, [fill]),
    h("span", { class: "progress-label", text: `${pct}%（${fmtNum(current)} / ${fmtNum(total)}）` }),
  ]);
}

export function statusPill(status: string): HTMLElement {
  return h("span", { class: `status-pill status-${status}`, text: status });
}

export function emptyHint(text: string): HTMLElement {
  return h("div", { class: "empty-hint", text });
}

export function rowItem(key: string, value: string): HTMLElement {
  return h("div", { class: "row-item" }, [
    h("span", { class: "row-key", text: key }),
    h("span", { text: value }),
  ]);
}
