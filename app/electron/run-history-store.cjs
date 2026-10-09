const {summarizeRuntime}=require("./runtime-metrics.cjs");
const {readCachedNdjson}=require("./cached-file.cjs");
const fs = require("node:fs");
const path = require("node:path");

class RunHistoryStore {
  constructor(baseDir) {
    this.dir = path.join(baseDir, "history");
    fs.mkdirSync(this.dir, { recursive: true });
  }

  fileFor(taskId) {
    return path.join(this.dir, safeId(taskId), "events.ndjson");
  }

  append(taskId, event = {}) {
    const target = this.fileFor(taskId);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    const record = {
      ...sanitizeEvent(event),
      taskId: String(taskId || ""),
      recordedAt: event.recordedAt || new Date().toISOString(),
    };
    fs.appendFileSync(target, `${JSON.stringify(record)}\n`, "utf8");
    return record;
  }

  list(taskId, limit = 50) {
    const target = this.fileFor(taskId);
    if (!fs.existsSync(target)) return [];
    const records=readCachedNdjson(target);
    return records.slice(-Math.max(1, Number(limit) || 50)).reverse().map(record=>({...record}));
  }

  timing(taskId,liveSession="",currentFormal) {
    const target=this.fileFor(taskId);return summarizeRuntime(fs.existsSync(target)?readCachedNdjson(target):[],Date.now(),liveSession,currentFormal);
  }

  recover(taskId, taskDir) {
    if (!taskDir || !fs.existsSync(taskDir)) return [];
    const names = fs.readdirSync(taskDir).filter((name) =>
      /(?:highwater|checkpoint|collection-strategy|交付清单).*\.json$/iu.test(name),
    );
    const known = new Set(this.list(taskId, 500).filter((item) => item.type === "recovered-artifact").map((item) => item.artifact));
    const recovered = [];
    for (const name of names.sort()) {
      if (known.has(name)) continue;
      const stat = fs.statSync(path.join(taskDir, name));
      recovered.push(this.append(taskId, {
        type: "recovered-artifact",
        status: /highwater|checkpoint/iu.test(name) ? "checkpoint" : "artifact",
        artifact: name,
        artifactModifiedAt: stat.mtime.toISOString(),
      }));
    }
    return recovered;
  }
}

function sanitizeEvent(event) {
  const allowed = [
    "workerAction","workerSession","timingVersion","listedBaseline","listed_count","wait_ms","backoff_ms",
    "type", "status", "message", "code", "candidate_count", "processed", "plain_contact_count",
    "qualified_plain_contact_count", "output", "artifact", "artifactModifiedAt", "batchId", "queueId",
  ];
  return Object.fromEntries(allowed.filter((key) => event[key] !== undefined).map((key) => [key, event[key]]));
}

function safeId(value) {
  return String(value || "task").replace(/[^a-zA-Z0-9_-]/g, "-") || "task";
}

module.exports = { RunHistoryStore };
