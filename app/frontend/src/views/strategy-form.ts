import {CREATOR_TYPES,PRESENTATIONS} from "../brief-parser";
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
  onDraftChange?(strategy:CollectionStrategy):void;
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
  {value:"美妆个护",label:"美妆 + 个护家清（分开轮流采集）"},
  ...["玩具乐器","服饰内衣","个护家清","智能家居","生鲜","美妆","母婴宠物","鲜花园艺","本地生活","食品饮料","3C数码家电","图书教育","鞋靴箱包","虚拟充值","运动户外","钟表配饰","珠宝文玩","医疗健康","酒类","滋补保健","原料包装","餐饮外卖"].map(value=>({value,label:value})),
];
const PLATFORM_TOPICS=["三农","二次元","亲子","人文社科","休闲娱乐","传统文化","体育","公益","剧情","动物","医疗健康","情感","摄影摄像","教育校园","文化","旅行","时尚","明星","母婴","汽车","法律","游戏","特效&小游戏","生活家居","生活记录","电影","电视剧","社会时政","科技","科普","综艺","美食","职场","舞蹈","艺术","财经","音乐","颜值","其他"];

const DISCOVERY_OPTIONS = [
  { value: "structured_browse", label: "类目搜索（推荐，无需关键词）" },
  { value: "keyword_search", label: "关键词搜索" },
];

const FIELDS: FieldDef[] = [
  { key: "category", label: "类目", type: "select", options: CATEGORY_OPTIONS,hint:"对应精选联盟主推类目；组合项分开轮流选择美妆与个护家清，合并去重。" },
  {
    key: "sourceDiscoveryMode",
    label: "发现方式",
    type: "select",
    options: DISCOVERY_OPTIONS,
    hint: "类目搜索不需要关键词；关键词搜索需填写关键词列表",
  },
  {key:"creatorType",label:"达人类型",type:"select",options:CREATOR_TYPES.map(x=>({value:x,label:x})),hint:"作品审核要求，由 AI 根据作品判断；不是精选联盟后台的内容类型。"},
  {key:"contentPresentation",label:"出镜方式",type:"select",options:PRESENTATIONS,hint:"作品审核要求；后台没有真人出镜筛选。证据不足待复核，不凭头像推断。"},
  {key:"contentType",label:"带货方式（后台）",type:"select",options:["全部达人","视频达人","直播达人","图文达人","橱窗达人"].map(value=>({value,label:value}))},
  {key:"platformContentTopic",label:"内容类型（后台）",type:"select",options:[{value:"",label:"全部"},...PLATFORM_TOPICS.map(value=>({value,label:value}))]},
  {key:"contactCollectionMode",label:"联系方式获取",type:"select",options:[{value:"all_channels",label:"一次获取全部渠道"},{value:"primary_wechat",label:"微信优先入库，其他渠道后补"}],hint:"优先获取微信；无可用微信时获取其他明文联系人。入库仍严格去重，未取渠道可通过联系方式补全流程继续获取。"},
  { key: "targetCount", label: "目标数量", type: "number", hint: "1-5000" },
  { key: "minimumFollowers", label: "粉丝下限", type: "number",hint:"软件按平台返回的粉丝数核对；0 为不限，不声称已设置后台粉丝指数。" },
  { key: "maximumFollowers", label: "粉丝上限", type: "number" },
  { key: "minimumMonthlySales", label: "月销下限", type: "number",hint:"软件按近30天销量金额区间下界核对；缺数据不放行。不是后台结算总额筛选。" },
  { key: "creatorLevels", label: "达人等级", type: "multiselect",hint:"单等级尝试后台选择；多等级按平台返回等级核对，不冒称后台已多选。",
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
  options:{disabledSubmit?:boolean}={},
): HTMLElement {
  // 默认值：新建任务或策略为空时给出可用配置，避免用户面对全空表单
  const DEFAULTS: CollectionStrategy = {
    sourceType: "brief",
    brief: "",
    viralExamples: "",
    category: "美妆个护",
    creatorLevels: [1, 2],
    minimumFollowers: 0,
    maximumFollowers: 0,
    minimumMonthlySales: 0,
    contentType: "视频达人",
    platformContentTopic:"",
    contactCollectionMode:"all_channels",
    requireContact: true,
    activeShops: ["A", "B"],
    keywords: [],
    exclusions: [],
    targetCount: 200,
    autoStart: false,
    applyMode: "next-batch",
    sourceDiscoveryMode: "structured_browse",
  };
  const s: CollectionStrategy =
    current && Object.keys(current).length ? { ...DEFAULTS, ...current } : { ...DEFAULTS };

  if(["短视频","真人口播"].includes(String(s.contentType)))s.contentType="视频达人";
  // 数组字段若为空数组，回落到默认（用户可能清空过）
  if (!Array.isArray(s.creatorLevels) || !s.creatorLevels.length) {
    s.creatorLevels = DEFAULTS.creatorLevels;
  }
  if (!Array.isArray(s.activeShops) || !s.activeShops.length) {
    s.activeShops = DEFAULTS.activeShops;
  }

  const form = h("form", { class: "strategy-form" });
  let customType:HTMLInputElement|undefined;
  const fieldNodes: Record<string, HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement> = {};

  for (const def of FIELDS) {
    const row = h("div", { class: "form-row" });
    row.append(h("label", { class: "form-label", text: def.label }));

    let input: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

    if (def.type === "select") {
      const sel = h("select", { class: "form-control", "aria-label":def.label }) as HTMLSelectElement;
      for (const opt of def.options ?? []) {
        const o = h("option", { value: opt.value, text: opt.label }) as HTMLOptionElement;
        sel.append(o);
      }
      const existing=String(s[def.key] ?? def.options?.[0]?.value ?? "");
      if(["creatorType","category","contentType"].includes(String(def.key)) && existing && !(def.options||[]).some(o=>o.value===existing))sel.append(h("option",{value:existing,text:existing}));
      sel.value = existing;
      if(def.key === "creatorType") {
        sel.append(h("option",{value:"__custom__",text:"没有符合的，自己填写"}));
        customType=h("input",{type:"text",class:"form-control","aria-label":"自定义达人类型",placeholder:"填写需要的达人类型",maxLength:"2000"}) as HTMLInputElement;
        customType.hidden=true;
        customType.addEventListener("input",()=>{s.creatorType=customType!.value;handlers.onDraftChange?.({...s});});
        sel.addEventListener("change",()=>{customType!.hidden=sel.value!=="__custom__";});
      }
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
        cb.addEventListener("change",()=>{const values=[...form.querySelectorAll<HTMLInputElement>(`input[data-multi-key="${def.key}"]:checked`)].map(x=>x.value);s[def.key]=def.key === "creatorLevels"?values.map(Number):values;handlers.onDraftChange?.({...s});});
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

    input.setAttribute("aria-label",def.label);
    const remember=()=>{s[def.key]=def.key==="creatorType"&&input.value==="__custom__"?customType?.value||"":def.type==="number"?Number(input.value)||0:def.type==="checkbox"?(input as HTMLInputElement).checked:def.type==="textarea"&&["keywords","exclusions"].includes(String(def.key))?toArray(input.value):input.value;handlers.onDraftChange?.({...s});};
    input.addEventListener("input",remember);input.addEventListener("change",remember);
    fieldNodes[String(def.key)] = input;
    row.append(input);
    if(def.key==="creatorType"&&customType)row.append(customType);
    if (def.hint) row.append(h("small", { class: "form-hint", text: def.hint }));
    form.append(row);
  }

  const error = h("div", { class: "form-error" });

  const submit = h("button", { type: "submit", class: "primary",disabled:options.disabledSubmit,title:options.disabledSubmit?"先暂停采集，再保存筛选条件":"保存筛选条件" }, ["保存策略"]);
  const cancel = h("button", {
    type: "button",
    onclick: () => handlers.onCancel(),
  }, ["取消"]);

  form.append(h("div", { class: "form-actions" }, [submit, cancel]));

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    error.textContent = "";
    if(options.disabledSubmit)return;

    const get = (k: string) => fieldNodes[k];
    const num = (k: string) => Number((get(k) as HTMLInputElement)?.value) || 0;
    const txt = (k: string) => k==="creatorType"&&(get(k) as HTMLSelectElement)?.value==="__custom__"?customType?.value||"":(get(k) as HTMLInputElement)?.value ?? "";
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
    if(!txt("creatorType").trim())return void(error.textContent="请选择或填写达人类型");
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
      creatorType: txt("creatorType"),
      contentPresentation: txt("contentPresentation"),
      creatorLevels: levels,
      minimumFollowers: minF,
      maximumFollowers: maxF,
      minimumMonthlySales: num("minimumMonthlySales"),
      contentType: txt("contentType"),
      platformContentTopic:txt("platformContentTopic"),
      contactCollectionMode:txt("contactCollectionMode"),
      requireContact: (get("requireContact") as HTMLInputElement)?.checked ?? true,
      activeShops: shops,
      keywords,
      exclusions: arr("exclusions"),
      targetCount: target,
      autoStart: false,
      applyMode: "next-batch",
      sourceDiscoveryMode: mode,
    });
  });

  form.append(error);
  return form;
}
