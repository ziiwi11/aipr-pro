const path = require("node:path");

const ACTIONS = {
  "probe-login": "probe_two_shop_login_cdp.py",
  "collect-creators": "collect_and_contact_pipeline.py",
  "contact-icons": "scrape_buyin_profile_contact_icons_cdp.py",
  "export-original": "export_original_format_with_contacts.py",
};

function buildWorkerCommand(action, task = {}, appPaths = {}) {
  const script = ACTIONS[action];
  if (!script) throw new Error(`Unsupported worker action: ${action}`);
  if (!appPaths.pythonExe || !appPaths.backendDir) throw new Error("Worker runtime is not configured");

  const args = [path.join(appPaths.backendDir, script)];
  if (action === "probe-login") {
    args.push(
      "--out-dir", task.outputDir || path.dirname(task.deliveryPath || task.queuePath || "."),
      "--shop-a", "http://127.0.0.1:9222?shop=A",
      "--shop-b", "http://127.0.0.1:9222?shop=B",
    );
  }
  if (action === "contact-icons") {
    if (!task.queuePath) throw new Error("Contact queue path is required");
    args.push(
      "--input", task.queuePath,
      "--out-dir", task.outputDir || path.dirname(task.queuePath),
      "--delay-ms", String(Math.max(3000, Number(task.contactDelayMs) || 3200)),
      "--shop-a", "http://127.0.0.1:9222?shop=A",
      "--shop-b", "http://127.0.0.1:9222?shop=B",
    );
  }
  if (action === "collect-creators") {
    if (!task.strategyPath) throw new Error("Collection strategy path is required");
    args.push(
      "--strategy", task.strategyPath,
      "--out-dir", task.outputDir || path.dirname(task.strategyPath),
      "--shop-a", "http://127.0.0.1:9222?shop=A",
      "--shop-b", "http://127.0.0.1:9222?shop=B",
      "--delay-ms", String(Math.max(3000, Number(task.contactDelayMs) || 3200)),
      "--task-id", task.id || "brand-task",
      "--task-name", task.name || "品牌达人任务",
    );
    if (task.originalWorkbookPath) args.push("--original-workbook", task.originalWorkbookPath);
    if (task.robotQueuePath) args.push("--robot-queue", task.robotQueuePath);
  }
  if (action === "export-original") {
    if (!task.originalWorkbookPath || !task.deliveryPath) {
      throw new Error("Original workbook and delivery paths are required");
    }
    args.push(
      "--source", task.originalWorkbookPath,
      "--delivery", task.deliveryPath,
      "--out-dir", task.outputDir || path.dirname(task.deliveryPath),
      "--task-name", task.name || "品牌任务",
    );
  }
  return { command: appPaths.pythonExe, args, shell: false };
}

function classifyWorkerEvent(line) {
  let payload;
  try {
    payload = JSON.parse(String(line || "").trim());
  } catch {
    return { type: "log", message: String(line || "").trim() };
  }
  const text = `${payload.status || ""} ${payload.message || ""}`;
  if (payload.status === "contact_collection_finished") {
    return { ...payload, type: "contact-summary" };
  }
  if (payload.status === "delivery_ready") {
    return { ...payload, type: "delivery-ready" };
  }
  if (payload.status === "login_probe_finished" && payload.shops) {
    return { ...payload, type: "login-summary" };
  }
  if (/daily_quota_exhausted|查看达人联系方式次数已达上限|pipeline_waiting_for_contact_quota/i.test(text)) {
    return { ...payload, type: "paused", reason: "daily_contact_quota" };
  }
  if (/rate_limited|请求过于频繁|稍后再试|限流/i.test(text)) {
    return { ...payload, type: "paused", reason: "rate_limited" };
  }
  if (/contact_revealed|plain_contact|wechat|phone/i.test(text) || payload.wechat || payload.phone) {
    return { ...payload, type: "contact" };
  }
  if (/error|failed|异常/i.test(text)) return { ...payload, type: "error" };
  return { ...payload, type: "progress" };
}

module.exports = { buildWorkerCommand, classifyWorkerEvent };
