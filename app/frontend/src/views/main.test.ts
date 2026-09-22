import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderBootstrap, renderError, renderLoading } from "./main";
import { setCurrentPage } from "./shell";
import type { Bootstrap, Creator } from "../types";

function makeCreator(i: number): Creator {
  return {
    nickname: `达人${i}`,
    douyinId: `dy${i}`,
    fans: i * 100,
    talentLevel: `LV${(i % 4) + 1}`,
    category: i % 2 ? "美妆/个护家清" : "个护家清",
    wechat: i % 3 === 0 ? `wx${i}` : "",
    phone: i % 3 !== 0 ? `1390000${String(i).padStart(4, "0")}` : "",
  };
}

function makeBootstrap(overrides: Partial<Bootstrap> = {}): Bootstrap {
  return {
    task: {
      id: "t1",
      name: "测试任务",
      targetCount: 100,
      collected: 40,
      processed: 35,
      plainContacts: 30,
      wechat: 10,
      phone: 20,
      remaining: 60,
      contactDelayMs: 3200,
      status: "running",
      outputDir: "/tmp/out",
      deliveryPath: "",
      queuePath: "",
      originalWorkbookPath: "",
      collectionStrategy: { category: "美妆个护", targetCount: 100 },
      shops: {
        A: { label: "抖店 A", port: "内置", status: "connected" },
        B: { label: "抖店 B", port: "内置", status: "unknown" },
      },
    },
    tasks: [],
    creators: [],
    candidateCreators: [],
    realtimeFlow: { available: true, updatedAt: "2026-09-22T10:00:00Z", metrics: {} },
    integrationPaths: {},
    deliveryCenter: { available: false, artifacts: {} },
    platformReadiness: {
      platform: "darwin", arch: "arm64", supported: true, ready: true,
      python: "/py", browser: "/chrome", documents: "/docs",
      checks: [
        { key: "architecture", label: "系统架构", passed: true, detail: "darwin/arm64" },
        { key: "python", label: "内置 Python", passed: true, detail: "/py" },
      ],
    },
    runHistory: [],
    outreachBatches: [],
    ...overrides,
  };
}

const handlers = {
  onCreateTask: vi.fn(),
  onSelectTask: vi.fn(),
  onLaunchBrowsers: vi.fn(),
  onProbeLogin: vi.fn(),
  onStartCollection: vi.fn(),
  onStartWorker: vi.fn(),
  onPauseWorker: vi.fn(),
  onOpenPath: vi.fn(),
  onExportRules: vi.fn(),
  onImportRules: vi.fn(),
  onRefresh: vi.fn(),
  onSaveStrategy: vi.fn(),
  onControlShop: vi.fn(),
  onLayoutShop: vi.fn(),
  onHideShops: vi.fn(),
  onPreviewHandoff: vi.fn(),
  onExportOriginal: vi.fn(),
  onPreviewOutreach: vi.fn(),
  onAuthorizeOutreach: vi.fn(),
  onSyncOutreach: vi.fn(),
  onStartOutreach: vi.fn(),
  onNavigate: vi.fn(),
  onImportBrief: vi.fn(),
  onImportFile: vi.fn(),
};

function render(state: Bootstrap) {
  const root = document.createElement("div");
  document.body.replaceChildren(root);
  renderBootstrap(root, state, handlers);
  return root;
}

beforeEach(() => {
  document.body.replaceChildren();
  vi.clearAllMocks();
  setCurrentPage("auto-collect");
});

describe("应用外壳 — 对齐原版结构", () => {
  it("渲染 .app-shell", () => {
    const root = render(makeBootstrap());
    expect(root.querySelector(".app-shell")).toBeTruthy();
  });

  it("渲染 aside.sidebar 与 main.workspace", () => {
    const root = render(makeBootstrap());
    expect(root.querySelector("aside.sidebar")).toBeTruthy();
    expect(root.querySelector("main.workspace")).toBeTruthy();
  });

  it("侧边栏含品牌标识", () => {
    const root = render(makeBootstrap());
    expect(root.querySelector(".brand-lockup")).toBeTruthy();
    expect(root.querySelector(".brand-lockup")?.textContent).toContain("AIPR Pro");
  });

  it("侧边栏含任务切换与上下文标签", () => {
    const root = render(makeBootstrap());
    expect(root.querySelector(".context-label")).toBeTruthy();
    expect(root.querySelector(".task-switch-wrap")).toBeTruthy();
    expect(root.querySelector(".task-switch")?.textContent).toContain("测试任务");
  });

  it("侧边栏含底部状态区", () => {
    const root = render(makeBootstrap());
    expect(root.querySelector(".sidebar-foot")).toBeTruthy();
    expect(root.querySelector(".system-state")).toBeTruthy();
    expect(root.querySelector(".user")).toBeTruthy();
  });

  it("工作区含 topbar 与 page-body", () => {
    const root = render(makeBootstrap());
    expect(root.querySelector("header.topbar")).toBeTruthy();
    expect(root.querySelector(".page-body")).toBeTruthy();
  });

  it("topbar 显示任务面包屑与两个店铺状态", () => {
    const root = render(makeBootstrap());
    expect(root.querySelector(".crumb")?.textContent).toContain("测试任务");
    expect(root.querySelectorAll(".shop-chip").length).toBe(2);
  });
});

describe("导航 — 9 个页面", () => {
  it("nav 内恰好 9 个按钮", () => {
    const root = render(makeBootstrap());
    expect(root.querySelectorAll("nav button").length).toBe(9);
  });

  it("菜单标签与原版一致", () => {
    const root = render(makeBootstrap());
    const labels = [...root.querySelectorAll("nav button")].map(
      (b) => b.textContent?.replace(/\d+$/, "").trim(),
    );
    expect(labels).toEqual([
      "自动采集", "任务总览", "品牌手卡", "达人优选", "联系方式",
      "AI 建联", "交付中心", "系统设置", "抖店浏览器",
    ]);
  });

  it("当前页按钮带 .active", () => {
    const root = render(makeBootstrap());
    const active = root.querySelectorAll("nav button.active");
    expect(active.length).toBe(1);
    expect(active[0].textContent).toContain("自动采集");
  });

  it("联系方式页在有正式名单时显示角标", () => {
    const rows = Array.from({ length: 5 }, (_, i) => makeCreator(i));
    const root = render(makeBootstrap({ creators: rows }));
    const badge = root.querySelector(".nav-badge");
    expect(badge?.textContent).toBe("5");
  });

  it("无正式名单时不显示角标", () => {
    const root = render(makeBootstrap());
    expect(root.querySelector(".nav-badge")).toBeFalsy();
  });
});

describe("页面路由 — 根类名对齐原版", () => {
  const cases: [string, string][] = [
    ["auto-collect", ".auto-collect-page"],
    ["dashboard", ".dashboard-grid"],
    ["brand-card", ".settings-layout"],
    ["creators", ".panel.list-panel"],
    ["contacts", ".contact-layout"],
    ["outreach", ".outreach-page"],
    ["delivery", ".delivery-center-page"],
    ["settings", ".settings-page"],
    ["browser", ".shop-browser-page.full"],
  ];

  for (const [pageId, selector] of cases) {
    it(`${pageId} → ${selector}`, () => {
      setCurrentPage(pageId);
      const root = render(makeBootstrap());
      expect(root.querySelector(selector), selector).toBeTruthy();
    });
  }
});

describe("AI 建联页 — 增量脚本挂载点", () => {
  it("存在 .outreach-page 与 .outreach-banner", () => {
    setCurrentPage("outreach");
    const root = render(makeBootstrap());
    expect(root.querySelector(".outreach-page")).toBeTruthy();
    expect(root.querySelector(".outreach-banner")).toBeTruthy();
  });

  it(".outreach-page 是页面根元素（非嵌套）", () => {
    setCurrentPage("outreach");
    const root = render(makeBootstrap());
    const page = root.querySelector(".outreach-page");
    expect(page?.parentElement?.classList.contains("page-body")).toBe(true);
  });
});

describe("自动采集页 — 进度与策略", () => {
  it("进度按 collected/targetCount 计算", () => {
    const root = render(makeBootstrap());
    expect(root.querySelector(".progress-label")?.textContent).toContain("40%");
  });

  it("目标为 0 时不除零", () => {
    const b = makeBootstrap();
    b.task = { ...b.task, targetCount: 0, collected: 0 };
    const root = render(b);
    expect(root.querySelector(".progress-label")?.textContent).toContain("0%");
  });

  it("有策略时显示摘要", () => {
    const root = render(makeBootstrap());
    expect(root.querySelector(".strategy-summary")).toBeTruthy();
  });

  it("无策略时提示配置", () => {
    const b = makeBootstrap();
    b.task = { ...b.task, collectionStrategy: undefined };
    const root = render(b);
    expect(root.querySelector(".strategy-section")?.textContent).toContain("尚未配置");
  });

  it("显示状态标签", () => {
    const root = render(makeBootstrap());
    expect(root.querySelector(".status-pill")?.textContent).toBe("running");
  });
});

describe("达人表格 — 分页与搜索", () => {
  it("每页最多 50 条", () => {
    setCurrentPage("creators");
    const rows = Array.from({ length: 120 }, (_, i) => makeCreator(i));
    const root = render(makeBootstrap({ candidateCreators: rows }));
    const table = root.querySelector(".creator-table");
    expect(table?.querySelectorAll("tr").length).toBe(51);
  });

  it("分页信息显示总页数", () => {
    setCurrentPage("creators");
    const rows = Array.from({ length: 120 }, (_, i) => makeCreator(i));
    const root = render(makeBootstrap({ candidateCreators: rows }));
    const info = root.querySelector(".pager-info")?.textContent ?? "";
    expect(info).toContain("1 / 3");
    expect(info).toContain("120");
  });

  it("第一页上一页禁用", () => {
    setCurrentPage("creators");
    const rows = Array.from({ length: 120 }, (_, i) => makeCreator(i));
    const root = render(makeBootstrap({ candidateCreators: rows }));
    const btns = root.querySelectorAll<HTMLButtonElement>(".table-toolbar button");
    expect(btns[0].disabled).toBe(true);
    expect(btns[1].disabled).toBe(false);
  });

  it("少于 50 条时只有 1 页", () => {
    setCurrentPage("creators");
    const rows = Array.from({ length: 10 }, (_, i) => makeCreator(i));
    const root = render(makeBootstrap({ candidateCreators: rows }));
    expect(root.querySelector(".pager-info")?.textContent).toContain("1 / 1");
  });

  it("表格 7 列", () => {
    setCurrentPage("creators");
    const root = render(makeBootstrap({ candidateCreators: [makeCreator(1)] }));
    expect(root.querySelectorAll(".creator-table th").length).toBe(7);
  });

  it("空列表显示提示", () => {
    setCurrentPage("creators");
    const root = render(makeBootstrap());
    expect(root.querySelectorAll(".empty-hint").length).toBeGreaterThan(0);
  });
});

describe("抖店浏览器页", () => {
  it("含 A/B 标签页", () => {
    setCurrentPage("browser");
    const root = render(makeBootstrap());
    const tabs = root.querySelectorAll(".shop-tab");
    expect(tabs.length).toBe(2);
    expect(tabs[0].textContent).toBe("抖店 A");
    expect(tabs[1].textContent).toBe("抖店 B");
  });

  it("含后退/前进/刷新", () => {
    setCurrentPage("browser");
    const root = render(makeBootstrap());
    const labels = [...root.querySelectorAll(".address-bar button")].map((b) => b.textContent);
    expect(labels).toEqual(["←", "→", "↻"]);
  });

  it("含视口占位", () => {
    setCurrentPage("browser");
    const root = render(makeBootstrap());
    expect(root.querySelector(".shop-viewport")).toBeTruthy();
  });
});

describe("系统设置页", () => {
  it("显示平台自检项", () => {
    setCurrentPage("settings");
    const root = render(makeBootstrap());
    const text = root.querySelector(".settings-page")?.textContent ?? "";
    expect(text).toContain("系统架构");
    expect(text).toContain("内置 Python");
  });
});

describe("renderError / renderLoading", () => {
  it("renderError 显示错误", () => {
    const root = document.createElement("div");
    renderError(root, "boom");
    expect(root.textContent).toContain("boom");
    expect(root.querySelector(".fatal-error")).toBeTruthy();
  });

  it("renderLoading 显示加载中", () => {
    const root = document.createElement("div");
    renderLoading(root);
    expect(root.querySelector(".loading")?.textContent).toContain("加载");
  });
});
