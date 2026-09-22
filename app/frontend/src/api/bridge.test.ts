import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import * as api from "./bridge";

/** 构造一个假的 aiprDesktop 桥 */
function installFakeBridge() {
  const calls: Array<{ method: string; args: unknown[] }> = [];
  const record = (method: string) => (...args: unknown[]) => {
    calls.push({ method, args });
    return Promise.resolve({ ok: true, method });
  };
  const bridge = {
    getBootstrap: record("getBootstrap"),
    getRealtimeCreatorFlow: record("getRealtimeCreatorFlow"),
    getPlatformReadiness: record("getPlatformReadiness"),
    listTasks: record("listTasks"),
    createTask: record("createTask"),
    selectTask: record("selectTask"),
    saveTask: record("saveTask"),
    importFile: record("importFile"),
    importBrief: record("importBrief"),
    importDelivery: record("importDelivery"),
    loadDeliveryPath: record("loadDeliveryPath"),
    launchBrowsers: record("launchBrowsers"),
    layoutEmbeddedShop: record("layoutEmbeddedShop"),
    hideEmbeddedShops: record("hideEmbeddedShops"),
    controlEmbeddedShop: record("controlEmbeddedShop"),
    probeLogin: record("probeLogin"),
    startCollection: record("startCollection"),
    startWorker: record("startWorker"),
    pauseWorker: record("pauseWorker"),
    exportOriginal: record("exportOriginal"),
    openPath: record("openPath"),
    getDeliveryCenter: record("getDeliveryCenter"),
    previewRobotHandoff: record("previewRobotHandoff"),
    copyText: record("copyText"),
    exportRules: record("exportRules"),
    importRules: record("importRules"),
    queueOutreach: record("queueOutreach"),
    getIntegrationPaths: record("getIntegrationPaths"),
    getOutreachState: record("getOutreachState"),
    previewOutreachAuthorization: record("previewOutreachAuthorization"),
    authorizeOutreachBatch: record("authorizeOutreachBatch"),
    syncOutreachBatch: record("syncOutreachBatch"),
    startOutreachBatch: record("startOutreachBatch"),
    getRunHistory: record("getRunHistory"),
    onWorkerEvent: vi.fn(() => () => {}),
    onShopBrowserEvent: vi.fn(() => () => {}),
  };
  (window as unknown as Record<string, unknown>).aiprDesktop = bridge;
  return { bridge, calls };
}

describe("bridge 在无 Electron 环境", () => {
  beforeEach(() => {
    delete (window as unknown as Record<string, unknown>).aiprDesktop;
  });

  it("isElectron 返回 false", () => {
    expect(api.isElectron()).toBe(false);
  });

  it("调用抛错并给出可读提示", () => {
    // api() 同步抛错（不是返回 rejected Promise），因此用 toThrow 断言
    expect(() => api.getBootstrap()).toThrow(/桥接不可用/);
  });

  it("事件订阅在无桥时返回空函数且不抛错", () => {
    const off = api.onWorkerEvent(() => {});
    expect(typeof off).toBe("function");
    expect(() => off()).not.toThrow();
  });
});

describe("bridge 在 Electron 环境", () => {
  let fake: ReturnType<typeof installFakeBridge>;

  beforeEach(() => {
    fake = installFakeBridge();
  });

  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).aiprDesktop;
  });

  it("isElectron 返回 true", () => {
    expect(api.isElectron()).toBe(true);
  });

  it("getBootstrap 转发到桥", async () => {
    await api.getBootstrap();
    expect(fake.calls[0].method).toBe("getBootstrap");
  });

  it("createTask 透传参数", async () => {
    await api.createTask({ name: "t", targetCount: 10 });
    expect(fake.calls[0].method).toBe("createTask");
    expect(fake.calls[0].args[0]).toEqual({ name: "t", targetCount: 10 });
  });

  it("startCollection 透传 task 与 strategy", async () => {
    const task = { id: "x" };
    const strategy = { category: "美妆个护" };
    await api.startCollection(task, strategy);
    expect(fake.calls[0].method).toBe("startCollection");
    expect(fake.calls[0].args).toEqual([task, strategy]);
  });

  it("controlEmbeddedShop 透传 shop 与 action", async () => {
    await api.controlEmbeddedShop({ shop: "A", action: "reload" });
    expect(fake.calls[0].args[0]).toEqual({ shop: "A", action: "reload" });
  });

  it("getRunHistory 带默认 limit", async () => {
    await api.getRunHistory("task-1");
    expect(fake.calls[0].args).toEqual(["task-1", 100]);
  });

  it("getRunHistory 可覆盖 limit", async () => {
    await api.getRunHistory("task-1", 10);
    expect(fake.calls[0].args).toEqual(["task-1", 10]);
  });

  it("onWorkerEvent 注册监听并返回取消函数", () => {
    const off = api.onWorkerEvent(() => {});
    expect(fake.bridge.onWorkerEvent).toHaveBeenCalledOnce();
    expect(typeof off).toBe("function");
  });

  it("全部 34 个 invoke 方法都可调用", async () => {
    const methods = [
      () => api.getBootstrap(),
      () => api.getRealtimeCreatorFlow(),
      () => api.getPlatformReadiness(),
      () => api.listTasks(),
      () => api.createTask({}),
      () => api.selectTask("a"),
      () => api.saveTask({}),
      () => api.importFile(),
      () => api.importBrief(),
      () => api.importDelivery(),
      () => api.loadDeliveryPath("p"),
      () => api.launchBrowsers(),
      () => api.layoutEmbeddedShop({}),
      () => api.hideEmbeddedShops(),
      () => api.controlEmbeddedShop({}),
      () => api.probeLogin(),
      () => api.startCollection({}, {}),
      () => api.startWorker({}),
      () => api.pauseWorker(),
      () => api.exportOriginal({}),
      () => api.openPath("p"),
      () => api.getDeliveryCenter(),
      () => api.previewRobotHandoff(),
      () => api.copyText("x"),
      () => api.exportRules({}),
      () => api.importRules(),
      () => api.queueOutreach({}),
      () => api.getIntegrationPaths(),
      () => api.getOutreachState(),
      () => api.previewOutreachAuthorization(["1"]),
      () => api.authorizeOutreachBatch("p"),
      () => api.syncOutreachBatch("b"),
      () => api.startOutreachBatch("b"),
      () => api.getRunHistory("t"),
    ];
    for (const call of methods) {
      await expect(call()).resolves.toBeDefined();
    }
    expect(fake.calls.length).toBe(methods.length);
  });
});
