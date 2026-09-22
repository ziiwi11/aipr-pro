const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { RunHistoryStore } = require("./run-history-store.cjs");

test("运行历史跨实例持久化并忽略损坏行", () => {
  const baseDir = fs.mkdtempSync(path.join(os.tmpdir(), "aipr-history-"));
  const first = new RunHistoryStore(baseDir);
  first.append("task-1", { type: "started", status: "running" });
  first.append("task-1", { type: "finished", code: 0 });
  fs.appendFileSync(first.fileFor("task-1"), "{broken json}\n", "utf8");

  const second = new RunHistoryStore(baseDir);
  const events = second.list("task-1", 1);

  assert.equal(events.length, 1);
  assert.equal(events[0].type, "finished");
  assert.equal(events[0].taskId, "task-1");
});

test("从任务目录恢复的历史只包含文件摘要", () => {
  const baseDir = fs.mkdtempSync(path.join(os.tmpdir(), "aipr-history-"));
  const taskDir = path.join(baseDir, "task-data");
  fs.mkdirSync(taskDir);
  fs.writeFileSync(path.join(taskDir, "aipr_replenishment_collection_highwater.json"), '{"rows":[{"微信":"secret"}]}');
  fs.writeFileSync(path.join(taskDir, "collection-strategy.json"), "{}");
  const store = new RunHistoryStore(baseDir);

  const recovered = store.recover("task-2", taskDir);

  assert.equal(recovered.length, 2);
  assert.equal(JSON.stringify(recovered).includes("secret"), false);
  assert.match(recovered[0].artifact, /\.json$/);
});
