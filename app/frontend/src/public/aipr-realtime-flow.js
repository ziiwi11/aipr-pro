const FLOW_REFRESH_MS = 5000;

function metric(label, value, tone = "") {
  return `<div class="aipr-flow-metric ${tone}"><span>${label}</span><strong>${Number(value || 0)}</strong></div>`;
}

function renderFlow(snapshot) {
  let panel = document.querySelector("[data-aipr-realtime-flow]");
  if (!panel) {
    panel = document.createElement("aside");
    panel.dataset.aiprRealtimeFlow = "true";
    panel.className = "aipr-realtime-flow-panel";
    document.body.appendChild(panel);
  }
  const metrics = snapshot?.metrics || {};
  const available = snapshot?.available === true;
  panel.innerHTML = `
    <div class="aipr-flow-title">
      <div><span>逐达人实时流程</span><strong>${available ? "已接入" : "等待首位候选"}</strong></div>
      <i class="${metrics.contactRevealing ? "running" : ""}"></i>
    </div>
    <div class="aipr-flow-metrics">
      ${metric("候选", metrics.candidates)}
      ${metric("合适", metrics.suitable)}
      ${metric("取联系方式中", metrics.contactRevealing)}
      ${metric("明文唯一", metrics.plaintext, "valid")}
      ${metric("正式名单", metrics.listed, "formal")}
    </div>
    <div class="aipr-flow-rule">单达人审核通过后才获取联系方式；只有唯一明文进入正式名单和 AI 授权。</div>
  `;
  for (const button of document.querySelectorAll("button")) {
    if (!String(button.textContent || "").includes("联系方式")) continue;
    for (const badge of button.querySelectorAll("span, b, strong, small, i")) {
      if (/^\s*\d+\s*$/u.test(String(badge.textContent || ""))) {
        badge.textContent = String(Number(metrics.plaintext || 0));
      }
    }
  }
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
