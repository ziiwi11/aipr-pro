const path = require("node:path");

const ACTIONS = {
  "apply-saved-audit": "audit_strict_contact_highwater.py",
  "audit-saved-list": "audit_strict_contact_highwater.py",
  "verify-saved-contacts": "verify_creator_evidence_cdp.py",
  "review-saved": "verify_creator_evidence_cdp.py",
  "probe-login": "probe_two_shop_login_cdp.py",
  "collect-creators": "collect_and_contact_pipeline.py",
  "contact-icons": "scrape_buyin_profile_contact_icons_cdp.py",
  "export-original": "export_original_format_with_contacts.py",
  "deliver-current": "finalize_creator_delivery.py",
};

function buildWorkerCommand(action, task = {}, appPaths = {}) {
  const script = ACTIONS[action];
  if (!script) throw new Error(`Unsupported worker action: ${action}`);
  if (!appPaths.pythonExe || !appPaths.backendDir) throw new Error("Worker runtime is not configured");

  const completeChannels = action === "contact-icons" && task.deliveryPath && task.strategyPath;
  const args = [path.join(appPaths.backendDir, completeChannels ? "complete_saved_contact_channels.py" : script)];
  const port = Number(appPaths.internalCdpPort) || 9222;
  const endpoint = `http://127.0.0.1:${port}`;
  if (["review-saved", "verify-saved-contacts"].includes(action)) {
    if (!task.outputDir) throw new Error("Saved task data is required");
    args.push(action === "review-saved" ? "--review-saved" : "--verify-saved-contacts", "--input", path.join(task.outputDir, "aipr_strict_contact_highwater.json"),
      "--out-dir", task.outputDir, "--limit", "20", "--lanes-per-shop", "1",
      "--keywords-json", JSON.stringify(task.collectionStrategy?.keywords || ["美妆", "唇护理"]),
      "--shop-a", `${endpoint}?shop=A`, "--shop-b", `${endpoint}?shop=B`);
  }
  if (action === "probe-login") {
    args.push(
      "--out-dir", task.outputDir || path.dirname(task.deliveryPath || task.queuePath || "."),
      "--shop-a", `${endpoint}?shop=A`,
      "--shop-b", `${endpoint}?shop=B`,
    );
  }
  if (action === "contact-icons") {
    if (!completeChannels && !task.queuePath) throw new Error("Contact queue path is required");
    args.push(
      "--input", completeChannels ? path.join(task.outputDir || path.dirname(task.deliveryPath), "aipr_strict_contact_highwater.json") : task.queuePath,
      "--out-dir", task.outputDir || path.dirname(task.queuePath),
      "--delay-ms", String(Math.max(3000, Number(task.contactDelayMs) || 3200)),
      "--shop-a", `${endpoint}?shop=A`,
      "--shop-b", `${endpoint}?shop=B`,
    );
  }
  if (completeChannels) {
    args.push("--strategy", task.strategyPath, "--task-id", task.id, "--task-name", task.name);
    if (task.robotQueuePath) args.push("--robot-queue", task.robotQueuePath);
  }
  if (action === "collect-creators") {
    if (!task.strategyPath) throw new Error("Collection strategy path is required");
    args.push(
      "--strategy", task.strategyPath,
      "--out-dir", task.outputDir || path.dirname(task.strategyPath),
      "--shop-a", `${endpoint}?shop=A`,
      "--shop-b", `${endpoint}?shop=B`,
      "--delay-ms", String(Math.max(3000, Number(task.contactDelayMs) || 3200)),
      "--task-id", task.id || "brand-task",
      "--task-name", task.name || "品牌达人任务",
    );
    if (task.originalWorkbookPath) args.push("--original-workbook", task.originalWorkbookPath);
    if (task.robotQueuePath) args.push("--robot-queue", task.robotQueuePath);
  }
  if (["audit-saved-list", "apply-saved-audit"].includes(action)) {
    if (!task.strategyPath || !task.outputDir) throw new Error("Saved task data is required");
    args.push("--saved-task-dir", task.outputDir, "--strategy", task.strategyPath);
    if (task.batchScope?.baselinePath) args.push("--batch-baseline",task.batchScope.baselinePath);
    if (action === "apply-saved-audit") args.push("--apply-pending");
  }
  if (action === "deliver-current") {
    if (!task.strategyPath || !task.outputDir) throw new Error("Saved task data is required");
    args.push("--input", path.join(task.outputDir, "aipr_strict_contact_highwater.json"),
      "--strategy", task.strategyPath, "--out-dir", task.outputDir,
      "--task-id", task.id || "brand-task", "--task-name", task.name || "品牌任务",
      "--require-strict-highwater", "--deliver-current");
    if(task.batchScope){
      args.push("--batch-baseline",task.batchScope.baselinePath);
      args[args.indexOf("--out-dir")+1]=task.batchScope.outputDir;
      args.push("--robot-queue",path.join(task.batchScope.outputDir,"outreach-queue.ndjson"));
    }else if (task.robotQueuePath) args.push("--robot-queue", task.robotQueuePath);
    if (task.originalWorkbookPath) args.push("--original-workbook", task.originalWorkbookPath);
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
