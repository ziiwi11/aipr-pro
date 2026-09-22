import { describe, it, expect, vi } from "vitest";
import { Store, h, mount, fmtNum, fmtTime } from "./store";

describe("Store", () => {
  it("初始化时保存初始状态", () => {
    const s = new Store({ n: 1 });
    expect(s.get()).toEqual({ n: 1 });
  });

  it("set 接受部分对象并合并", () => {
    const s = new Store({ a: 1, b: 2 });
    s.set({ b: 3 });
    expect(s.get()).toEqual({ a: 1, b: 3 });
  });

  it("set 接受函数形式", () => {
    const s = new Store({ n: 1 });
    s.set((prev) => ({ n: prev.n + 10 }));
    expect(s.get().n).toBe(11);
  });

  it("subscribe 立即收到当前状态", () => {
    const s = new Store({ n: 1 });
    const fn = vi.fn();
    s.subscribe(fn);
    expect(fn).toHaveBeenCalledWith({ n: 1 });
  });

  it("状态变更时通知订阅者", () => {
    const s = new Store({ n: 1 });
    const fn = vi.fn();
    s.subscribe(fn);
    fn.mockClear();
    s.set({ n: 2 });
    expect(fn).toHaveBeenCalledWith({ n: 2 });
  });

  it("取消订阅后不再收到通知", () => {
    const s = new Store({ n: 1 });
    const fn = vi.fn();
    const unsub = s.subscribe(fn);
    fn.mockClear();
    unsub();
    s.set({ n: 2 });
    expect(fn).not.toHaveBeenCalled();
  });

  it("订阅者抛错不影响其他订阅者", () => {
    const s = new Store({ n: 1 });
    const bad = vi.fn(() => {
      throw new Error("boom");
    });
    const good = vi.fn();
    s.subscribe(bad);
    s.subscribe(good);
    bad.mockClear();
    good.mockClear();
    expect(() => s.set({ n: 2 })).not.toThrow();
    expect(good).toHaveBeenCalled();
  });
});

describe("h() DOM 构造器", () => {
  it("创建元素并设置文本", () => {
    const el = h("div", { text: "hi" });
    expect(el.tagName).toBe("DIV");
    expect(el.textContent).toBe("hi");
  });

  it("设置 class", () => {
    const el = h("span", { class: "a b" });
    expect(el.className).toBe("a b");
  });

  it("跳过 null / undefined / false 属性", () => {
    const el = h("div", { title: null, id: undefined, hidden: false, "data-x": "y" });
    expect(el.hasAttribute("title")).toBe(false);
    expect(el.hasAttribute("id")).toBe(false);
    expect(el.hasAttribute("hidden")).toBe(false);
    expect(el.getAttribute("data-x")).toBe("y");
  });

  it("绑定事件（on* 前缀）", () => {
    const fn = vi.fn();
    const el = h("button", { onclick: fn });
    el.click();
    expect(fn).toHaveBeenCalledOnce();
  });

  it("设置 dataset", () => {
    const el = h("div", { dataset: { key: "v" } });
    expect(el.dataset.key).toBe("v");
  });

  it("递归追加子节点（含字符串）", () => {
    const el = h("div", {}, [h("span", { text: "a" }), "b"]);
    expect(el.children.length).toBe(1);
    expect(el.textContent).toBe("ab");
  });
});

describe("mount()", () => {
  it("清空并重填容器", () => {
    const c = document.createElement("div");
    c.innerHTML = "<p>old</p>";
    mount(c, h("span", { text: "new" }));
    expect(c.children.length).toBe(1);
    expect(c.textContent).toBe("new");
  });
});

describe("fmtNum()", () => {
  it("格式化千分位", () => {
    expect(fmtNum(1234567)).toBe("1,234,567");
  });

  it("非数字回落到 0", () => {
    expect(fmtNum(undefined)).toBe("0");
    expect(fmtNum("abc")).toBe("0");
    expect(fmtNum(NaN)).toBe("0");
  });

  it("接受数字字符串", () => {
    expect(fmtNum("1000")).toBe("1,000");
  });
});

describe("fmtTime()", () => {
  it("空值返回占位符", () => {
    expect(fmtTime(null)).toBe("-");
    expect(fmtTime("")).toBe("-");
  });

  it("非法日期原样返回", () => {
    expect(fmtTime("not-a-date")).toBe("not-a-date");
  });

  it("合法日期格式化为本地时间", () => {
    const out = fmtTime("2026-09-22T00:00:00Z");
    expect(out).not.toBe("-");
    expect(out.length).toBeGreaterThan(5);
  });
});
