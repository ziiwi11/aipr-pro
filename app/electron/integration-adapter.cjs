const fs = require("node:fs");
const path = require("node:path");

class IntegrationAdapter {
  constructor(baseDir) {
    this.dir = path.join(baseDir, "integrations");
    this.paths = {
      rules: path.join(this.dir, "portable-rules.json"),
      outreachQueue: path.join(this.dir, "outreach-queue.ndjson"),
    };
    fs.mkdirSync(this.dir, { recursive: true });
  }

  saveRules(bundle) {
    if (bundle?.schemaVersion !== "1.0") {
      throw new Error(`不支持的规则版本：${bundle?.schemaVersion || "未知"}`);
    }
    writeAtomic(this.paths.rules, JSON.stringify(bundle, null, 2));
    return this.paths.rules;
  }

  readRules() {
    if (!fs.existsSync(this.paths.rules)) return null;
    return JSON.parse(fs.readFileSync(this.paths.rules, "utf8"));
  }

  enqueueOutreach(payload) {
    const record = { ...payload, queuedAt: payload.queuedAt || new Date().toISOString() };
    fs.appendFileSync(this.paths.outreachQueue, `${JSON.stringify(record)}\n`, "utf8");
    return record;
  }

  readOutreachQueue() {
    if (!fs.existsSync(this.paths.outreachQueue)) return [];
    return fs.readFileSync(this.paths.outreachQueue, "utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
  }

  previewOutreachBatch(batchPath) {
    const resolved = path.resolve(String(batchPath || ""));
    if (!fs.existsSync(resolved)) throw new Error("机器人交接文件不存在");
    const records = readRobotRecords(resolved);
    const seen = new Set();
    const valid = [];
    const invalid = [];
    let duplicateCount = 0;
    for (const record of records) {
      const check = validateRobotRecord(record);
      if (!check.ok) {
        invalid.push({ creatorId: record?.creator?.id || "", reason: check.reason });
        continue;
      }
      const key = `${record.task.id}:${record.creator.id}`;
      if (seen.has(key)) {
        duplicateCount += 1;
        continue;
      }
      seen.add(key);
      valid.push(record);
    }
    const reportPath = path.join(
      path.dirname(resolved),
      `${path.basename(resolved, path.extname(resolved))}_机器人预演报告.json`,
    );
    const result = {
      mode: "dry-run",
      sourcePath: resolved,
      reportPath,
      contractVersion: "aipr.robot.outreach.v1",
      totalCount: records.length,
      validCount: valid.length,
      invalidCount: invalid.length,
      duplicateCount,
      actualSendCount: 0,
      canHandOff: valid.length > 0 && invalid.length === 0,
      invalid,
      checkedAt: new Date().toISOString(),
    };
    writeAtomic(reportPath, JSON.stringify(result, null, 2));
    return result;
  }
}

function readRobotRecords(target) {
  if (target.toLowerCase().endsWith(".ndjson")) {
    return fs.readFileSync(target, "utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
  }
  const payload = JSON.parse(fs.readFileSync(target, "utf8"));
  if (payload?.schemaVersion !== "aipr.robot.batch.v1" || !Array.isArray(payload.records)) {
    throw new Error("机器人批量包格式不正确");
  }
  return payload.records;
}

function validateRobotRecord(record) {
  if (record?.schemaVersion !== "aipr.robot.outreach.v1") return { ok: false, reason: "契约版本不匹配" };
  if (record?.event !== "creator.outreach.requested") return { ok: false, reason: "事件类型不匹配" };
  if (!record?.task?.id || !record?.creator?.id) return { ok: false, reason: "任务或达人身份缺失" };
  if (!record.creator.contact?.wechat && !record.creator.contact?.phone) return { ok: false, reason: "缺少微信或手机号" };
  return { ok: true };
}

function writeAtomic(target, contents) {
  const temp = `${target}.tmp`;
  fs.writeFileSync(temp, contents, "utf8");
  fs.renameSync(temp, target);
}

module.exports = { IntegrationAdapter };
