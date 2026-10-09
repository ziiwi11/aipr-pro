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

test("正式名单和计数以审计结果为准，不能采用历史 listed 状态", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "aipr-realtime-audited-"));
  fs.writeFileSync(path.join(directory, "aipr_realtime_creator_flow.json"), JSON.stringify({
    records: ["approved", "pending"].map((identity) => ({identity, state: "listed",
      row: {identity, buyin_contact_wechat: `wx_${identity}`}})),
  }));
  fs.writeFileSync(path.join(directory, "aipr_strict_contact_highwater.json"), JSON.stringify({
    candidates: [{identity: "approved", buyin_contact_wechat: "wx_approved"}],
  }));
  const result = readRealtimeCreatorFlow(directory);
  assert.equal(result.metrics.candidates, 2);
  assert.equal(result.metrics.listed, 1);
  assert.deepEqual(result.formalRows.map((row) => row.identity), ["approved"]);
  fs.writeFileSync(path.join(directory, "aipr_strict_contact_highwater.json"), '{broken');
  assert.equal(readRealtimeCreatorFlow(directory).metrics.listed, 0);
});


test("实时联系方式分类以正式名单为准，排除掩码与未入库数据", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "aipr-live-contact-count-"));
  fs.writeFileSync(path.join(directory, "aipr_realtime_creator_flow.json"), JSON.stringify({records: [
    {identity: "a", state: "listed", row: {buyin_contact_wechat: "wx_a", buyin_contact_phone: "13812345678"}},
    {identity: "b", state: "listed", row: {cart_contact_wechat: "wx_b", cart_contact_phone: "138****0000"}},
    {identity: "c", state: "duplicate_contact", row: {buyin_contact_wechat: "wx_a"}},
  ]}));
  const result = readRealtimeCreatorFlow(directory);
  assert.equal(result.metrics.listed, 2);
  assert.equal(result.metrics.wechat, 2);
  assert.equal(result.metrics.phone, 1);
});
