/**
 * 采集策略编辑表单
 *
 * 字段对齐 electron/main.cjs 的 sanitizeCollectionStrategy，
 * 保证提交后能被后端正确接受（否则 startCollection 会写入不完整策略）。
 */

import type { CollectionStrategy } from "../types";
import { h } from "../store";

export interface StrategyFormHandlers {
  onSubmit(strategy: CollectionStrategy): void;
  onCancel(): void;
}

/** 表单字段定义 */
interface FieldDef {
  key: keyof CollectionStrategy;
  label: string;
  type: "text" | "number" | "select" | "checkbox" | "textarea" | "multiselect";
  hint?: string;
  options?: { value: string; label: string }[];
}

const CATEGORY_OPTIONS = [
  { value: "美妆个护", label: "美妆个护（美妆 + 个护家清）" },
  { value: "个护家清", label: "个护家清" },
  { value: "服饰内衣", label: "服饰内衣" },
  { value: "母婴宠物", label: "母婴宠物" },
  { value: "食品饮料", label: "食品饮料" },
  { value: "泛生活好物", label: "泛生活好物" },
];

const DISCOVERY_OPTIONS = [
  { value: "structured_browse", label: "类目搜索（推荐，无需关键词）" },
  { value: "keyword_search", label: "关键词搜索" },
];

const FIELDS: FieldDef[] = [
  { key: "category", label: "类目", type: "select", options: CATEGORY_OPTIONS },
  {
    key: "sourceDiscoveryMode",
    label: "发现方式",
    type: "select",
    options: DISCOVERY_OPTIONS,
    hint: "类目搜索不需要关键词；关键词搜索需填写关键词列表",
  },
  { key: "targetCount", label: "目标数量", type: "number", hint: "1-5000" },
  { key: "minimumFollowers", label: "粉丝下限", type: "number" },
  { key: "maximumFollowers", label: "粉丝上限", type: "number" },
  { key: "minimumMonthlySales", label: "月销下限", type: "number" },
  { key: "creatorLevels", label: "达人等级", type: "multiselect",
    options: [
      { value: "1", label: "LV1" },
      { value: "2", label: "LV2" },
      { value: "3", label: "LV3" },
      { value: "4", label: "LV4" },
    ] },
  { key: "activeShops", label: "采集店铺", type: "multiselect",
    options: [
      { value: "A", label: "抖店 A" },
      { value: "B", label: "抖店 B" },
    ] },
  { key: "requireContact", label: "必须有联系方式", type: "checkbox" },
  { key: "keywords", label: "关键词", type: "textarea",
    hint: "每行一个；类目搜索模式下可留空" },
  { key: "exclusions", label: "排除词", type: "textarea", hint: "每行一个" },
  { key: "brief", label: "任务简报", type: "textarea",
    hint: "描述合作方式、内容要求等，供审核规则参考" },
];

function toInputValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join("\n");
  return String(value);
}

function toArray(text: string): string[] {
  return text
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function renderStrategyForm(
  current: CollectionStrategy | undefined,
  handlers: StrategyFormHandlers,
): HTMLElement {
  // 默认值：新建任务或策略为空时给出可用配置，避免用户面对全空表单
  const DEFAULTS: CollectionStrategy = {
    sourceType: "brief",
    brief: "",
    viralExamples: "",
    category: "美妆个护",
    creatorLevels: [1, 2],
    minimumFollowers: 0,
    maximumFollowers: 100000,
    minimumMonthlySales: 0,
    contentType: "短视频",
    requireContact: true,
    activeShops: ["A", "B"],
    keywords: [],
    exclusions: [],
    targetCount: 200,
    autoStart: true,
    applyMode: "next-batch",
    sourceDiscoveryMode: "structured_browse",
  };
  const s: CollectionStrategy =
    current && Object.keys(current).length ? { ...DEFAULTS, ...current } : { ...DEFAULTS };

  // 数组字段若为空数组，回落到默认（用户可能清空过）
  if (!Array.isArray(s.creatorLevels) || !s.creatorLevels.length) {
    s.creatorLevels = DEFAULTS.creatorLevels;
  }
  if (!Array.isArray(s.activeShops) || !s.activeShops.length) {
    s.activeShops = DEFAULTS.activeShops;
  }

  const form = h("form", { class: "strategy-form" });
  const fieldNodes: Record<string, HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement> = {};

  for (const def of FIELDS) {
    const row = h("div", { class: "form-row" });
    row.append(h("label", { class: "form-label", text: def.label }));

    let input: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

    if (def.type === "select") {
      const sel = h("select", { class: "form-control" }) as HTMLSelectElement;
      for (const opt of def.options ?? []) {
        const o = h("option", { value: opt.value, text: opt.label }) as HTMLOptionElement;
        sel.append(o);
      }
      sel.value = String(s[def.key] ?? def.options?.[0]?.value ?? "");
      input = sel;
    } else if (def.type === "multiselect") {
      const wrap = h("div", { class: "multi-select" });
      const selected = new Set(
        (Array.isArray(s[def.key]) ? (s[def.key] as unknown[]) : []).map(String),
      );
      for (const opt of def.options ?? []) {
        const cb = h("input", { type: "checkbox", value: opt.value }) as HTMLInputElement;
        cb.checked = selected.has(opt.value);
        cb.dataset.multiKey = String(def.key);
        const lbl = h("label", { class: "multi-item" }, [cb, h("span", { text: opt.label })]);
        wrap.append(lbl);
      }
      row.append(wrap);
      row.append(def.hint ? h("small", { class: "form-hint", text: def.hint }) : "");
      form.append(row);
      continue;
    } else if (def.type === "checkbox") {
      const cb = h("input", { type: "checkbox", class: "form-check" }) as HTMLInputElement;
      cb.checked = s[def.key] !== false;
      input = cb;
    } else if (def.type === "textarea") {
      const ta = h("textarea", { class: "form-control", rows: "4" }) as HTMLTextAreaElement;
      ta.value = toInputValue(s[def.key]);
      input = ta;
    } else if (def.type === "number") {
      const num = h("input", { type: "number", class: "form-control" }) as HTMLInputElement;
      num.value = toInputValue(s[def.key]);
      input = num;
    } else {
      const txt = h("input", { type: "text", class: "form-control" }) as HTMLInputElement;
      txt.value = toInputValue(s[def.key]);
      input = txt;
    }

    fieldNodes[String(def.key)] = input;
    row.append(input);
    if (def.hint) row.append(h("small", { class: "form-hint", text: def.hint }));
    form.append(row);
  }

  const error = h("div", { class: "form-error" });

  const submit = h("button", { type: "submit", class: "primary" }, ["保存策略"]);
  const cancel = h("button", {
    type: "button",
    onclick: () => handlers.onCancel(),
  }, ["取消"]);

  form.append(h("div", { class: "form-actions" }, [submit, cancel]));

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    error.textContent = "";

    const get = (k: string) => fieldNodes[k];
    const num = (k: string) => Number((get(k) as HTMLInputElement)?.value) || 0;
    const txt = (k: string) => (get(k) as HTMLInputElement)?.value ?? "";
    const arr = (k: string) => toArray((get(k) as HTMLTextAreaElement)?.value ?? "");

    // 多选字段
    const multi = (key: string): string[] => {
      const boxes = form.querySelectorAll<HTMLInputElement>(
        `input[data-multi-key="${key}"]:checked`,
      );
      return [...boxes].map((b) => b.value);
    };

    const levels = multi("creatorLevels").map(Number).filter((n) => n >= 1 && n <= 4);
    const shops = multi("activeShops");
    const target = num("targetCount");
    const mode = txt("sourceDiscoveryMode");
    const keywords = arr("keywords");

    // 校验
    if (!levels.length) return void (error.textContent = "请至少选择一个达人等级");
    if (!shops.length) return void (error.textContent = "请至少选择一个采集店铺");
    if (target < 1 || target > 5000) return void (error.textContent = "目标数量需在 1-5000 之间");
    if (mode === "keyword_search" && !keywords.length) {
      return void (error.textContent = "关键词搜索模式需要至少一个关键词");
    }
    const maxF = num("maximumFollowers");
    const minF = num("minimumFollowers");
    if (maxF && minF && minF > maxF) {
      return void (error.textContent = "粉丝下限不能大于上限");
    }

    handlers.onSubmit({
      ...s,
      sourceType: s.sourceType || "brief",
      brief: txt("brief"),
      viralExamples: s.viralExamples || "",
      category: txt("category"),
      creatorLevels: levels,
      minimumFollowers: minF,
      maximumFollowers: maxF || 500000,
      minimumMonthlySales: num("minimumMonthlySales"),
      contentType: s.contentType || "短视频",
      requireContact: (get("requireContact") as HTMLInputElement)?.checked ?? true,
      activeShops: shops,
      keywords,
      exclusions: arr("exclusions"),
      targetCount: target,
      autoStart: true,
      applyMode: "next-batch",
      sourceDiscoveryMode: mode,
    });
  });

  form.append(error);
  return form;
}
