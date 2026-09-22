const fs = require("node:fs");
const path = require("node:path");

const ARTIFACT_LABELS = {
  finalJson: "最终 JSON",
  standardXlsx: "标准达人名单",
  originalXlsx: "原格式补联系方式",
  robotNdjson: "机器人逐条队列",
  robotBatchJson: "机器人批量包",
  handoffManifest: "交接清单",
};

function resolvePersistentTaskDir(documentsDir, taskId) {
  const safeId = String(taskId || "brand-task").replace(/[^a-zA-Z0-9_-]/g, "-");
  return path.join(path.resolve(documentsDir), "AIPR Pro", "品牌任务", safeId);
}

function discoverDeliveryArtifacts(deliveryPath) {
  const resolved = path.resolve(String(deliveryPath || ""));
  if (!resolved || !fs.existsSync(resolved)) return emptyCenter(resolved);
  let delivery;
  try {
    delivery = JSON.parse(fs.readFileSync(resolved, "utf8"));
  } catch {
    return emptyCenter(resolved);
  }
  const outputDir = path.dirname(resolved);
  const declared = delivery.artifacts || {};
  const candidates = {
    finalJson: declared.finalJson || resolved,
    standardXlsx: declared.standardXlsx || findLatest(outputDir, (name) => name.endsWith(".xlsx") && name.includes("最终达人名单")),
    originalXlsx: declared.originalXlsx || findLatest(outputDir, (name) => name.endsWith(".xlsx") && name.includes("原格式补联系方式")),
    robotNdjson: declared.robotNdjson || findLatest(outputDir, (name) => name.endsWith(".ndjson")),
    robotBatchJson: declared.robotBatchJson || findLatest(outputDir, (name) => name.endsWith(".json") && (name.includes("机器人批量") || name.includes("robot-batch"))),
    handoffManifest: declared.handoffManifest || findLatest(outputDir, (name) => name.endsWith(".json") && name.includes("交接清单")),
  };
  const files = Object.fromEntries(Object.entries(candidates).map(([key, target]) => [key, artifact(key, target)]));
  const result = {
    deliveryPath: resolved,
    outputDir,
    files,
    metrics: {
      candidateCount: numberOr(delivery.candidate_count, delivery.rows?.length || 0),
      plainContactCount: numberOr(delivery.plain_contact_count, 0),
      wechatCount: numberOr(delivery.wechat_contact_count, 0),
      phoneCount: numberOr(delivery.phone_contact_count, 0),
      robotCount: numberOr(delivery.robot_queue_count, delivery.robot_queue?.length || 0),
    },
    robotContractVersion: String(delivery.robot_contract_version || ""),
    createdAt: String(delivery.created_at || ""),
  };
  result.readiness = buildRehearsalReadiness(result);
  return result;
}

function buildRehearsalReadiness(center = {}) {
  const files = center.files || {};
  const required = Object.keys(ARTIFACT_LABELS);
  const missing = required.filter((key) => !files[key]?.exists);
  const robotCount = Number(center.metrics?.robotCount) || 0;
  const candidateCount = Number(center.metrics?.candidateCount) || 0;
  const checks = [
    { key: "delivery-data", label: "最终名单可读取", passed: Boolean(files.finalJson?.exists && candidateCount > 0) },
    { key: "spreadsheets", label: "标准表与原格式表齐全", passed: Boolean(files.standardXlsx?.exists && files.originalXlsx?.exists) },
    { key: "robot-files", label: "机器人双格式齐全", passed: Boolean(files.robotNdjson?.exists && files.robotBatchJson?.exists) },
    { key: "robot-records", label: "存在待建联任务", passed: robotCount > 0 },
    { key: "handoff-manifest", label: "交接清单已生成", passed: Boolean(files.handoffManifest?.exists) },
  ];
  return { ready: missing.length === 0 && checks.every((item) => item.passed), missing, checks };
}

function artifact(key, target) {
  const resolved = target ? path.resolve(String(target)) : "";
  let size = 0;
  let modifiedAt = "";
  if (resolved && fs.existsSync(resolved)) {
    const stats = fs.statSync(resolved);
    size = stats.size;
    modifiedAt = stats.mtime.toISOString();
  }
  return { key, label: ARTIFACT_LABELS[key], path: resolved, exists: Boolean(resolved && fs.existsSync(resolved)), size, modifiedAt };
}

function findLatest(dir, predicate) {
  if (!fs.existsSync(dir)) return "";
  return fs.readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && predicate(entry.name))
    .map((entry) => path.join(dir, entry.name))
    .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0] || "";
}

function emptyCenter(deliveryPath) {
  const files = Object.fromEntries(Object.keys(ARTIFACT_LABELS).map((key) => [key, artifact(key, key === "finalJson" ? deliveryPath : "")]));
  const result = { deliveryPath, outputDir: deliveryPath ? path.dirname(deliveryPath) : "", files, metrics: { candidateCount: 0, plainContactCount: 0, wechatCount: 0, phoneCount: 0, robotCount: 0 }, robotContractVersion: "", createdAt: "" };
  result.readiness = buildRehearsalReadiness(result);
  return result;
}

function numberOr(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

module.exports = { buildRehearsalReadiness, discoverDeliveryArtifacts, resolvePersistentTaskDir };
