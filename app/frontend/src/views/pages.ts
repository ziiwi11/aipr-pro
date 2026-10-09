import {parseBrief} from "../brief-parser";
import {filterCreators} from "../creator-filters";
/**
 * 9 个页面
 *
 * 每个页面的根类名对齐原版（见 docs/ORIGINAL-UI-SPEC.md）：
 *   .auto-collect-page / .dashboard-grid / .settings-layout /
 *   .panel.list-panel / .contact-layout / .outreach-page /
 *   .delivery-center-page / .settings-page / .shop-browser-page.full
 */

import type { Bootstrap, CollectionStrategy, Creator, OutreachBatch, RoiFunnel } from "../types";
import { fmtNum, fmtTime, h } from "../store";
import { emptyHint, metric, panel, progressBar, rowItem, statusPill } from "./shell";
import { renderStrategyForm } from "./strategy-form";

export interface PageHandlers {
  onSaveShopLabels?(labels:Record<string,string>): Promise<void>;
  onValidateDelivery?(): void;
  onBackupData?(): void;
  onRestoreData?(): void;
  onExportDiagnostics?(): void;
  onSaveBrandCard?(payload:{taskName:string;brandName:string;productName:string;sellingPoints:string;brief:string;criteria:string;exclusions:string[]}): Promise<void>;
  onSaveContactCorrection?(payload:Record<string,string>):Promise<void>;
  onSaveReviewNote?(payload: {creatorId:string;note:string;disposition:string}): Promise<void>;
  onSaveJevSettings?(apiKey: string, model?: string): Promise<void>;
  onTestJevConnection?(): Promise<void>;
  onOpenJevConsole?(): void;
  onSaveStrategy(s: CollectionStrategy): void;
  onStartCollection(s?: CollectionStrategy): void;
  onStartWorker(): void;
  onPauseWorker(): void;
  onEndCollection?(): void;
  onCopyContact?(text: string): void;
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
  onRepairSavedWechat?(scope?:"current"|"history"): void;
  onVerifySavedContacts?(): void;
  onApplySavedAudit?():void;
  onAuditSavedList?(): void;
  onReviewSaved?(): void;
  onOpenSavedReview?(): void;
  onImportBatchBaseline?():void;
  onDeliverCurrent?(): void;
  onExportOriginal(): void;
  onPreviewOutreach(): void;
  onAuthorizeOutreach(previewId: string): void;
  onSyncOutreach(batchId: string): void;
  onStartOutreach(batchId: string): void;
  onImportBrief(): void;
  onImportFile(): void;
  onImportDelivery?(): void;
  onRefresh(): void;
}

/** 策略编辑态（跨重渲染保持） */
const strategyDrafts = new Map<string,CollectionStrategy>();

// ---------- 1. 自动采集 ----------

export function autoCollectPage(state: Bootstrap, handlers: PageHandlers, rerender:()=>void=()=>{}): HTMLElement {
  const t = state.task;
  const draft = strategyDrafts.get(t.id) || t.collectionStrategy;
  const strategyArea = renderStrategyForm(draft, {
    onDraftChange: s => strategyDrafts.set(t.id,s),
    onSubmit: s => { handlers.onSaveStrategy(s); },
    onCancel: () => { strategyDrafts.delete(t.id); handlers.onRefresh(); },
  }, {disabledSubmit:t.status === "running"});

  return h("div", { class: "auto-collect-page" }, [
    panel("采集控制",
      h("div", { class: "button-row" }, [statusPill(t.status)]),
      ...(t.status === "ended" ? [h("p", {class:"empty-hint",text:`${t.endedReason || "用户已结束本批"}。原目标 ${fmtNum(t.targetCount)} 人，实际保存 ${fmtNum(t.plainContacts)} 人；未把未达目标标为完成。`})] : [progressBar(Number(t.plainContacts) || 0, Number(t.targetCount) || 0)]),
      h("div", {class:"button-row"}, [
        h("button", {class:"primary",type:"button",disabled:t.status === "running",onclick:()=>handlers.onStartCollection(t.collectionStrategy),text:t.status === "ended" ? "从断点新开续跑" : "开始 / 继续采集"}),
        h("button", {type:"button",disabled:t.status !== "running",onclick:handlers.onPauseWorker,text:"暂停"}),
        h("button", {type:"button",disabled:t.status === "ended",onclick:handlers.onEndCollection,text:"结束本批（保留数据）"}),
      ]),
      h("div", { class: "metric-grid" }, [
        metric("目标", t.targetCount),
        metric("候选已采集", t.collected),
        metric("正式名单", t.plainContacts),
        metric("流程已判定", state.realtimeFlow?.available ? (state.realtimeFlow.metrics.suitable || 0) + (state.realtimeFlow.metrics.rejected || 0) : t.processed),
        metric("明文联系方式", t.plainContacts),
        metric("微信", t.wechat),
        metric("手机", t.phone),
      ]),
    ),
    panel("采集策略",
      h("div", { class: "strategy-section" }, [
        h("h3", { class: "section-title", text: "筛选达人" }),
        h("p",{text:t.status === "running"?"可先选择筛选条件；暂停采集后保存再续跑。未保存的选择不会改变当前任务。":"选择类目、达人类型和出镜方式，保存后由你开始采集。"}),
        strategyArea,
      ]),

    ),
    h("details",{},[h("summary",{text:`本批待复核（${(state.candidateCreators||[]).filter(c=>["evidence_reviewing","insufficient_evidence"].includes(String(c.flowState))||c.stage==="内容复核").length}）`}),creatorTable((state.candidateCreators||[]).filter(c=>["evidence_reviewing","insufficient_evidence"].includes(String(c.flowState))||c.stage==="内容复核"),"本批待复核","current-pending",rerender,handlers)]),
  ]);
}

// ---------- 2. 任务总览 ----------

/** ROI 漏斗可视化：宽度按占候选总数的比例 */
function roiFunnel(funnel: RoiFunnel): HTMLElement {
  const stages: [string, number, string][] = [
    ["候选达人", funnel.candidates, ""],
    ["已验证", funnel.verified, funnel.rates.verify_rate],
    ["预接触合格", funnel.qualified, funnel.rates.qualify_rate],
    ["已揭示联系方式", funnel.revealed, funnel.rates.reveal_rate],
    ["历史入选标记", funnel.delivered, funnel.rates.deliver_rate],
  ];
  const max = Math.max(1, funnel.candidates);
  const wrap = h("div", { class: "roi-funnel" });
  for (const [label, value, rate] of stages) {
    const pct = Math.round((value / max) * 100);
    const bar = h("div", { class: "funnel-bar" });
    bar.style.width = `${Math.max(2, pct)}%`;
    wrap.append(
      h("div", { class: "funnel-row" }, [
        h("span", { class: "funnel-label", text: label }),
        h("div", { class: "funnel-track" }, [bar]),
        h("span", { class: "funnel-value", text: `${fmtNum(value)}${rate ? ` · ${rate}%` : ""}` }),
      ]),
    );
  }
  return wrap;
}

function roiPanel(state: Bootstrap): HTMLElement | null {
  const roi = state.deliveryCenter?.roi;
  if (!roi || roi.error || !roi.funnel) return null;

  const f = roi.funnel;
  const c = roi.contacts;
  const children: Node[] = [
    rowItem("已导出正式名单", `${fmtNum(state.deliveryCenter?.metrics?.exportedCount)} 人（按实际交付 JSON 行数）`),
    h("details", {}, [h("summary", {text:"历史审核漏斗（诊断口径）"}), roiFunnel(f)]),
    h("div", { class: "metric-grid" }, [
      metric("本批全部候选", state.task.collected),
      metric("历史交付名单联系人覆盖率", Number(c?.contact_rate) || 0),
      metric("手机", c?.phone),
      metric("微信", c?.wechat),
    ]),
  ];

  if (roi.throughput) {
    children.push(
      h("div", { class: "empty-hint",
        text: `历史文件记录（非有效作业吞吐）：${roi.throughput.reveals_per_minute} 次/分钟 · 每次 ${roi.throughput.seconds_per_reveal ?? "-"} 秒 · 耗时 ${roi.throughput.elapsed_minutes} 分钟` }),
    );
  }
  const cost = roi.roi;
  if (cost && cost.estimated_spent) {
    children.push(
      h("div", { class: "empty-hint",
        text: `成本：估算花费 ${cost.estimated_spent} · 单联系人 ${cost.cost_per_revealed_contact ?? "-"} · 单交付 ${cost.cost_per_delivered ?? "-"}` }),
    );
  }
  const jev = roi.jev;
  if (jev && jev.enabled > 0) {
    children.push(
      h("div", { class: "empty-hint",
        text: `Jev 内容判断：覆盖 ${jev.coverage_rate}% · 匹配 ${jev.supported_rate}% · 待复核 ${jev.uncertain_rate}% · 置信度均值 ${jev.confidence.avg ?? "-"}` }),
    );
  }

  const risk = roi.risk;
  if (risk && (risk.rate_limited || risk.not_revealed || risk.failed)) {
    children.push(
      h("div", { class: "empty-hint",
        text: `风控：触发限流 ${risk.rate_limited ?? 0} · 未揭示 ${risk.not_revealed ?? 0} · 失败 ${risk.failed ?? 0}` }),
    );
  }

  children.unshift(h("div", { class: "empty-hint", text: `历史交付快照：${fmtTime(state.deliveryCenter?.createdAt)} · 仅统计已导出名单，不代表当前全部候选或实际账单。` }));
  return panel("已保存交付与审核统计", ...children);
}

export function dashboardPage(state: Bootstrap): HTMLElement {
  const t = state.task;
  const flow = state.realtimeFlow;
  const m = flow.metrics ?? {};
  return h("div", { class: "dashboard-grid" }, [
    panel("任务进度",
      ...(t.status === "ended" ? [h("p", {class:"empty-hint",text:`${t.endedReason || "用户已结束本批"}。原目标 ${fmtNum(t.targetCount)} 人，实际保存 ${fmtNum(t.plainContacts)} 人；未把未达目标标为完成。`})] : [progressBar(Number(t.plainContacts) || 0, Number(t.targetCount) || 0)]),
      h("div", { class: "metric-grid" }, [
        metric("目标", t.targetCount),
        metric("候选已采集", t.collected),
        metric("正式名单", t.plainContacts),
        metric("流程已判定", state.realtimeFlow?.available ? (state.realtimeFlow.metrics.suitable || 0) + (state.realtimeFlow.metrics.rejected || 0) : t.processed),
      ]),
    ),
    panel(t.status === "running" ? "实时流程" : "最近保存的流程状态",
      h("div", { class: "metric-grid" }, [
        metric("候选", m.candidates),
        metric("合适", m.suitable),
        metric(t.status === "running" ? "取联系方式中" : "等待获取联系方式", m.contactRevealing),
        metric("含明文候选", m.plaintext, "valid"),
        metric("本流程入库", m.listed, "formal"),
      ]),
      h("div", { class: "empty-hint", text: `更新时间：${fmtTime(flow.updatedAt)}` }),
    ),
    panel("作业时间与净新增",
      rowItem("观测范围",state.runtimeMetrics?.scope || "尚无完整作业计时记录"),
      ...(state.runtimeMetrics?.available ? [
        rowItem("作业存在时长",`${((state.runtimeMetrics.elapsedMs||0)/60000).toFixed(1)} 分钟`),
        rowItem("有进展有效时段",`${((state.runtimeMetrics.effectiveMs||0)/60000).toFixed(1)} 分钟`),
        rowItem("明确冷却等待",`${((state.runtimeMetrics.cooldownMs||0)/60000).toFixed(1)} 分钟`),
        rowItem("未证实活动时段",`${((state.runtimeMetrics.unknownMs||0)/60000).toFixed(1)} 分钟`),
        rowItem("最近一次作业净新增",`${state.runtimeMetrics.newCreators||0} 人`),
        rowItem("中断次数",String(state.runtimeMetrics.interruptions||0)),
        rowItem("每小时净新增",state.runtimeMetrics.netPerHour==null?"无法确认（有效时间证据不足）":`${state.runtimeMetrics.netPerHour.toFixed(1)} 人/小时`),
      ] : [rowItem("有效作业 / 冷却 / 净新增速度","未知；下一次显式作业开始记时，本轮不自动启动")]),
      rowItem("本批正式 / 全部候选",`${t.plainContacts||0} / ${t.collected||0} 人；${t.collected?((Number(t.plainContacts)||0)*100/Number(t.collected)).toFixed(1):"0"}%`),
    ),
    panel("联系方式",
      h("div", { class: "metric-grid" }, [
        metric("明文总数", t.plainContacts),
        metric("微信", t.wechat),
        metric("手机", t.phone),
      ]),
    ),
    ...(roiPanel(state) ? [roiPanel(state) as HTMLElement] : []),
    panel("运行历史",
      ...((state.runHistory ?? []).slice(0, 8).map((r) =>
        rowItem(fmtTime(String(r.recordedAt ?? r.startedAt ?? "")), String(r.message || r.artifact || historyStatus(String(r.status || r.type || "")))),
      )),
      ...((state.runHistory ?? []).length ? [] : [emptyHint("暂无运行记录")]),
    ),
  ]);
}

// ---------- 3. 品牌手卡 ----------

export function brandCardPage(state: Bootstrap, handlers: PageHandlers): HTMLElement {
  const strategy=state.task.collectionStrategy || {};
  const textInput=(label:string,value:string,multiline=false)=>{const input=h(multiline?"textarea":"input", {class:"form-control","aria-label":label,maxLength:multiline?"20000":"2000",style:"width:100%;margin:6px 0"}) as HTMLInputElement|HTMLTextAreaElement;input.value=value;return input;};
  const name=textInput("任务名称",state.task.name),brand=textInput("品牌",String(strategy.brandName||"")),product=textInput("产品",String(strategy.productName||"")),selling=textInput("核心卖点",String(strategy.sellingPoints||"")),brief=textInput("任务简报",String(strategy.brief||""),true);
  const criteria=textInput("适配条件",String(strategy.criteria||""),true),exclusions=textInput("排除条件",(strategy.exclusions||[]).join("\n"),true);
  criteria.maxLength=2000;
  const revisions=state.task.brandRevisions||[];
  const template=h("select",{class:"form-control","aria-label":"品牌手卡模板"},[h("option",{value:"general",text:"通用好物（宽松）"}),h("option",{value:"lip",text:"美妆唇护理（宽松）"})]) as HTMLSelectElement;
  const applyTemplate=h("button",{type:"button",text:"填入适配模板",onclick:()=>{criteria.closest<HTMLElement>("[data-preserve-input]")!.dataset.editingDraft="true";criteria.value=template.value==="lip"?"作品中可自然展示美妆、口红试色或唇部护理，允许生活方式及跨品类好物分享。":"作品中可自然展示产品使用场景，允许生活方式及跨品类好物分享。";}});
  (brief as HTMLTextAreaElement).rows=8;
  const parse=h("button",{type:"button",text:"解析手卡并核对",onclick:()=>{const result=parseBrief(brief.value);brand.value=String(result.fields.brandName||brand.value);product.value=String(result.fields.productName||product.value);selling.value=String(result.fields.sellingPoints||selling.value);criteria.value=String(result.fields.criteria||criteria.value);exclusions.value=result.fields.exclusions?.join("\n")||exclusions.value;brief.closest<HTMLElement>("[data-preserve-input]")!.dataset.editingDraft="true";error.textContent="明确字段已整理，未识别内容保留在简报中。请核对后保存；类目与达人类型在找达人条件中选择。";}});
  const error=h("p",{role:"alert"});
  const save=h("button",{type:"button",class:"primary",text:"保存品牌手卡",onclick:async()=>{save.disabled=true;try{if(!name.value.trim())throw new Error("请填写任务名称");await handlers.onSaveBrandCard?.({taskName:name.value.trim(),brandName:brand.value.trim(),productName:product.value.trim(),sellingPoints:selling.value.trim(),brief:brief.value,criteria:criteria.value.trim(),exclusions:exclusions.value.split(/\n/).map(x=>x.trim()).filter(Boolean).slice(0,30)});}catch(e){error.textContent=e instanceof Error?e.message:"保存失败";}finally{save.disabled=false;}}}) as HTMLButtonElement;
  return h("div",{class:"settings-layout"},[
    panel("品牌手卡",h("div",{class:"brand-card-form","data-preserve-input":"true"},[h("label",{},["任务名称",name]),h("label",{},["品牌",brand]),h("label",{},["产品",product]),h("label",{},["核心卖点",selling]),h("label",{},["任务简报",brief]),h("label",{},["适配条件",criteria]),h("label",{},["排除条件（每行一项）",exclusions]),h("div",{class:"button-row"},[template,applyTemplate,parse]),save,error]),
      h("p",{class:"empty-hint",text:"保存后用于后续分析；历史判断与交付保留原版本，不会自动重算或付费。"}),h("button",{type:"button",onclick:handlers.onImportBrief,text:"从文件导入简报"})),
    panel("配置版本与生效范围",rowItem("当前版本",revisions.length?`v${revisions.at(-1)?.version} · ${fmtTime(revisions.at(-1)?.createdAt)}`:"历史配置尚未记录版本；首次保存后建立记录"),
      h("p",{class:"empty-hint",text:"模板只填入适配条件，不自动保存、采集或重算。保存规则在下一次显式分析生效，原交付与人工复核保留。"}),
      h("details",{},[h("summary",{text:`已保存 ${revisions.length} 个版本`}),...revisions.slice().reverse().map(r=>h("section",{},[h("h3",{text:`v${r.version} · ${fmtTime(r.createdAt)}`}),h("pre",{class:"brief-text",text:JSON.stringify(r.config,null,2)})]))])),
    panel("规则配置",h("div",{class:"button-row"},[h("button",{type:"button",onclick:handlers.onExportRules,text:"导出规则"}),h("button",{type:"button",onclick:handlers.onImportRules,text:"导入规则"})]),h("details",{},[h("summary",{text:"高级任务信息"}),rowItem("任务标识",state.task.id),rowItem("保存位置",state.task.outputDir)])),
  ]);
}

// ---------- 4. 达人优选（分页表格） ----------

const PAGE_SIZE = 50;
const tableState = new Map<string, { page: number; query: string;channel:string;evidence:string;sort:string }>();

function getTableState(key: string) {
  let s = tableState.get(key);
  if (!s) {
    s = { page: 1, query: "",channel:"all",evidence:"all",sort:"default" };
    tableState.set(key, s);
  }
  return s;
}

function creatorSalesRange(c: Creator): string {
  const amount = (n: number) => `¥${n.toLocaleString("zh-CN")}`;
  if (c.monthlySalesLow !== undefined && c.monthlySalesHigh !== undefined) return `${amount(c.monthlySalesLow)}–${amount(c.monthlySalesHigh)}（平台区间）`;
  const lower = c.monthlySalesLow ?? c.monthlySalesLowerBound;
  if (lower !== undefined) return `≥${amount(lower)}（平台下界）`;
  return c.monthlySalesDisplay || "未获取";
}

function creatorDetails(c: Creator, handlers?: PageHandlers): void {
  const dialog = document.createElement("dialog");
  dialog.className = "creator-detail";
  dialog.setAttribute("aria-label", `${c.nickname || "达人"}的复核依据`);
  const show = (value: unknown): string => typeof value === "object" && value !== null ? JSON.stringify(value, null, 2) : value === null || value === undefined || value === "" ? "未记录" : String(value);
  const jev = c.jevAnalysis as Record<string, unknown> | undefined;
  const fields: [string, unknown][] = [
    ["抖音号", c.douyinId], ["粉丝数", Number(c.fans) > 0 ? fmtNum(c.fans) : "未获取"],
    ["达人等级", c.talentLevel], ["主推类目", c.category], ["所在城市", c.city],
    ["主要带货方式", c.mainSaleType], ["近30天视频数", c.videoCount30d ?? "未获取"],
    ["近30天销售区间", creatorSalesRange(c)], ["采集店铺", c.shop],
    ["抖音主页", c.douyinHomepage], ["精选联盟主页", c.buyinHomepage],
    ["达人简介与平台资料", c.profileText], ["作品文字与近期内容", c.contentText],
    ["微信", c.wechat], ["手机号", c.phone], ["邮箱", c.email],
    ["推荐结论", c.decision], ["推荐理由", c.reason || c.evidence],
    ["处理阶段", c.flowState || c.stage], ["待处理原因", c.flowReason],
    ["作品证据", c.contentEvidence], ["作品证据来源", c.contentEvidenceSource], ["作品复核时间", c.evidenceReviewedAt], ["平台入库状态", c.libraryStatus], ["联系人证据", c.contactEvidence], ["Jev 模型", jev?.model],
    ["Jev 判断", jev?.route], ["Jev 判断理由", jev?.reason], ["Jev 置信度", jev?.confidence],
    ["证据截图", c.evidenceScreenshot || "未记录截图，需要补充证据"],
    ["联系方式来源", c.contactSource], ["原始获取时间", c.contactAcquiredAt], ["人工修订时间", c.contactCorrectedAt],
    ["可达性", "尚未验证；获取联系方式不代表可以联系成功"],
  ];
  const close = h("button", {type:"button", text:"关闭", onclick: () => {dialog.close();dialog.remove();}});
  dialog.append(h("h2", {text: c.nickname || "达人复核依据"}), close);
  for (const [label, value] of fields) dialog.append(h("section", {}, [h("h3", {text:label}), h("pre", {class:"brief-text",text:show(value)})]));
  dialog.addEventListener("close", () => dialog.remove());
  const history = (c.reviewRecords || []) as {note:string;disposition:string;recordedAt:string;revision:number}[];
  for (const record of history) dialog.append(h("p",{text:`复核记录 #${record.revision} · ${fmtTime(record.recordedAt)} · ${record.note}`}));
  if (handlers?.onSaveReviewNote && c.contactEditable !== false) {
    const note=h("textarea",{"aria-label":"复核说明",maxLength:"2000",placeholder:"记录已核对的证据、缺失项或排除理由"}) as HTMLTextAreaElement;
    const disposition=h("select",{"aria-label":"处理方式"},[["needs_evidence","待补证据"],["reviewed_note","已核对，仅记录"],["exclude_requested","建议排除，待审核执行"]].map(([value,text])=>h("option",{value,text}))) as HTMLSelectElement;
    const error=h("p",{role:"alert"});
    const save=h("button",{type:"button",text:"保存复核记录",onclick:async()=>{
      save.disabled=true;
      try{await handlers.onSaveReviewNote!({creatorId:String(c.canonicalTaskCreatorId||c.id||c.identity||""),note:note.value,disposition:disposition.value});dialog.close();dialog.remove();}
      catch(e){error.textContent=e instanceof Error?e.message.replace(/^Error invoking remote method '[^']+': Error: /, ""):"复核记录保存失败";}
      finally{save.disabled=false;}
    }}) as HTMLButtonElement;
    dialog.append(h("h3",{text:"人工处理记录"}),h("p",{text:"记录不等于准入放行。待补证据和排除建议需审核处理，不能用人工备注跳过作品核验。"}),disposition,note,save,error);
  }
  if(handlers?.onSaveContactCorrection && c.contactEditable !== false){
    const input=(label:string,value:string)=>{const element=h("input",{"aria-label":label,style:"width:100%;margin:6px 0"}) as HTMLInputElement;element.value=value;return element;};
    const wx=input("修订微信",c.wechat||""),phone=input("修订手机号",c.phone||""),email=input("修订邮箱",String(c.email||"")),source=input("修订来源",String(c.contactSource||"")),reason=input("修订理由","");
    const error=h("p",{role:"alert"});const save=h("button",{type:"button",text:"保存联系人修订",onclick:async()=>{save.disabled=true;try{await handlers.onSaveContactCorrection!({creatorId:String(c.canonicalTaskCreatorId||c.id||c.identity||""),wechat:wx.value,phone:phone.value,email:email.value,source:source.value,reason:reason.value});dialog.close();}catch(e){error.textContent=e instanceof Error?e.message.replace(/^Error invoking remote method '[^']+': Error: /, ""):"联系人修订失败";}finally{save.disabled=false;}}}) as HTMLButtonElement;
    const content=h("div",{"data-preserve-input":"true"},[h("p",{text:"填写真实证据来源和理由。保存后用于当前查看和后续交付，历史交付包保留；不验证可达性，不改变准入或发送授权。不同身份的重复联系人会拒绝保存，数字微信不按外观改成手机号。"}),...[["微信",wx],["手机号",phone],["邮箱",email],["来源",source],["修订理由",reason]].map(([label,element])=>h("label",{},[String(label),element as HTMLElement])),save,error]);
    const records=(c.contactCorrectionRecords||[]) as {revision:number;source:string;reason:string;recordedAt:string;before:Record<string,string>;after:Record<string,string>}[];
    records.forEach(r=>content.append(h("pre",{class:"brief-text",text:`修订 #${r.revision} · ${fmtTime(r.recordedAt)} · ${r.source} · ${r.reason}\n修改前：${JSON.stringify(r.before)}\n修改后：${JSON.stringify(r.after)}`})));
    dialog.append(h("details",{},[h("summary",{text:"人工修订联系方式与历史"}),content]));
  }
  const screenshots = String(c.evidenceScreenshot || "").split(/\n| \| /).filter(Boolean);
  for (const path of screenshots) dialog.append(h("button", {type:"button",text:"打开证据截图",onclick:()=>handlers?.onOpenPath(path),disabled:!handlers}));
  if (c.wechat || c.phone || c.email) dialog.append(h("button", {type:"button",text:"复制联系方式",onclick:()=>handlers?.onCopyContact?.([c.wechat && `微信:${c.wechat}`,c.phone && `手机:${c.phone}`,c.email && `邮箱:${c.email}`].filter(Boolean).join("；")),disabled:!handlers?.onCopyContact}));
  document.body.append(dialog); dialog.showModal(); close.focus();
}

export function creatorTable(
  rows: Creator[],
  title: string,
  key: string,
  rerender: () => void,
  handlers?: PageHandlers,
): HTMLElement {
  const st = getTableState(key);
  const filtered=filterCreators(rows,st.query,st.channel,st.evidence,st.sort);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const page = Math.min(Math.max(1, st.page), totalPages);
  st.page = page;
  const slice = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const table = h("table", { class: "creator-table" });
  table.append(h("tr", {}, [
    h("th", { text: "复核依据" }), h("th", { text: "昵称" }), h("th", { text: "抖音号" }), h("th", { text: "粉丝" }),
    h("th", { text: "等级" }), h("th", { text: "类目" }),
    h("th", { text: "销售区间" }), h("th", { text: "近30天视频" }), h("th", { text: "带货方式" }), h("th", { text: "城市" }),
    h("th", { text: "微信" }), h("th", { text: "手机" }), h("th", { text: "邮箱" }),
  ]));
  for (const c of slice) {
    table.append(h("tr", {}, [
      h("td", {}, [h("button", {type:"button", text:"查看详情", onclick: () => creatorDetails(c, handlers)})]),
      h("td", { text: c.nickname || "-" }),
      h("td", { text: c.douyinId || "-" }),
      h("td", { text: Number(c.fans) > 0 ? fmtNum(c.fans) : "未知" }),
      h("td", { text: c.talentLevel || "-" }),
      h("td", { text: (c.category || "-").slice(0, 20) }),
      h("td", { text: creatorSalesRange(c) }),
      h("td", { text: c.videoCount30d ?? "未获取" }),
      h("td", { text: c.mainSaleType || "未获取" }),
      h("td", { text: c.city || "未获取" }),
      h("td", { text: c.wechat || "-" }),
      h("td", { text: c.phone || "-" }),
      h("td", { text: String(c.email || "-") }),
    ]));
  }

  const search = h("input", {
    class: "table-search", type: "search", "aria-label": "搜索达人", "data-table-key": key,
    placeholder: "搜索昵称 / 抖音号 / 类目 / 联系方式", value: st.query,
  });
  search.addEventListener("input", () => {
    st.query = (search as HTMLInputElement).value;
    st.page = 1;
    const cursor = (search as HTMLInputElement).selectionStart;
    rerender();
    const restored = Array.from(document.querySelectorAll<HTMLInputElement>(".table-search")).find(input => input.dataset.tableKey === key);
    restored?.focus();
    if (restored && cursor !== null) restored.setSelectionRange(cursor, cursor);
  });

  const filter=(label:string,field:"channel"|"evidence"|"sort",options:[string,string][])=>{
    const select=h("select",{"aria-label":label},options.map(([value,text])=>h("option",{value,text}))) as HTMLSelectElement;
    select.value=st[field];select.onchange=()=>{st[field]=select.value;st.page=1;rerender();};return h("label",{},[label,select]);
  };
  const toolbar = h("div", { class: "table-toolbar" }, [
    h("label",{},["搜索达人",search]),
    filter("渠道","channel",[["all","全部联系方式"],["wechat","含微信"],["phone","含手机"],["email","含邮箱"]]),
    filter("截图","evidence",[["all","全部截图状态"],["has","有截图记录"],["missing","缺少截图记录"]]),
    filter("排序","sort",[["default","原始顺序"],["fans","粉丝从高到低"],["score","评分从高到低"],["name","昵称顺序"]]),
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

let libraryTaskFilter = "all";


export function creatorsPage(state: Bootstrap, rerender: () => void, handlers?: PageHandlers): HTMLElement {
  const library = state.creatorLibrary;
  const batches=(library?.batches||[]).filter(b=>b.id!==state.task.id && (!b.status || ["completed","ended"].includes(b.status)));
  const historicalIds=new Set(batches.map(b=>b.id));
  const allRows=(library?.creators||[]).filter(row=>((row.libraryTaskIds as string[])||[]).some(id=>historicalIds.has(id)));
  if(libraryTaskFilter!=="all"&&!historicalIds.has(libraryTaskFilter))libraryTaskFilter="all";
  const selector=h("select",{"aria-label":"往期达人批次"},[h("option",{value:"all",text:"全部往期批次"}),...batches.map(b=>h("option",{value:b.id,text:`${b.name}（${b.count}人）`}))]) as HTMLSelectElement;
  selector.value=libraryTaskFilter;selector.addEventListener("change",()=>{libraryTaskFilter=selector.value;rerender();});
  const rows=libraryTaskFilter==="all"?allRows:allRows.filter(row=>((row.libraryTaskIds as string[])||[]).includes(libraryTaskFilter));
  const enriched=rows.map(c=>({...c,contactEditable:((c.libraryTaskIds as string[])||[]).some(id=>id===state.task.id||id===`${state.task.id}-batch-baseline`),contactCorrectionRecords:(state.contactCorrections||[]).filter(r=>r.creatorId===String(c.contactCorrectionCreatorId||c.canonicalTaskCreatorId||c.id||c.identity||"")),reviewRecords:(state.reviewRecords||[]).filter(r=>r.creatorId===String(c.contactCorrectionCreatorId||c.canonicalTaskCreatorId||c.id||c.identity||""))}));
  const historicalDeliveryCards=batches.filter(b=>libraryTaskFilter==="all"||b.id===libraryTaskFilter).map(b=>{
    const task=state.tasks.find(t=>t.id===b.id);
    const savedDelivery=task?.deliveryPath || b.deliveryPath;
    return h("div",{class:"row-item"},[
      h("span",{text:`${b.name} · ${b.count}人`}),
      ...(b.baselinePath ? [h("button",{type:"button",text:"打开往期基线名单",onclick:()=>handlers?.onOpenPath(b.baselinePath!)})] : []),
      h("button",{type:"button",text:"查看本批联系方式",onclick:()=>{libraryTaskFilter=b.id;rerender();}}),
      h("button",{type:"button",text:b.baselinePath?"打开原累计交付快照":"打开历史交付包",disabled:!savedDelivery,onclick:()=>{if(savedDelivery)handlers?.onOpenPath(savedDelivery);}}),
    ]);
  });
  return h("div",{class:"panel list-panel"},[panel("往期达人库",selector,h("p",{text:`这里只查看已完成或已结束批次的达人与来源。当前任务 ${state.task.name} 的 ${state.creators?.length||0} 人，请到联系与交付查看。全系统累计 ${library?.creators.length||0} 人。`})),creatorTable(enriched,"往期达人",`history-${state.task.id}-${libraryTaskFilter}`,rerender,handlers),...(state.historicalWechatRepairCount && (libraryTaskFilter==="all" || libraryTaskFilter===`${state.task.id}-batch-baseline`) ? [panel("当前任务往期微信完整性",h("p",{text:`当前任务往期基线中有 ${state.historicalWechatRepairCount} 条微信被截断，可按同一达人原始平台标签恢复完整值。保留旧名单与旧交付包，不改变本批20人范围，不验证可达性。其他任务请先切换到对应品牌任务修订。`}),h("button",{type:"button",disabled:state.task.status==="running",onclick:()=>handlers?.onRepairSavedWechat?.("history"),text:`恢复往期完整微信号（${state.historicalWechatRepairCount}条）`}))] : []),panel("历史联系方式与交付",...historicalDeliveryCards)]);
}

// ---------- 5. 联系方式 ----------

export function contactsPage(state: Bootstrap, rerender: () => void, handlers?: PageHandlers): HTMLElement {
  const withContact = (state.creators ?? []).filter((c) => c.plainContact || c.wechat || c.phone || c.email).map(c=>({...c,contactCorrectionRecords:(state.contactCorrections||[]).filter(r=>r.creatorId===String(c.contactCorrectionCreatorId||c.canonicalTaskCreatorId||c.id||c.identity||""))}));
  return h("div", { class: "contact-layout" }, [
    panel("本批联系方式统计",
      h("div", { class: "metric-grid" }, [
        metric("正式名单", (state.creators ?? []).length),
        metric("有联系方式", withContact.length),
        metric("微信", (state.creators ?? []).filter((c) => c.wechat).length),
        metric("手机", (state.creators ?? []).filter((c) => c.phone).length),
      ]),
    ),
    h("p", {class:"empty-hint",text:"同一达人可同时有微信和手机，人数不相加；联系可达性尚未验证。来源与获取时间见达人详情。"}),
    creatorTable(withContact.map(c=>({...c,contactCorrectionRecords:(state.contactCorrections||[]).filter(r=>r.creatorId===String(c.contactCorrectionCreatorId||c.canonicalTaskCreatorId||c.id||c.identity||"")),reviewRecords:(state.reviewRecords||[]).filter(r=>r.creatorId===String(c.contactCorrectionCreatorId||c.canonicalTaskCreatorId||c.id||c.identity||""))})), "联系方式明细", "contacts", rerender, handlers),
  ]);
}

// ---------- 6. AI 建联 ----------

export function outreachPage(state: Bootstrap, handlers: PageHandlers, rerender:()=>void=()=>{}): HTMLElement {
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
  return h("div", { class: "outreach-page contact-outreach-page" }, [
    h("h2",{text:"联系与交付"}),
    h("button",{type:"button",text:"设置本轮开始前的往期基线",disabled:state.task.status === "running",onclick:handlers.onImportBatchBaseline}),
    ...(state.currentBatch ? [h("p",{text:`本轮新增 ${state.currentBatch.newCount} 人；已将起点前 ${state.currentBatch.baselineCount} 人归入达人优选。累计任务人数不等于本轮人数。`})] : []),
    h("p",{text:`仅当前批次：${state.task.name}。核对联系方式、AI 建联预览和名单交付在同一页完成；往期名单在达人优选。查看和导出不会触发发送。`}),
    h("div",{class:"button-row"},[h("button",{type:"button",text:"核对联系方式",onclick:()=>document.querySelector(".contact-layout")?.scrollIntoView({block:"start"})}),h("button",{type:"button",text:"AI 建联预览",onclick:()=>document.querySelector(".outreach-banner")?.scrollIntoView({block:"start"})}),h("button",{type:"button",text:"交付中心",onclick:()=>document.querySelector(".delivery-center-page")?.scrollIntoView({block:"start"})})]),
    h("h3",{text:"1. 核对联系方式"}),
    contactsPage(state,rerender,handlers),
    h("header", { class: "outreach-banner" }, [
      h("h3",{text:"2. AI 建联预览"}),
      h("p", { text: "请在下方工作台选择达人并预览；只有单独确认授权后才能继续。" }),
    ]),
    panel("建联批次", list),
    h("h3",{text:"3. 交付中心"}),
    deliveryPage(state,handlers),
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
      h("button", {type:"button", disabled:state.task.status === "running", onclick:handlers.onAuditSavedList, text:"重新核对已保存名单"}),
      h("button",{type:"button",disabled:state.task.status === "running",onclick:handlers.onApplySavedAudit,text:"查看并应用复核差异"}),
      h("p",{text:"按当前内容规则与严格联系人去重重新审核已保存证据；先备份旧名单，不采集、不调用付费模型。判断过期或证据不足仍需复核。"}),
      h("div", { class: "empty-hint", text: `已保存正式名单 ${fmtNum(state.task.plainContacts)} 人；当前交付文件 ${fmtNum(dc?.metrics?.candidateCount)} 人。生成当前交付包只复核已保存数据，不新增采集、不发送消息。` }),
      h("button", { type: "button", "data-delivery-generation":"true", onclick: handlers.onDeliverCurrent, disabled: state.task.status === "running" || !state.task.plainContacts }, ["生成当前名单交付包"]),
      h("div", { class: "button-row" }, [
        h("button", { type: "button", onclick: handlers.onPreviewHandoff }, ["预览机器人队列"]),
        h("button", { type: "button", onclick: handlers.onImportDelivery, disabled: state.task.status === "running", title: "导入已保存交付JSON到当前任务，不重新采集、分析或发送" }, ["导入历史交付 JSON"]),
        h("button", { type: "button", onclick: handlers.onExportOriginal, disabled: !state.task.originalWorkbookPath, title: state.task.originalWorkbookPath ? "按导入表格格式导出" : "请先导入原始表格" }, ["导出原始表格"]),
        ...(state.task.originalExport?.path && state.task.originalExport.deliveryPath===state.task.deliveryPath && state.task.originalExport.sourceWorkbookPath===state.task.originalWorkbookPath ? [h("button",{type:"button",onclick:()=>handlers.onOpenPath(state.task.originalExport!.path),text:"打开最近原格式导出"})] : []),
      ]),
    ),
    panel("作品证据补核",
      h("p",{text:"仅补核已保存名单中最多 20 条缺失截图；不新增达人、不调用模型、不发送。联系人仅核对平台当前明文展示；真实可达性仍需验证。补核是新时点证据，需人工复核，不替换历史判断。"}),
      h("button",{type:"button",disabled:state.task.status === "running",onclick:handlers.onReviewSaved,text:"补核缺失作品截图（最多20条）"}),
      h("button",{type:"button",onclick:handlers.onOpenSavedReview,text:"打开补核报告"}),
      ...(state.savedEvidenceReview ? [
        rowItem("补核状态", state.savedEvidenceReview.status === "running" ? "软件补核中" : state.savedEvidenceReview.status === "finished" ? "本轮补核已结束" : "仍需复核或登录"),
        rowItem("截图补齐", `${state.savedEvidenceReview.records.filter(r=>r.screenshots.length).length} 条；补核时间 ${fmtTime(state.savedEvidenceReview.updated_at)}`),
        rowItem("联系人可达性", "未验证 · 未发送任何消息"),
        h("p",{text:"平台明文复核会使用店铺的查看联系方式次数；仅核验本次20位达人，遇限流或额度限制保留断点。不会替换历史联系人。"}),
        h("button",{type:"button",disabled:state.task.status === "running",onclick:handlers.onVerifySavedContacts,text:"核验这20条平台明文联系方式"}),
        rowItem("平台联系人复核", state.savedEvidenceReview.contact_review_status === "running" ? "核验中" : state.savedEvidenceReview.contact_review_status === "finished" ? "本轮核验结束（查看逐条结果）" : state.savedEvidenceReview.contact_review_status ? "等待冷却或登录" : "尚未开展明文核验"),
        h("details",{},[h("summary",{text:"查看新时点截图与平台联系人核验（仍需人工复核）"}),
          ...state.savedEvidenceReview.records.map((record,index)=>h("div",{class:"row-item"},[
            h("span",{text:`补核 ${index+1}：${record.screenshots.length} 张截图；平台联系人 ${Object.values(record.contact_verification.channels).includes("platform_mismatch") ? "存在差异，需核实" : Object.values(record.contact_verification.channels).includes("platform_match") ? "有明文匹配" : "遮蔽或未展示，尚未核实"}`}),
            ...record.screenshots.map((shot,i)=>h("button",{type:"button",text:`打开截图 ${i+1}`,onclick:()=>handlers.onOpenPath(shot)}))]))])
      ] : [])),
    ...(state.savedWechatRepairCount ? [panel("微信号完整性修复",
      h("p",{text:`发现 ${state.savedWechatRepairCount} 条有原始平台微信标签证据的号码被软件截断。可恢复完整字母和数字，不修改旧交付包，不覆盖人工修订。恢复后需重新生成并校验交付包；可达性仍未验证。`}),
      h("button",{type:"button",onclick:()=>handlers.onRepairSavedWechat?.("current"),text:`按原始展示恢复完整微信号（${state.savedWechatRepairCount}条）`}))] : []),
    panel("交付文件一致性",
      h("button",{type:"button","data-delivery-validation":"true",disabled:!dc?.available || state.maintenance?.busy,onclick:handlers.onValidateDelivery,text:state.maintenance?.busy ? "正在校验文件，请稍候…" : "校验 JSON / Excel / 待发送队列"}),
      rowItem("上次校验", dc?.validation ? `${fmtTime(dc.validation.checkedAt)} · ${dc.validation.stale ? "文件发生变化，需重新校验" : dc.validation.ok ? "通过" : "未通过"}` : "尚未校验"),
      ...(dc?.validation ? [rowItem("校验人数",`名单 ${dc.validation.rowCount ?? "未知"} / 队列 ${dc.validation.queueCount ?? "未知"}`),
        ...dc.validation.errors.map(error=>h("p",{role:"alert",text:error})),
        h("details",{},[h("summary",{text:"文件校验指纹"}),...dc.validation.files.map(file=>rowItem(file.key,file.sha256))])] : []),
      h("p",{class:"empty-hint",text:"校验只读文件，不调用模型，不采集或发送。核对身份、联系方式及发送保护，不代表达人适配准确率或联系人可达性；文件变化后需重验。"})),
    ...(state.contactRevisionPending ? [panel("联系人已修订",h("p",{text:"当前联系人已有人工作出修订，旧交付包保留旧联系人。请重新生成并校验交付包后使用；旧包校验通过不代表与修订后的名单一致。"}))] : []),
    panel("交付包信息",
      rowItem("生成时间", fmtTime(dc?.createdAt)),
      rowItem("导出人数", `${fmtNum(dc?.metrics?.exportedCount)} 人（当前交付 JSON）`),
      rowItem("模板版本", dc?.exportTemplate ? `${String((dc.exportTemplate as Record<string,unknown>).name)} · v${String((dc.exportTemplate as Record<string,unknown>).version)}` : "历史模板"),
      rowItem("发送状态", "导出和生成待发送队列不代表实际发送")),
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
  const shopLabels = ["A", "B"].map(shop => h("input",{class:"form-control",type:"text",value:shops[shop]?.label || `抖店 ${shop}`,maxlength:60,"aria-label":`店铺 ${shop} 备注`}) as HTMLInputElement);
  return h("div", { class: "settings-page" }, [
    panel("软件与数据管理",
      rowItem("当前版本", state.appVersion || "未知"),
      h("p",{"data-maintenance-status":"true",text:`数据维护：${state.maintenance?.message || "尚未开始"}${state.maintenance?.busy ? ` · 已处理 ${fmtNum(state.maintenance.files)} 个文件` : ""}`}),
      h("div",{class:"button-row"},[
        h("button",{type:"button",disabled:state.maintenance?.busy || state.task.status === "running","data-maintenance-action":"true",onclick:handlers.onBackupData,text:"备份任务与名单"}),
        h("button",{type:"button",disabled:state.maintenance?.busy || state.task.status === "running","data-maintenance-action":"true",onclick:handlers.onRestoreData,text:"校验并恢复备份"}),
        h("button",{type:"button",onclick:handlers.onExportDiagnostics,text:"导出去敏诊断报告"}),
      ]),
      h("p",{class:"empty-hint",text:"备份包含任务、名单、证据、交付与复核记录。恢复到新目录，保留原数据；不含登录会话、API Key 和发送授权，任务不会自动续跑。"})),
    panel("平台自检",
      rowItem("平台", p?.platform === "darwin" ? "macOS" : p?.platform === "win32" ? "Windows" : "其他系统"),
      rowItem("就绪状态", p?.ready ? "就绪" : "未就绪"),
      h("details",{},[h("summary",{text:"高级环境诊断"}),checks]),
    ),
    panel("内置浏览器",
      h("div", { class: "button-row" }, [
        h("button", { class: "primary", type: "button", onclick: handlers.onLaunchBrowsers }, ["启动浏览器"]),
        h("button", { type: "button", onclick: handlers.onProbeLogin }, ["检测登录"]),
        h("button", { type: "button", onclick: handlers.onHideShops }, ["隐藏视图"]),
      ]),
      ...["A","B"].map((shop,i)=>h("div",{},[rowItem(`店铺 ${shop} 备注`,""),shopLabels[i],rowItem("登录状态",shops[shop]?.status === "connected" ? "上次检测已登录" : "待检测或未登录"),rowItem("最近检测",shops[shop]?.checkedAt ? fmtTime(shops[shop]?.checkedAt) : "尚无检测时间")])),
      h("button",{type:"button",onclick:()=>handlers.onSaveShopLabels?.({A:shopLabels[0].value.trim(),B:shopLabels[1].value.trim()}),text:"保存店铺备注"}),
      h("p",{class:"empty-hint",text:"备注用于区分本机窗口，不代表已核验平台店铺实名。"}),
    ),
    panel("数据导入",
      h("div", { class: "button-row" }, [
        h("button", { type: "button", onclick: handlers.onImportBrief }, ["导入简报"]),
        h("button", { type: "button", onclick: handlers.onImportFile }, ["导入原始 Excel（XLSX）"]),
        h("button", { type: "button", onclick: handlers.onImportRules }, ["导入规则"]),
      ]),
    ),
  ]);
}

export function modelsPage(state: Bootstrap, handlers: PageHandlers): HTMLElement {
  const jevKey = h("input", { type: "password", autocomplete: "off", "aria-label": "Jev API Key", placeholder: state.jevStatus?.configured ? "留空保留现有 Key" : "输入 Jev API Key" }) as HTMLInputElement;
  const jevModel = h("input", { "aria-label": "Jev 模型", list: "jev-model-options", value: state.jevStatus?.model || "jev-latest" }) as HTMLInputElement;
  const modelOptions = h("datalist", { id: "jev-model-options" }, ["jev-latest", "jev-preview", "jev-1.13.0"].map(value => h("option", { value })));
  const jevSave = h("button", { type: "button", onclick: async () => {
    jevSave.disabled = true;
    try { await handlers.onSaveJevSettings?.(jevKey.value, jevModel.value); jevKey.value = ""; }
    finally { jevSave.disabled = false; }
  }, text: "保存 Jev 配置" }) as HTMLButtonElement;
  const testButton=h("button",{type:"button",text:"测试模型（单次云端调用）",disabled:!state.jevStatus?.configured,onclick:async()=>{testButton.disabled=true;testButton.textContent="正在测试…";try{await handlers.onTestJevConnection?.();}finally{testButton.disabled=false;testButton.textContent="测试模型（单次云端调用）";}}}) as HTMLButtonElement;
  const status = state.jevStatus;
  const usage = status?.usage;
  const latestBlock = [...state.runHistory].find(r => r.status === "jev_action_required");
  const durable = usage?.accountStatus;
  const durableBlocked = durable?.outcome === "http_error" && [401,402,403].includes(durable.httpStatus ?? 0);
  const blocked = durableBlocked || latestBlock && (!usage?.lastAt || Date.parse(String(latestBlock.recordedAt || "")) > Date.parse(usage.lastAt));
  const grouped = (groups: NonNullable<typeof usage>["byTask"], byTask = false): HTMLElement => h("div", {}, Object.entries(groups || {}).sort(([a],[b])=>b.localeCompare(a)).slice(0,30).map(([key,value])=>rowItem(byTask ? state.tasks.find(task=>task.id===key)?.name || key : key, `成功 ${value.calls} · 失败 ${value.failures} · 重试 ${value.retries} · 输入 ${value.inputTokens ?? "未知"} / 输出 ${value.outputTokens ?? "未知"} Token`)));
  const tokens = (value: number | null | undefined, coverage: number | undefined) => value == null ? "未知（尚无用量记录）" : `${fmtNum(value)} Token · ${coverage ?? 0}/${usage?.calls ?? 0} 次记录含此用量`;
  return h("div", { class: "settings-page" }, [
    panel("手卡理解 · 千问",rowItem("用途","理解品牌手卡，给出可编辑候选条件；确认后才生效"),rowItem("模型",state.qwenStatus?.model||"尚未读取"),rowItem("连接状态",state.qwenStatus?.configured?"已读取现有配置，真实调用仍需验证":"未读取到已有千问配置；不会借用Jev密钥"),h("p",{text:"千问负责手卡理解，Jev负责快速达人适配判断。现有凭据不重设。"})),
    panel("分析模型配置 · Jev",
      rowItem("服务", "TypeSafe Jev 云端达人分析"),
      rowItem("配置状态", status?.configured && status?.enabled ? "已配置并启用（不代表调用已验证）" : "尚未配置或未启用"),
      rowItem("凭据保护", status?.credentialProtection || "未知"),
      rowItem("配置模型", status?.model || "jev-latest"),
      rowItem("最近实际模型", usage?.lastModel || "未知（尚无版本记录）"),
      h("div", { class: "button-row", "data-preserve-input": "true" }, [jevKey, jevModel, modelOptions, jevSave, testButton]),
      ...(status?.connectionTest ? [rowItem("最近单次测试",`${fmtTime(status.connectionTest.checkedAt)} · ${status.connectionTest.message} · ${status.connectionTest.elapsedMs} 毫秒`),rowItem("测试实际模型及用量",`${status.connectionTest.model || "未知"} · 输入 ${status.connectionTest.usage?.input_tokens ?? "未知"} / 输出 ${status.connectionTest.usage?.output_tokens ?? "未知"} Token；测试通过不代表达人名单准确率或账户余额已核实`)] : []),
      rowItem("模型选择", "jev-latest：稳定版；jev-preview：预览版；也可填写固定版本。留空 Key 保留原配置。"),
      rowItem("连接状态", blocked ? "最近调用被账户问题阻止；处理后尚未重新验证" : usage?.lastAt ? `最近成功调用：${fmtTime(usage.lastAt)}` : "尚无本地成功记录；未发起付费测试"),
      ...(blocked ? [rowItem("最近阻断", durableBlocked ? `${fmtTime(durable?.recordedAt)} · HTTP ${durable?.httpStatus} · 请到官网检查账户、额度及权限` : `${fmtTime(latestBlock?.recordedAt)} · ${latestBlock?.message || "请到官网检查账户、额度及权限"}`)] : []),
      rowItem("分析用途", "硬条件核验后判断作品与品牌匹配度；证据不足进入待复核"),
      rowItem("运行方式", "由千寻直接调用云服务；打开软件并联网即可，无需 Codex"),
    ),
    panel("Jev 用量与额度",
      h("div", { class: "button-row" }, [
        h("button", { class: "primary", type: "button", onclick: handlers.onOpenJevConsole, text: "充值 / 额度管理（Jev 官网）" }),
        h("button", { type: "button", onclick: handlers.onRefresh, text: "刷新本地用量" }),
      ]),
      rowItem("账户余额", "未知 · 请在 Jev 官网查看"),
      rowItem("实际花费", "未知 · 尚未取得官方账单"),
      rowItem("本机成功调用记录", `${fmtNum(usage?.calls ?? 0)} 次（仅含开始记账后的记录）`),
      rowItem("调用尝试", `${fmtNum(usage?.attempts ?? usage?.calls ?? 0)} 次 · 失败 ${fmtNum(usage?.failures ?? 0)} 次 · 重试 ${fmtNum(usage?.retries ?? 0)} 次`),
      rowItem("每次尝试平均耗时", usage?.averageLatencyMs == null ? "未知（无耗时记录）" : `${usage.averageLatencyMs} 毫秒（仅含有耗时记录的尝试）`),
      ...(usage?.writeError ? [h("p",{role:"alert",text:"本机用量记账失败；部分消耗可能缺失。云端结果已保留，不会为记账重试付费请求。"})] : []),
      h("details", {}, [h("summary",{text:"按品牌任务查看用量（最多30项）"}), grouped(usage?.byTask,true)]),
      h("details", {}, [h("summary",{text:"按日期查看用量（北京时间，最近30个有记录日期）"}), grouped(usage?.byDate)]),
      rowItem("输入消耗", tokens(usage?.inputTokens, usage?.inputCoverage)),
      rowItem("输出用量", tokens(usage?.outputTokens, usage?.outputCoverage)),
      rowItem("记录范围", usage?.firstAt ? `${fmtTime(usage.firstAt)} 至 ${fmtTime(usage.lastAt)} · 本机所有品牌任务` : "尚无记录；此前历史消耗未知"),
      rowItem("账单说明", "本地 Token 记录不等于账户余额或账单；缺失、失败及其他设备的消耗需到官网核对。刷新不会调用分析模型。"),
      ...(usage?.readError || usage?.invalidRows ? [rowItem("记录提示", `用量记录存在读取或格式问题，统计可能不完整（异常行 ${usage?.invalidRows ?? 0}）`)] : []),
    ),
  ]);
}

// ---------- 9. 抖店浏览器 ----------

let activeShop: "A" | "B" = "A";

export function browserPage(handlers: PageHandlers, state?:Bootstrap): HTMLElement {
  const tab = (shop: "A" | "B"): HTMLElement =>
    h("button", {
      class: `shop-tab${activeShop === shop ? " active" : ""}`,
      type: "button",
      onclick: () => {
        activeShop = shop;
        handlers.onLayoutShop(shop);
        handlers.onRefresh();
      },
    }, [state?.task.shops?.[shop]?.label || `抖店 ${shop}`]);

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
      h("button", { type: "button", "aria-label":"返回上一页", onclick: () => handlers.onControlShop(activeShop, "back") }, ["←"]),
      h("button", { type: "button", "aria-label":"前进到下一页", onclick: () => handlers.onControlShop(activeShop, "forward") }, ["→"]),
      h("button", { type: "button", "aria-label":"刷新店铺页面", onclick: () => handlers.onControlShop(activeShop, "reload") }, ["↻"]),
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
    case "auto-collect": return autoCollectPage(state, handlers, rerender);
    case "dashboard": return dashboardPage(state);
    case "brand-card": return brandCardPage(state, handlers);
    case "creators": return creatorsPage(state, rerender, handlers);
    case "contacts": return outreachPage(state, handlers, rerender);
    case "outreach": return outreachPage(state, handlers, rerender);
    case "delivery": return outreachPage(state, handlers, rerender);
    case "models": return modelsPage(state, handlers);
    case "settings": return settingsPage(state, handlers);
    case "browser": return browserPage(handlers,state);
    default: return autoCollectPage(state, handlers);
  }
}

function historyStatus(status: string): string {
 const labels: Record<string, string> = { pipeline_error: "流程已停止：请查看失败原因", jev_action_required: "Jev 账户需要处理", finished: "作业已结束", paused: "已暂停", collection_checkpoint_saved: "采集断点已保存", collection_incomplete: "采集未达目标", shop_error: "店铺作业异常", filters_applied: "筛选规则已应用", filter_controls_clicked: "后台筛选操作记录", platform_filters_confirmed: "后台类目与带货方式已核对", worker_stderr: "运行诊断记录", progress: "作业进度", "recovered-artifact": "历史文件已恢复" };
 return labels[status] || (/progress/.test(status) ? "采集与审核进行中" : "运行诊断记录");
}
