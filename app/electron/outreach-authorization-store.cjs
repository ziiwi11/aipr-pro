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
      if (seenContacts.has(contact.normalized)) {
        duplicate.push({ id: creator.id, name: creator.name || "", contactType: contact.type });
        continue;
      }
      seenContacts.add(contact.normalized);
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
    if (value) return { type, value, normalized: value.toLowerCase().replace(/[\s-]+/g, "") };
  }
  return { type: "", value: "", normalized: "" };
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
