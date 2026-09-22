export function isOutreachEligible(creator = {}) {
  const direct = String(creator.wechat || creator.phone || "").trim();
  const fallback = String(creator.plainContact || "").trim();
  return Boolean(direct || (fallback && !fallback.includes("@")));
}

export function selectableCreators(creators = []) {
  return creators.filter(isOutreachEligible);
}

export function previewSummary(preview = {}) {
  return `已选 ${preview.selectedCount || 0} · 可同步 ${preview.validCount || 0} · 缺失 ${preview.missingCount || 0} · 重复 ${preview.duplicateCount || 0} · 当前发送 0`;
}

export function canStartBatch(batch, confirmed) {
  return batch?.status === "synced" && confirmed === true;
}

const state = {
  bootstrap: null,
  outreach: null,
  selected: new Set(),
  preview: null,
  batch: null,
  busy: false,
  error: "",
};

if (typeof window !== "undefined" && typeof document !== "undefined") {
  installOutreachWorkbench();
}

function installOutreachWorkbench() {
  const observer = new MutationObserver(() => mountIfNeeded());
  observer.observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener("click", (event) => {
    const button = event.target.closest?.("button");
    if (button?.textContent?.includes("配置机器人接口")) {
      event.preventDefault();
      event.stopImmediatePropagation();
      mountIfNeeded();
      document.querySelector("#aipr-leishen-workbench")?.scrollIntoView({ behavior: "smooth", block: "start" });
      refresh();
    }
  }, true);
  mountIfNeeded();
}

function mountIfNeeded() {
  const page = document.querySelector(".outreach-page");
  if (!page || page.querySelector("#aipr-leishen-workbench")) return;
  const panel = document.createElement("section");
  panel.id = "aipr-leishen-workbench";
  panel.className = "panel aipr-leishen-workbench";
  panel.addEventListener("click", handleAction);
  panel.addEventListener("change", handleSelection);
  const banner = page.querySelector(".outreach-banner");
  banner?.insertAdjacentElement("afterend", panel);
  render();
  refresh();
}

async function refresh() {
  if (state.busy) return;
  state.busy = true;
  state.error = "";
  render();
  try {
    const bridge = requireBridge();
    [state.bootstrap, state.outreach] = await Promise.all([bridge.getBootstrap(), bridge.getOutreachState()]);
    const latest = state.outreach?.batches?.[0];
    if (latest) state.batch = latest;
  } catch (error) {
    state.error = error?.message || "无法读取 AI 建联状态";
  } finally {
    state.busy = false;
    render();
  }
}

async function handleAction(event) {
  const action = event.target.closest?.("button")?.dataset?.action;
  if (!action || state.busy) return;
  const creators = selectableCreators(state.bootstrap?.creators || []);
  if (action === "refresh") return refresh();
  if (action === "select-all") {
    state.selected = new Set(creators.map((creator) => String(creator.id)));
    return render();
  }
  if (action === "clear") {
    state.selected.clear();
    state.preview = null;
    return render();
  }
  state.busy = true;
  state.error = "";
  render();
  try {
    const bridge = requireBridge();
    if (action === "preview") {
      state.preview = await bridge.previewOutreachAuthorization([...state.selected]);
    } else if (action === "authorize-sync") {
      if (!state.preview?.previewId) throw new Error("请先生成授权预览");
      const authorized = await bridge.authorizeOutreachBatch(state.preview.previewId);
      const result = await bridge.syncOutreachBatch(authorized.batchId);
      state.batch = result.batch;
      state.preview = null;
    } else if (action === "start") {
      if (!canStartBatch(state.batch, true)) throw new Error("请先授权并同步批次");
      const confirmed = window.confirm(`即将让雷神开始处理 ${state.batch.validCount || 0} 位已授权达人。\n\n这会实际操作微信并可能发送消息，是否继续？`);
      if (!confirmed) return;
      const result = await bridge.startOutreachBatch(state.batch.batchId);
      state.batch = result.batch;
    }
    state.outreach = await bridge.getOutreachState();
  } catch (error) {
    state.error = error?.message || "AI 建联操作失败";
  } finally {
    state.busy = false;
    render();
  }
}

function handleSelection(event) {
  const checkbox = event.target.closest?.('input[data-creator-id]');
  if (!checkbox) return;
  if (checkbox.checked) state.selected.add(checkbox.dataset.creatorId);
  else state.selected.delete(checkbox.dataset.creatorId);
  state.preview = null;
  render();
}

function render() {
  const panel = document.querySelector("#aipr-leishen-workbench");
  if (!panel) return;
  const creators = state.bootstrap?.creators || [];
  const eligible = selectableCreators(creators);
  const leishenStatus = state.outreach?.leishen?.status;
  const permission = state.outreach?.leishen?.permissions?.result || {};
  const online = leishenStatus?.online === true;
  const batch = state.batch;
  const history = (state.outreach?.history || state.bootstrap?.runHistory || []).slice(0, 12);
  panel.innerHTML = `
    <header class="aipr-ls-header">
      <div><span class="kicker">雷神 AI 建联系统</span><h2>批量选择、授权与 AI 建联</h2><p>名单同步不会自动发送；实际启动必须再次人工确认。</p></div>
      <button class="button secondary" data-action="refresh" ${state.busy ? "disabled" : ""}>${state.busy ? "检查中…" : "刷新状态"}</button>
    </header>
    <div class="aipr-ls-status-grid">
      ${metric("雷神连接", online ? "已连接" : "未连接", online ? "ready" : "pending")}
      ${metric("候选名单", creators.length, "")}
      ${metric("可建联", eligible.length, eligible.length ? "ready" : "pending")}
      ${metric("已选择", state.selected.size, state.selected.size ? "ready" : "")}
      ${metric("辅助功能", permission.accessibility === true ? "已授权" : "待授权", permission.accessibility === true ? "ready" : "pending")}
      ${metric("当前批次", batch?.status ? statusLabel(batch.status) : "未创建", batch?.status === "running" ? "ready" : "")}
    </div>
    ${state.error ? `<div class="aipr-ls-error">${escapeHtml(state.error)}</div>` : ""}
    <div class="aipr-ls-actions">
      <button class="button secondary" data-action="select-all" ${!eligible.length ? "disabled" : ""}>全选可建联达人</button>
      <button class="button secondary" data-action="clear" ${!state.selected.size ? "disabled" : ""}>清空选择</button>
      <button class="button primary" data-action="preview" ${!state.selected.size || state.busy ? "disabled" : ""}>生成授权预览</button>
    </div>
    ${state.preview ? previewBlock(state.preview) : ""}
    ${batchBlock(batch, online)}
    <div class="aipr-ls-columns">
      <section><h3>达人选择</h3><div class="aipr-ls-creator-list">${creatorRows(creators)}</div></section>
      <section><h3>运行历史</h3><div class="aipr-ls-history">${historyRows(history)}</div></section>
    </div>`;
}

function previewBlock(preview) {
  return `<div class="aipr-ls-preview"><strong>授权预览</strong><span>${escapeHtml(previewSummary(preview))}</span><small>同步后仍不会自动发送；你还需要单独点击“授权并开始 AI 建联”。</small><button class="button primary" data-action="authorize-sync" ${preview.validCount ? "" : "disabled"}>确认授权并同步到雷神</button></div>`;
}

function batchBlock(batch, online) {
  if (!batch) return "";
  return `<div class="aipr-ls-batch"><div><strong>批次 ${escapeHtml(batch.batchId || "")}</strong><span>${escapeHtml(statusLabel(batch.status))} · ${batch.validCount || 0} 位达人</span></div><button class="button primary danger" data-action="start" ${batch.status === "synced" && online ? "" : "disabled"}>授权并开始 AI 建联</button></div>`;
}

function creatorRows(creators) {
  if (!creators.length) return '<div class="aipr-ls-empty">当前任务没有可显示名单。</div>';
  return creators.map((creator) => {
    const eligible = isOutreachEligible(creator);
    const id = String(creator.id || "");
    const checked = state.selected.has(id);
    return `<label class="aipr-ls-creator ${eligible ? "" : "disabled"}"><input type="checkbox" data-creator-id="${escapeHtml(id)}" ${checked ? "checked" : ""} ${eligible ? "" : "disabled"}><span><strong>${escapeHtml(creator.name || "未命名达人")}</strong><small>${escapeHtml(creator.douyin || "待补抖音号")}</small></span><em>${eligible ? escapeHtml(maskedContact(creator)) : "缺少微信/手机号"}</em></label>`;
  }).join("");
}

function historyRows(history) {
  if (!history.length) return '<div class="aipr-ls-empty">暂无历史；后续采集、授权和雷神执行会保存在这里。</div>';
  return history.map((item) => `<article><strong>${escapeHtml(historyLabel(item))}</strong><span>${escapeHtml(item.message || item.artifact || statusLabel(item.status))}</span><time>${escapeHtml(formatTime(item.recordedAt || item.artifactModifiedAt))}</time></article>`).join("");
}

function metric(label, value, tone) {
  return `<div class="aipr-ls-metric ${tone}"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function maskedContact(creator) {
  const value = String(creator.wechat || creator.phone || creator.plainContact || "");
  if (value.length <= 4) return "****";
  return `${value.slice(0, 2)}***${value.slice(-2)}`;
}

function statusLabel(value) {
  return ({ previewed: "待授权", authorized: "已授权", synced: "已同步待启动", running: "AI 建联运行中", checkpoint: "采集检查点", artifact: "交付文件" })[value] || String(value || "-");
}

function historyLabel(item) {
  return ({ "outreach-previewed": "生成授权预览", "outreach-authorized": "批量授权", "leishen-synced": "同步到雷神", "leishen-started": "启动 AI 建联", "recovered-artifact": "恢复历史文件", started: "任务开始", finished: "任务结束" })[item.type] || item.type || "运行记录";
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN", { hour12: false });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
}

function requireBridge() {
  const bridge = window.aiprDesktop;
  if (!bridge?.getOutreachState || !bridge?.previewOutreachAuthorization) throw new Error("当前 AIPR 安装包尚未加载雷神接口");
  return bridge;
}
