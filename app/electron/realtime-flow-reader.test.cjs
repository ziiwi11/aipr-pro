const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { readRealtimeCreatorFlow } = require("./realtime-flow-reader.cjs");

test("逐人流水线分离候选、合适、明文与正式名单", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "aipr-realtime-flow-"));
  fs.writeFileSync(path.join(directory, "aipr_realtime_creator_flow.json"), JSON.stringify({
    records: [
      { identity: "candidate", state: "discovered", row: { identity: "candidate" } },
      { identity: "suitable", state: "contact_revealing", row: { identity: "suitable" } },
      { identity: "listed", state: "listed", row: { identity: "listed", buyin_contact_wechat: "wx_listed_1" } },
      { identity: "masked", state: "listed", row: { identity: "masked", buyin_contact_phone: "138****0000" } },
    ],
  }));

  const result = readRealtimeCreatorFlow(directory);

  assert.equal(result.available, true);
  assert.equal(result.metrics.candidates, 4);
  assert.equal(result.metrics.suitable, 3);
  assert.equal(result.metrics.plaintext, 1);
  assert.equal(result.metrics.listed, 1);
  assert.deepEqual(result.formalRows.map((row) => row.identity), ["listed"]);
});

test("没有流水线文件时返回空快照", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "aipr-realtime-empty-"));
  const result = readRealtimeCreatorFlow(directory);
  assert.equal(result.available, false);
  assert.equal(result.metrics.listed, 0);
});
