import { describe, it, expect, vi } from "vitest";
import { renderStrategyForm } from "./strategy-form";
import type { CollectionStrategy } from "../types";

function setup(current?: CollectionStrategy) {
  const onSubmit = vi.fn();
  const onCancel = vi.fn();
  const form = renderStrategyForm(current, { onSubmit, onCancel });
  document.body.replaceChildren(form);
  return { form, onSubmit, onCancel };
}

const submit = () => {
  const btn = document.querySelector<HTMLButtonElement>('.strategy-form button[type="submit"]');
  btn?.click();
};

const errorText = () => document.querySelector(".form-error")?.textContent ?? "";

describe("策略表单 — 默认值", () => {
  it("无初始策略时给出可用默认值", () => {
    setup();
    const selects = document.querySelectorAll<HTMLSelectElement>(".strategy-form select");
    expect(selects[0].value).toBe("美妆个护");
    expect(selects[1].value).toBe("structured_browse");
  });

  it("默认勾选 LV1 与 LV2", () => {
    setup();
    const checked = [...document.querySelectorAll<HTMLInputElement>(
      'input[data-multi-key="creatorLevels"]:checked',
    )].map((c) => c.value);
    expect(checked).toEqual(["1", "2"]);
  });

  it("默认勾选店铺 A 与 B", () => {
    setup();
    const checked = [...document.querySelectorAll<HTMLInputElement>(
      'input[data-multi-key="activeShops"]:checked',
    )].map((c) => c.value);
    expect(checked).toEqual(["A", "B"]);
  });

  it("默认目标数量 200", () => {
    setup();
    const nums = document.querySelectorAll<HTMLInputElement>('.strategy-form input[type="number"]');
    expect(nums[0].value).toBe("200");
  });
});

describe("策略表单 — 读取已有策略", () => {
  it("扩大目标时保留零粉丝上限的不限制含义", () => {
    const { onSubmit } = setup({ targetCount: 500, maximumFollowers: 0 });
    const nums = document.querySelectorAll<HTMLInputElement>('.strategy-form input[type="number"]');
    nums[0].value = "1000";
    submit();
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ targetCount: 1000, maximumFollowers: 0 }));
  });
  it("用已有值覆盖默认值", () => {
    setup({ category: "服饰内衣", targetCount: 500, creatorLevels: [3, 4] });
    const selects = document.querySelectorAll<HTMLSelectElement>(".strategy-form select");
    expect(selects[0].value).toBe("服饰内衣");
    const nums = document.querySelectorAll<HTMLInputElement>('.strategy-form input[type="number"]');
    expect(nums[0].value).toBe("500");
    const checked = [...document.querySelectorAll<HTMLInputElement>(
      'input[data-multi-key="creatorLevels"]:checked',
    )].map((c) => c.value);
    expect(checked).toEqual(["3", "4"]);
  });

  it("空数组回落到默认（用户清空过）", () => {
    setup({ creatorLevels: [], activeShops: [] });
    const levels = [...document.querySelectorAll<HTMLInputElement>(
      'input[data-multi-key="creatorLevels"]:checked',
    )].map((c) => c.value);
    expect(levels).toEqual(["1", "2"]);
  });

  it("关键词数组渲染为多行文本", () => {
    setup({ keywords: ["a", "b"] });
    const tas = document.querySelectorAll<HTMLTextAreaElement>(".strategy-form textarea");
    expect(tas[0].value).toBe("a\nb");
  });
});

describe("策略表单 — 校验", () => {
  it("未选等级时报错且不提交", () => {
    const { onSubmit } = setup();
    for (const cb of document.querySelectorAll<HTMLInputElement>(
      'input[data-multi-key="creatorLevels"]',
    )) {
      cb.checked = false;
    }
    submit();
    expect(errorText()).toContain("达人等级");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("未选店铺时报错且不提交", () => {
    const { onSubmit } = setup();
    for (const cb of document.querySelectorAll<HTMLInputElement>(
      'input[data-multi-key="activeShops"]',
    )) {
      cb.checked = false;
    }
    submit();
    expect(errorText()).toContain("采集店铺");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("目标数量越界报错", () => {
    const { onSubmit } = setup();
    const nums = document.querySelectorAll<HTMLInputElement>('.strategy-form input[type="number"]');
    nums[0].value = "0";
    submit();
    expect(errorText()).toContain("1-5000");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("关键词模式无关键词时报错", () => {
    const { onSubmit } = setup();
    const selects = document.querySelectorAll<HTMLSelectElement>(".strategy-form select");
    selects[1].value = "keyword_search";
    submit();
    expect(errorText()).toContain("关键词");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("粉丝下限大于上限时报错", () => {
    const { onSubmit } = setup();
    const nums = document.querySelectorAll<HTMLInputElement>('.strategy-form input[type="number"]');
    nums[1].value = "100000"; // min
    nums[2].value = "1000"; // max
    submit();
    expect(errorText()).toContain("粉丝下限");
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("策略表单 — 提交", () => {
  it("校验通过时提交并带上全部字段", () => {
    const { onSubmit } = setup();
    submit();
    expect(onSubmit).toHaveBeenCalledOnce();
    const s = onSubmit.mock.calls[0][0] as CollectionStrategy;
    expect(s.category).toBe("美妆个护");
    expect(s.creatorLevels).toEqual([1, 2]);
    expect(s.activeShops).toEqual(["A", "B"]);
    expect(s.targetCount).toBe(200);
    expect(s.sourceDiscoveryMode).toBe("structured_browse");
    expect(s.requireContact).toBe(true);
  });

  it("关键词按行拆分", () => {
    const { onSubmit } = setup();
    const selects = document.querySelectorAll<HTMLSelectElement>(".strategy-form select");
    selects[1].value = "keyword_search";
    const tas = document.querySelectorAll<HTMLTextAreaElement>(".strategy-form textarea");
    tas[0].value = "面霜\n护肤\n\n  面膜  ";
    submit();
    const s = onSubmit.mock.calls[0][0] as CollectionStrategy;
    expect(s.keywords).toEqual(["面霜", "护肤", "面膜"]);
  });

  it("关键词支持逗号分隔", () => {
    const { onSubmit } = setup();
    const selects = document.querySelectorAll<HTMLSelectElement>(".strategy-form select");
    selects[1].value = "keyword_search";
    const tas = document.querySelectorAll<HTMLTextAreaElement>(".strategy-form textarea");
    tas[0].value = "a,b, c";
    submit();
    const s = onSubmit.mock.calls[0][0] as CollectionStrategy;
    expect(s.keywords).toEqual(["a", "b", "c"]);
  });

  it("取消按钮触发 onCancel", () => {
    const { onCancel } = setup();
    document.querySelector<HTMLButtonElement>('.strategy-form button[type="button"]')?.click();
    expect(onCancel).toHaveBeenCalledOnce();
  });
});

it("自定义达人类型保存原文，粉丝不限，不自动开始",()=>{const {onSubmit}=setup({maximumFollowers:0});const select=document.querySelector<HTMLSelectElement>('[aria-label="达人类型"]')!;select.value="__custom__";select.dispatchEvent(new Event("change"));const custom=document.querySelector<HTMLInputElement>('[aria-label="自定义达人类型"]')!;expect(custom.hidden).toBe(false);custom.value="真人生活分享";custom.dispatchEvent(new Event("input"));submit();expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({creatorType:"真人生活分享",maximumFollowers:0,autoStart:false}));});

it("微信优先获取模式可选择并保存，不自动采集",()=>{const {onSubmit}=setup();const select=document.querySelector<HTMLSelectElement>('[aria-label="联系方式获取"]')!;expect(select.value).toBe("all_channels");select.value="primary_wechat";submit();expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({contactCollectionMode:"primary_wechat",autoStart:false}));});

 it("后台同名内容类型和带货方式提交到策略，作品要求保持独立",()=>{const {onSubmit}=setup({contentType:"短视频",creatorType:"测评种草"});const select=(name:string)=>document.querySelector<HTMLSelectElement>(`select[aria-label="${name}"]`)!; expect(select("带货方式（后台）").value).toBe("视频达人");select("带货方式（后台）").value="图文达人";select("内容类型（后台）").value="时尚";submit();expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({contentType:"图文达人",platformContentTopic:"时尚",creatorType:"测评种草"}));expect([...select("类目").options].map(x=>x.value)).not.toContain("泛生活好物");});
