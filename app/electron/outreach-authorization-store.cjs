const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

class OutreachAuthorizationStore {
  constructor(baseDir) {
    this.dir = path.join(baseDir, "outreach-authorizations");
    fs.mkdirSync(this.dir, { recursive: true });
  }

  preview(task = {}, creators = [], selectedIds = []) {
    const selected = new Set((selectedIds || []).map(String));
    const rows = creators.filter((creator) => selected.has(String(creator.id)));
    const seenContacts = new Set();
    const valid = [];
    const missing = [];
    const duplicate = [];
    for (const creator of rows) {
      const contact = creatorContact(creator);
      if (!contact.value) {
        missing.push({ id: creator.id, name: creator.name || "" });
        continue;
      }
      const contactValues = creatorContactValues(creator);
      if (contactValues.some(value => seenContacts.has(value))) {
        duplicate.push({ id: creator.id, name: creator.name || "", contactType: contact.type });
        continue;
      }
      for (const value of contactValues) seenContacts.add(value);
      valid.push({
        id: String(creator.id),
        name: String(creator.name || ""),
        douyin: String(creator.douyin || ""),
        contactType: contact.type,
        contactValue: contact.value,
      });
    }
    const previewId = crypto.randomUUID();
    const record = {
      schemaVersion: "aipr.leishen.authorization.v1",
      previewId,
      batchId: previewId,
      task: { id: String(task.id || ""), name: String(task.name || "") },
      status: "previewed",
      selectedCount: rows.length,
      validCount: valid.length,
      missingCount: missing.length,
      duplicateCount: duplicate.length,
      actualSendCount: 0,
      valid,
      missing,
      duplicate,
      previewedAt: new Date().toISOString(),
    };
    this.write(record);
    return publicRecord(record);
  }

  authorize(previewId) {
    const record = this.read(previewId);
    if (!record || record.status !== "previewed") throw new Error("授权前必须先生成有效预览");
    if (!record.validCount) throw new Error("预览中没有可授权达人");
    const next = { ...record, status: "authorized", authorizedAt: new Date().toISOString() };
    this.write(next);
    return publicRecord(next);
  }

  markSynced(batchId, syncResult = {}) {
    const record = this.read(batchId);
    if (!record || !["authorized", "synced"].includes(record.status)) throw new Error("批次尚未授权，不能标记同步");
    const next = { ...record, status: "synced", syncedAt: new Date().toISOString(), syncResult };
    this.write(next);
    return publicRecord(next);
  }

  markStarted(batchId, startResult = {}) {
    const record = this.read(batchId);
    if (!record || !["synced", "running"].includes(record.status)) throw new Error("批次尚未同步，不能开始 AI 建联");
    const next = { ...record, status: "running", startedAt: new Date().toISOString(), startResult };
    this.write(next);
    return publicRecord(next);
  }

  get(batchId, { includeContacts = false } = {}) {
    const record = this.read(batchId);
    return includeContacts ? record : publicRecord(record);
  }

  list(taskId) {
    return fs.readdirSync(this.dir).filter((name) => name.endsWith(".json")).map((name) => {
      try { return JSON.parse(fs.readFileSync(path.join(this.dir, name), "utf8")); } catch { return null; }
    }).filter((item) => item?.task?.id === taskId).sort((a, b) => String(b.previewedAt).localeCompare(String(a.previewedAt))).map(publicRecord);
  }

  fileFor(id) {
    return path.join(this.dir, `${safeId(id)}.json`);
  }

  read(id) {
    const target = this.fileFor(id);
    if (!fs.existsSync(target)) return null;
    return JSON.parse(fs.readFileSync(target, "utf8"));
  }

  write(record) {
    const target = this.fileFor(record.batchId || record.previewId);
    const temp = `${target}.tmp`;
    fs.writeFileSync(temp, JSON.stringify(record, null, 2), "utf8");
    fs.renameSync(temp, target);
  }
}

function creatorContact(creator = {}) {
  const candidates = [
    ["wechat", creator.wechat],
    ["phone", creator.phone],
    ["contact", creator.plainContact],
  ];
  for (const [type, raw] of candidates) {
    const value = String(raw || "").trim();
    if (value && !/[*•]|隐藏|未授权|待补|暂无|不可见/u.test(value)) return { type, value, normalized: normalizeContact(type, value) };
  }
  return { type: "", value: "", normalized: "" };
}

function normalizeContact(type, value) {
  const text = String(value || "").trim().toLowerCase().replace(/\s+/g, "");
  const phoneText = type === "phone" ? text.replace(/-/g, "") : text;
  const phone = phoneText.match(/^(?:\+?86)?(1[3-9]\d{9})$/);
  if (phone) return phone[1];
  return type === "phone" ? text.replace(/-/g, "") : text;
}

function creatorContactValues(creator) {
  return ["wechat", "phone", "plainContact"].flatMap(key => {
    const value = String(creator[key] || "").trim();
    return value && !/[*•]|隐藏|未授权|待补|暂无|不可见/u.test(value)
      ? [normalizeContact(key === "plainContact" ? "contact" : key, value)] : [];
  });
}

function publicRecord(record) {
  if (!record) return null;
  const { valid = [], ...rest } = record;
  return {
    ...rest,
    valid: valid.map(({ contactValue, ...item }) => ({ ...item, contactMasked: maskContact(contactValue) })),
  };
}

function maskContact(value) {
  const text = String(value || "");
  if (text.length <= 4) return "****";
  return `${text.slice(0, 2)}***${text.slice(-2)}`;
}

function safeId(value) {
  return String(value || "batch").replace(/[^a-zA-Z0-9_-]/g, "-") || "batch";
}

module.exports = { OutreachAuthorizationStore, creatorContact };
