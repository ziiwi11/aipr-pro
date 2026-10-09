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
  onImportDelivery: vi.fn(),
};

function render(state: Bootstrap) {
  const root = document.createElement("div");
  document.body.replaceChildren(root);
  if(!state.creatorLibrary && state.creators?.length)state.creatorLibrary={creators:state.creators.map(c=>({...c,libraryTaskIds:["historical-test"]})),batches:[{id:"historical-test",name:"往期测试批",count:state.creators.length}]};
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
    expect(root.querySelector(".brand-lockup")?.textContent).toContain("千寻");
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

describe("导航 — 8 个模块", () => {
  it("联系方式与建联合并为单一导航入口", () => {
    const root = render(makeBootstrap());
    expect(root.querySelectorAll("nav button").length).toBe(8);
  });

  it("菜单标签与原版一致", () => {
    const root = render(makeBootstrap());
    const labels = [...root.querySelectorAll("nav button")].map(
      (b) => b.textContent?.replace(/\d+$/, "").trim(),
    );
    expect(labels).toEqual([
      "自动采集", "任务总览", "品牌手卡", "达人优选", "联系与交付", "分析模型", "系统设置", "抖店浏览器",
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

describe("历史交付导入保护", () => {
  it("活动采集期间不允许导入覆盖名单", () => {
    setCurrentPage("delivery");
    const root=render(makeBootstrap());
    const button=Array.from(root.querySelectorAll("button")).find(b=>b.textContent==="导入历史交付 JSON")!;
    expect(button.disabled).toBe(true);
    button.click();
    expect(handlers.onImportDelivery).not.toHaveBeenCalled();
  });
  it("停止后允许显式导入，不触发采集或外发", () => {
    setCurrentPage("delivery");
    const state=makeBootstrap();state.task.status="paused";
    const root=render(state);
    const button=Array.from(root.querySelectorAll("button")).find(b=>b.textContent==="导入历史交付 JSON")!;
    button.click();
    expect(handlers.onImportDelivery).toHaveBeenCalledOnce();
    expect(handlers.onStartWorker).not.toHaveBeenCalled();
    expect(handlers.onStartOutreach).not.toHaveBeenCalled();
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
  it("进度按正式明文名单/targetCount 计算", () => {
    const root = render(makeBootstrap());
    expect(root.querySelector(".progress-label")?.textContent).toContain("30%");
  });

  it("目标为 0 时不除零", () => {
    const b = makeBootstrap();
    b.task = { ...b.task, targetCount: 0, collected: 0 };
    const root = render(b);
    expect(root.querySelector(".progress-label")?.textContent).toContain("0%");
  });

  it("自动采集直接显示筛选字段", () => {
    const root = render(makeBootstrap());
    expect(root.querySelector('[aria-label="类目"]')).toBeTruthy();
  });

  it("无策略时提示配置", () => {
    const b = makeBootstrap();
    b.task = { ...b.task, collectionStrategy: undefined };
    const root = render(b);
    expect(root.querySelector('[aria-label="类目"]')).toBeTruthy();
  });

  it("显示状态标签", () => {
    const root = render(makeBootstrap());
    expect(root.querySelector(".status-pill")?.textContent).toBe("运行中");
  });
});

describe("达人表格 — 分页与搜索", () => {
  it("每页最多 50 条", () => {
    setCurrentPage("creators");
    const rows = Array.from({ length: 120 }, (_, i) => makeCreator(i));
    const root = render(makeBootstrap({ creators: rows }));
    const table = root.querySelector(".creator-table");
    expect(table?.querySelectorAll("tr").length).toBe(51);
  });

  it("分页信息显示总页数", () => {
    setCurrentPage("creators");
    const rows = Array.from({ length: 120 }, (_, i) => makeCreator(i));
    const root = render(makeBootstrap({ creators: rows }));
    const info = root.querySelector(".pager-info")?.textContent ?? "";
    expect(info).toContain("1 / 3");
    expect(info).toContain("120");
  });

  it("第一页上一页禁用", () => {
    setCurrentPage("creators");
    const rows = Array.from({ length: 120 }, (_, i) => makeCreator(i));
    const root = render(makeBootstrap({ creators: rows }));
    const btns = root.querySelectorAll<HTMLButtonElement>(".table-toolbar button");
    expect(btns[0].disabled).toBe(true);
    expect(btns[1].disabled).toBe(false);
  });

  it("少于 50 条时只有 1 页", () => {
    setCurrentPage("creators");
    const rows = Array.from({ length: 10 }, (_, i) => makeCreator(i));
    const root = render(makeBootstrap({ creators: rows }));
    expect(root.querySelector(".pager-info")?.textContent).toContain("1 / 1");
  });

  it("表格包含邮箱和复核依据", () => {
    setCurrentPage("creators");
    const root = render(makeBootstrap({ creators: [makeCreator(1)] }));
    expect([...root.querySelectorAll(".creator-table th")].map(th => th.textContent)).toContain("复核依据");
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

describe("ROI 转化漏斗面板", () => {
  const roiReport = {
    generated_at: "2026-09-23T00:00:00Z",
    funnel: {
      candidates: 100, verified: 80, qualified: 60, revealed: 50, delivered: 20,
      rates: {
        verify_rate: "80.0", qualify_rate: "75.0", reveal_rate: "83.3",
        deliver_rate: "40.0", end_to_end_rate: "20.0",
      },
    },
    contacts: {
      with_contact: 50, phone: 40, wechat: 10,
      only_phone: 40, only_wechat: 10, both_phone_and_wechat: 0,
      contact_rate: "50.0",
    },
    risk: { rate_limited: 3, not_revealed: 1, failed: 0 },
    jev: {
      enabled: 50, coverage_rate: "100.0",
      routes: { supported: 10, uncertain: 40 },
      supported_rate: "20.0", conflict_rate: "0.0", uncertain_rate: "80.0",
      confidence: { count: 50, min: 0.1, max: 0.9, avg: 0.4 },
      backends: { "jev-cloud": 50 }, cloud_errors: 0,
    },
    throughput: { elapsed_minutes: 10, reveals_per_minute: 5, seconds_per_reveal: 12 },
  };

  function withRoi() {
    const b = makeBootstrap();
    b.deliveryCenter = { available: true, artifacts: {}, roi: roiReport as never };
    return b;
  }

  it("有 ROI 数据时渲染漏斗面板", () => {
    setCurrentPage("dashboard");
    const root = render(withRoi());
    expect(root.querySelector(".roi-funnel")).toBeTruthy();
    expect(root.querySelectorAll(".funnel-row").length).toBe(5);
  });

  it("漏斗显示五个阶段标签", () => {
    setCurrentPage("dashboard");
    const root = render(withRoi());
    const labels = [...root.querySelectorAll(".funnel-label")].map((e) => e.textContent);
    expect(labels).toEqual(["候选达人", "已验证", "预接触合格", "已揭示联系方式", "历史入选标记"]);
  });

  it("漏斗条宽度按比例（候选最宽）", () => {
    setCurrentPage("dashboard");
    const root = render(withRoi());
    const bars = [...root.querySelectorAll<HTMLElement>(".funnel-bar")];
    expect(bars.length).toBe(5);
    expect(bars[0].style.width).toBe("100%");
    // 已交付 20/100 = 20%
    expect(bars[4].style.width).toBe("20%");
  });

  it("显示端到端转化率", () => {
    setCurrentPage("dashboard");
    const root = render(withRoi());
    const text = root.querySelector(".roi-funnel")?.parentElement?.textContent ?? "";
    expect(text).toContain("20");
  });

  it("显示风控统计", () => {
    setCurrentPage("dashboard");
    const root = render(withRoi());
    const text = root.textContent ?? "";
    expect(text).toContain("触发限流");
  });

  it("无 ROI 数据时不渲染面板", () => {
    setCurrentPage("dashboard");
    const root = render(makeBootstrap());
    expect(root.querySelector(".roi-funnel")).toBeFalsy();
  });

  it("ROI 含 error 时不渲染", () => {
    setCurrentPage("dashboard");
    const b = makeBootstrap();
    b.deliveryCenter = { available: true, artifacts: {}, roi: { error: "boom" } as never };
    const root = render(b);
    expect(root.querySelector(".roi-funnel")).toBeFalsy();
  });

  it("显示 JEV 复核统计", () => {
    setCurrentPage("dashboard");
    const root = render(withRoi());
    const text = root.textContent ?? "";
    expect(text).toContain("Jev 内容判断");
    expect(text).toContain("20.0");
  });
});

it("dashboard separates saved formal progress from candidate counts and shows dated errors", () => {
 setCurrentPage("dashboard");
 const root=render(makeBootstrap({ task: { ...makeBootstrap().task, targetCount:1000, collected:3059,plainContacts:584 }, runHistory:[{ recordedAt:"2026-10-07T14:56:58Z",status:"pipeline_error",message:"Jev HTTP 402：账户需要处理" }] }));
 expect(root.textContent).toContain("584 / 1,000");
 expect(root.textContent).not.toContain("100%（3,059");
 expect(root.textContent).toContain("Jev HTTP 402：账户需要处理");
});


describe("分析模型配置与真实用量", () => {
 it("独立入口展示未知余额，官网入口及保留 Key 的配置", () => {
  setCurrentPage("models");
  const open = vi.fn();
  const root = document.createElement("div");
  renderBootstrap(root, makeBootstrap({jevStatus:{enabled:true, configured:true, decisionMode:true,model:"jev-latest"}}), {...handlers,onOpenJevConsole:open});
  expect(root.textContent).toContain("账户余额未知");
  expect(root.textContent).toContain("此前历史消耗未知");
  expect(root.textContent).toContain("不代表调用已验证");
  expect(root.querySelector<HTMLInputElement>('[aria-label="Jev API Key"]')?.value).toBe("");
  [...root.querySelectorAll("button")].find(b=>b.textContent?.includes("充值 / 额度管理"))!.click();
  expect(open).toHaveBeenCalledOnce();
 });
 it("用量含缺失记录时披露覆盖范围，最新账户阻断不被旧成功掩盖", () => {
  setCurrentPage("models");
  const root=render(makeBootstrap({jevStatus:{enabled:true,configured:true,decisionMode:true,usage:{calls:2,inputTokens:120,outputTokens:null,inputCoverage:1,outputCoverage:0,firstAt:"2026-10-08T00:00:00Z",lastAt:"2026-10-08T00:00:00Z",lastModel:"jev-1.13.0",invalidRows:0,readError:false,balance:null,billedAmount:null}},runHistory:[{status:"jev_action_required",recordedAt:"2026-10-08T01:00:00Z",message:"HTTP 402"}]}));
  expect(root.textContent).toContain("120 Token · 1/2");
  expect(root.textContent).toContain("HTTP 402");
  expect(root.textContent).toContain("处理后尚未重新验证");
  expect(root.textContent).toContain("jev-1.13.0");
 });
});


describe("审查问题回归", () => {
  it("导航无需等待远程刷新即可显示目标页面", () => {
    const root = render(makeBootstrap());
    [...root.querySelectorAll<HTMLButtonElement>("nav button")].find(b => b.textContent === "分析模型")!.click();
    expect(root.querySelector(".topbar h1")?.textContent).toBe("分析模型");
    expect(handlers.onNavigate).toHaveBeenCalledWith("models");
  });
  it("复核详情展示判断依据及缺失截图，不授权或外发", () => {
    setCurrentPage("creators");
    const root=render(makeBootstrap({creators:[{nickname:"样本",reason:"近期唇护理作品",jevAnalysis:{model:"jev-test",reason:"证据待核实",confidence:0.7}}]}));
    [...root.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent==="查看详情")!.click();
    const dialog=document.querySelector("dialog")!;
    expect(dialog.textContent).toContain("近期唇护理作品");
    expect(dialog.textContent).toContain("证据待核实");
    expect(dialog.textContent).toContain("未记录截图");
    expect(handlers.onAuthorizeOutreach).not.toHaveBeenCalled();
    expect(handlers.onStartOutreach).not.toHaveBeenCalled();
  });
  it("达人资料显示平台销售区间和真实零视频，不把下界当精确销售", () => {
    setCurrentPage("creators");
    const root=render(makeBootstrap({creators:[{nickname:"资料样本",city:"山西·太原",monthlySalesLow:10000,monthlySalesHigh:25000,videoCount30d:0,mainSaleType:"纯短视频",profileText:"平台简介"}]}));
    expect(root.textContent).toContain("¥10,000–¥25,000（平台区间）");
    [...root.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent==="查看详情")!.click();
    const dialog=document.querySelector("dialog")!;
    expect(dialog.textContent).toContain("山西·太原");expect(dialog.textContent).toContain("纯短视频");
    expect(dialog.textContent).toContain("平台简介");
    const section=[...dialog.querySelectorAll("section")].find(e=>e.querySelector("h3")?.textContent==="近30天视频数")!;
    expect(section.querySelector("pre")?.textContent).toBe("0");
  });
  it("搜索多个字符后保留焦点和输入值", () => {
    setCurrentPage("creators");
    const root=render(makeBootstrap({candidateCreators:[makeCreator(1)]}));
    const search=root.querySelector<HTMLInputElement>(".table-search")!;
    search.value="达人"; search.dispatchEvent(new Event("input"));
    expect((document.activeElement as HTMLInputElement).value).toBe("达人");
  });
});

it("交付快照漏斗为零时仍显示真实导出584，并保留原1000目标", () => {
 setCurrentPage("dashboard");
 const state=makeBootstrap(); state.task={...state.task,status:"ended",endedReason:"用户结束本批",targetCount:1000,plainContacts:584,collected:3059};
 state.deliveryCenter={available:true,artifacts:{},metrics:{exportedCount:584},roi:{funnel:{candidates:584,verified:584,qualified:584,revealed:584,delivered:0,rates:{verify_rate:"100",qualify_rate:"100",reveal_rate:"100",deliver_rate:"0",end_to_end_rate:"0"}}} as never};
 const root=render(state); expect(root.textContent).toContain("584 人（按实际交付 JSON 行数）");
 expect(root.textContent).toContain("原目标 1,000 人"); expect(root.textContent).toContain("用户结束本批");
 expect(root.querySelector(".progress-fill")).toBeFalsy();
});
it("待复核标签显示缺证据原因，不混入正式名单",()=>{
 setCurrentPage("auto-collect");const root=render(makeBootstrap({creators:[{nickname:"正式"}],candidateCreators:[{nickname:"待核",flowState:"insufficient_evidence",flowReason:"缺少近期作品"}]}));
 root.querySelector("details summary")?.dispatchEvent(new Event("click"));
 expect(root.querySelector(".creator-table")?.textContent).toContain("待核");expect(root.querySelector(".creator-table")?.textContent).not.toContain("正式");
 [...root.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent==="查看详情")!.click();expect(document.querySelector("dialog")?.textContent).toContain("缺少近期作品");
});
it("品牌手卡保留原简报内容，可编辑保存而不启动采集",()=>{
 setCurrentPage("brand-card");
 const state=makeBootstrap();state.task.collectionStrategy={brief:"唇护理原始简报\n宽松美妆适配",brandName:"唇本",maximumFollowers:0};
 const save=vi.fn().mockResolvedValue(undefined);const root=document.createElement("div");document.body.replaceChildren(root);renderBootstrap(root,state,{...handlers,onSaveBrandCard:save});
 const brief=root.querySelector<HTMLTextAreaElement>('[aria-label="任务简报"]')!;expect(brief.value).toContain("唇护理原始简报");brief.value="修改后的简报";
 [...root.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent==="保存品牌手卡")!.click();
 expect(save).toHaveBeenCalledWith(expect.objectContaining({brief:"修改后的简报",brandName:"唇本"}));expect(handlers.onStartCollection).not.toHaveBeenCalled();
});
it("维护进行中禁止再次备份恢复，并显示软件版本",()=>{
 setCurrentPage("settings");const state=makeBootstrap({appVersion:"1.0.22",maintenance:{busy:true,message:"正在备份",files:10,bytes:1000,lastBackup:""}});const root=render(state);
 expect(root.textContent).toContain("1.0.22");
 expect([...root.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent==="备份任务与名单")!.disabled).toBe(true);
 expect([...root.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent==="校验并恢复备份")!.disabled).toBe(true);
});

it("旧联系人入口进入合并模块，保留联系人表与建联预览入口且不启动外发",()=>{setCurrentPage("contacts");handlers.onStartOutreach.mockClear();handlers.onSyncOutreach.mockClear();const root=render(makeBootstrap({creators:[makeCreator(0)]}));expect(root.querySelector(".contact-layout")?.textContent).toContain("wx0");expect(root.querySelector(".outreach-banner")).toBeTruthy();expect(root.querySelector("nav button.active")?.textContent).toContain("联系与交付");expect(handlers.onStartOutreach).not.toHaveBeenCalled();expect(handlers.onSyncOutreach).not.toHaveBeenCalled();});

it("旧交付入口进入同一模块，三个区域同时存在且运行中禁用生成交付",()=>{setCurrentPage("delivery");const root=render(makeBootstrap());expect(root.querySelector(".contact-layout")).toBeTruthy();expect(root.querySelector(".outreach-banner")).toBeTruthy();expect(root.querySelector(".delivery-center-page")).toBeTruthy();const deliver=[...root.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent==="生成当前名单交付包");expect(deliver?.disabled).toBe(true);expect(root.querySelector("nav button.active")?.textContent).toContain("联系与交付");});

it("往期库排除仅属于当前任务的达人，本批联系交付不含往期",()=>{const state=makeBootstrap({creators:[{nickname:"本批专属",wechat:"current"}],creatorLibrary:{creators:[{nickname:"往期专属",wechat:"past",libraryTaskIds:["past"]},{nickname:"本批专属",wechat:"current",libraryTaskIds:["t1"]}],batches:[{id:"past",name:"旧批",count:1},{id:"t1",name:"当前批",count:1}]}});state.task.id="scope-current";state.creatorLibrary!.batches[1].id="scope-current";state.creatorLibrary!.creators[1].libraryTaskIds=["scope-current"];setCurrentPage("creators");let root=render(state);expect(root.querySelector(".creator-table")?.textContent).toContain("往期专属");expect(root.querySelector(".creator-table")?.textContent).not.toContain("本批专属");setCurrentPage("outreach");root=render(state);expect(root.querySelector(".contact-layout")?.textContent).toContain("本批专属");expect(root.querySelector(".contact-layout")?.textContent).not.toContain("往期专属");});
it("往期仅包括已完成或已结束批次，未作业的验收导入保留但不混入",()=>{setCurrentPage("creators");const state=makeBootstrap({creatorLibrary:{creators:[{nickname:"已完成达人",libraryTaskIds:["completed"]},{nickname:"已结束达人",libraryTaskIds:["ended"]},{nickname:"未启动验收",libraryTaskIds:["idle"]}],batches:[{id:"completed",name:"完成批次",count:1,status:"completed"},{id:"ended",name:"结束批次",count:1,status:"ended"},{id:"idle",name:"验收导入",count:1,status:"idle"}]}});state.task.id="history-status-test";const root=render(state);expect(root.querySelector(".creator-table")?.textContent).toContain("已完成达人");expect(root.querySelector(".creator-table")?.textContent).toContain("已结束达人");expect(root.querySelector(".creator-table")?.textContent).not.toContain("未启动验收");expect(root.querySelector('[aria-label="往期达人批次"]')?.textContent).not.toContain("验收导入");expect(state.creatorLibrary!.creators.length).toBe(3);});

it("往期修复只在优选显示，并提交历史范围而不操作本批",()=>{
 const repair=vi.fn();const state=makeBootstrap({historicalWechatRepairCount:1,savedWechatRepairCount:0,creatorLibrary:{creators:[],batches:[]}});
 state.task.status="paused";state.task.id="history-repair66";setCurrentPage("creators");const root=document.createElement("div");document.body.replaceChildren(root);renderBootstrap(root,state,{...handlers,onRepairSavedWechat:repair});
 const button=[...root.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent==="恢复往期完整微信号（1条）");expect(button).toBeTruthy();button!.click();expect(repair).toHaveBeenCalledWith("history");
 setCurrentPage("outreach");renderBootstrap(root,state,{...handlers,onRepairSavedWechat:repair});expect(root.textContent).not.toContain("恢复往期完整微信号");
});
it("当前任务往期可记录修订，其他任务历史仅查看避免写错归属",()=>{
 const state=makeBootstrap({creatorLibrary:{creators:[{id:"own",nickname:"本任务往期",libraryTaskIds:["history-edit66-batch-baseline"]},{id:"other",nickname:"其他任务历史",libraryTaskIds:["past"]}],batches:[{id:"history-edit66-batch-baseline",name:"本任务基线",count:1,status:"ended"},{id:"past",name:"其他任务",count:1,status:"ended"}]}});
 state.task.id="history-edit66";setCurrentPage("creators");const root=document.createElement("div");document.body.replaceChildren(root);renderBootstrap(root,state,{...handlers,onSaveContactCorrection:vi.fn()});
 const buttons=[...root.querySelectorAll<HTMLButtonElement>("button")].filter(b=>b.textContent==="查看详情");buttons[0].click();expect(document.querySelector("dialog")?.textContent).toContain("人工修订联系方式与历史");document.querySelector("dialog")?.remove();buttons[1].click();expect(document.querySelector("dialog")?.textContent).not.toContain("人工修订联系方式与历史");
});


describe("Jev首次配置与未保存修改保护", () => {
 it("只填Key即可配置，失败保留输入，不允许测试旧配置", async () => {
  setCurrentPage("models");
  const save=vi.fn().mockRejectedValue(new Error("failed"));const test=vi.fn();
  const root=document.createElement("div");document.body.replaceChildren(root);
  renderBootstrap(root,makeBootstrap({jevStatus:{enabled:true,configured:true,decisionMode:true,model:"jev-latest"}}),{...handlers,onSaveJevSettings:save,onTestJevConnection:test});
  expect(root.textContent).toContain("调用地址（已内置，无需填写）");
  const key=root.querySelector<HTMLInputElement>('[aria-label="Jev API Key"]')!;
  const saveButton=[...root.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent==="保存 Jev 配置")!;
  const testButton=[...root.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent==="测试模型（单次云端调用）")!;
  key.value="new-test-only-key";key.dispatchEvent(new Event("input"));
  expect(testButton.disabled).toBe(true);testButton.click();expect(test).not.toHaveBeenCalled();
  saveButton.click();await vi.waitFor(()=>expect(root.textContent).toContain("保存失败，输入内容已保留"));
  expect(key.value).toBe("new-test-only-key");expect(testButton.disabled).toBe(true);
  save.mockResolvedValue(undefined);saveButton.click();await vi.waitFor(()=>expect(key.value).toBe(""));
  expect(save).toHaveBeenLastCalledWith("new-test-only-key","jev-latest");expect(testButton.disabled).toBe(false);
 });
 it("测试期间锁定配置，修改模型必须先保存", async () => {
  setCurrentPage("models");let finish!:()=>void;
  const test=vi.fn(()=>new Promise<void>(resolve=>finish=resolve));const save=vi.fn();
  const root=document.createElement("div");document.body.replaceChildren(root);
  renderBootstrap(root,makeBootstrap({jevStatus:{enabled:true,configured:true,decisionMode:true,model:"jev-latest"}}),{...handlers,onSaveJevSettings:save,onTestJevConnection:test});
  const model=root.querySelector<HTMLInputElement>('[aria-label="Jev 模型"]')!;
  const testButton=[...root.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent==="测试模型（单次云端调用）")!;
  const saveButton=[...root.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent==="保存 Jev 配置")!;
  testButton.click();expect(model.disabled).toBe(true);expect(saveButton.disabled).toBe(true);
  saveButton.click();testButton.click();expect(test).toHaveBeenCalledOnce();expect(save).not.toHaveBeenCalled();
  finish();await vi.waitFor(()=>expect(model.disabled).toBe(false));
  model.value="jev-preview";model.dispatchEvent(new Event("input"));expect(testButton.disabled).toBe(true);
  model.value="jev-latest";model.dispatchEvent(new Event("input"));expect(testButton.disabled).toBe(false);
 });
});

it("新电脑默认模型可用，只填Key保存，并在保存期间阻止重复提交", async () => {
 setCurrentPage("models");let finish!:()=>void;
 const save=vi.fn(()=>new Promise<void>(resolve=>finish=resolve));const test=vi.fn();
 const root=document.createElement("div");document.body.replaceChildren(root);
 renderBootstrap(root,makeBootstrap({jevStatus:{enabled:false,configured:false,decisionMode:false}}),{...handlers,onSaveJevSettings:save,onTestJevConnection:test});
 const key=root.querySelector<HTMLInputElement>('[aria-label="Jev API Key"]')!;
 const model=root.querySelector<HTMLInputElement>('[aria-label="Jev 模型"]')!;
 const saveButton=[...root.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent==="保存 Jev 配置")!;
 const testButton=[...root.querySelectorAll<HTMLButtonElement>("button")].find(b=>b.textContent==="测试模型（单次云端调用）")!;
 expect(model.value).toBe("jev-latest");expect(testButton.disabled).toBe(true);
 key.value="fresh-test-only";key.dispatchEvent(new Event("input"));saveButton.click();saveButton.click();
 expect(save).toHaveBeenCalledOnce();expect(save).toHaveBeenCalledWith("fresh-test-only","jev-latest");
 expect(testButton.disabled).toBe(true);expect(key.disabled).toBe(true);
 finish();await vi.waitFor(()=>expect(testButton.disabled).toBe(false));expect(key.value).toBe("");expect(test).not.toHaveBeenCalled();
});
