const FLOW_REFRESH_MS = 5000;

export function flowProgress(snapshot, now = Date.now()) {
  if (snapshot?.workerRunning !== true && snapshot?.taskStatus === "completed") return "采集已完成，正式名单和交付文件已保存。";
  if (snapshot?.workerRunning !== true) return "采集已停止，已保存进度；可从断点继续。";
  const records = Array.isArray(snapshot?.records) ? snapshot.records : [];
  const latest = records.reduce((found, row) => {
    const time = Date.parse(row.updated_at || "");
    return Number.isFinite(time) && time > found.time ? { time, row } : found;
  }, { time: 0, row: null });
  const updated = Date.parse(snapshot?.updatedAt || "");
  const age = Number.isFinite(updated) ? Math.max(0, Math.floor((now - updated) / 1000)) : null;
  const stages = {
    discovered: "保存候选", identity_unique: "核对达人身份", evidence_reviewing: "复核主页、作品与 Jev 判断",
    suitable: "通过适配审核", contact_revealing: "获取授权联系方式", plaintext_unique: "核对联系人重复",
    listed: "正式入库", duplicate_contact: "排除重复联系人", not_authorized: "记录类目不匹配",
    not_available: "记录联系方式不可用", insufficient_evidence: "记录证据不足",
    unsuitable: "记录不适配达人", retry_pending: "保存待重试断点", error: "记录单人处理失败",
  };
  const stage = stages[latest.row?.state] || "等待首个处理结果";
  const waiting = records.filter(row => row.state === "evidence_reviewing" && row.reason).length;
  const elapsed = age === null ? "尚无更新时间" : age < 60 ? `${age} 秒前` : `${Math.floor(age / 60)} 分 ${age % 60} 秒前`;
  return `任务运行中 · 最近一步：${stage} · 数据更新：${elapsed} · 待复核 ${waiting} 人。${age !== null && age >= 60 ? "正在等待新结果；复核和联系方式揭示有访问间隔，累计人数暂未变化。" : ""}`;
}

function metric(label, value, tone = "") {
  return `<div class="aipr-flow-metric ${tone}"><span>${label}</span><strong>${Number(value || 0)}</strong></div>`;
}

export function renderFlow(snapshot) {
  let panel = document.querySelector("[data-aipr-realtime-flow]");
  if (!panel) {
    panel = document.createElement("aside");
    panel.dataset.aiprRealtimeFlow = "true";
    panel.className = "aipr-realtime-flow-panel";
    (document.querySelector(".page-body") || document.body).appendChild(panel);
  }
  const metrics = { ...(snapshot?.metrics || {}) };
  if (snapshot?.workerRunning === false) metrics.contactRevealing = 0;
  const available = snapshot?.available === true;
  panel.innerHTML = `
    <div class="aipr-flow-title">
      <div><span>逐达人实时流程</span><strong>${available ? "已接入" : "等待首位候选"}</strong></div>
      <i class="${snapshot?.workerRunning === true ? "running" : ""}"></i>
    </div>
    <div class="aipr-flow-metrics">
      ${metric("候选", metrics.candidates)}
      ${metric("合适", metrics.suitable)}
      ${metric("取联系方式中", metrics.contactRevealing)}
      ${metric("含明文候选", metrics.plaintext, "valid")}
      ${metric("本流程入库", metrics.listed, "formal")}
    </div>
    <div class="aipr-flow-rule">此处仅统计当前采集流程；历史导入名单见联系方式页。审核通过且有唯一明文才入库，发送需另行授权。</div>
  `;
  const progress = document.createElement("div");
  progress.className = "aipr-flow-rule";
  progress.setAttribute("role", "status");
  progress.textContent = flowProgress(snapshot);
  panel.appendChild(progress);

}

async function refreshFlow() {
  try {
    const api = window.aiprDesktop?.getRealtimeCreatorFlow;
    if (!api) return;
    renderFlow(await api());
  } catch {
    renderFlow({ available: false, metrics: {} });
  }
}

refreshFlow();
const flowTimer = window.setInterval(() => {
  if (document.visibilityState === "visible") refreshFlow();
}, FLOW_REFRESH_MS);
window.addEventListener("beforeunload", () => window.clearInterval(flowTimer), { once: true });
window.aiprDesktop?.onWorkerEvent?.(() => refreshFlow());
