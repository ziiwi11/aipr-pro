const test = require("node:test");
const assert = require("node:assert/strict");

let isOutreachEligible;
let selectableCreators;
let previewSummary;
let canStartBatch;

test.before(async () => {
  ({ isOutreachEligible, selectableCreators, previewSummary, canStartBatch } = await import("../dist/aipr-ai-outreach.js"));
});

test("只有含微信或手机号的达人可被批量选择", () => {
  const creators = [
    { id: "a", wechat: "wx_a" },
    { id: "b", phone: "13800138000" },
    { id: "c", plainContact: "" },
    { id: "d", email: "only@example.test" },
  ];

  assert.equal(isOutreachEligible(creators[0]), true);
  assert.equal(isOutreachEligible(creators[2]), false);
  assert.deepEqual(selectableCreators(creators).map((item) => item.id), ["a", "b"]);
});

test("授权预览文案显示有效、缺失和重复数量", () => {
  assert.equal(previewSummary({ selectedCount: 8, validCount: 5, missingCount: 2, duplicateCount: 1 }), "已选 8 · 可同步 5 · 缺失 2 · 重复 1 · 当前发送 0");
});

test("只有同步完成并勾选二次确认的批次可启动", () => {
  assert.equal(canStartBatch({ status: "authorized" }, true), false);
  assert.equal(canStartBatch({ status: "synced" }, false), false);
  assert.equal(canStartBatch({ status: "synced" }, true), true);
});
