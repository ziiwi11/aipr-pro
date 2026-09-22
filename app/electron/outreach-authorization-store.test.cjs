const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { OutreachAuthorizationStore } = require("./outreach-authorization-store.cjs");

function fixtures() {
  return [
    { id: "a", name: "A", wechat: "wx_a", plainContact: "wx_a" },
    { id: "b", name: "B", plainContact: "" },
    { id: "c", name: "C", wechat: "WX_A", plainContact: "WX_A" },
    { id: "d", name: "D", phone: "13800138000", plainContact: "13800138000" },
  ];
}

test("授权预览排除缺失和重复联系方式且不会产生发送", () => {
  const baseDir = fs.mkdtempSync(path.join(os.tmpdir(), "aipr-auth-"));
  const store = new OutreachAuthorizationStore(baseDir);

  const preview = store.preview({ id: "task-1", name: "唇本" }, fixtures(), ["a", "b", "c"]);

  assert.equal(preview.selectedCount, 3);
  assert.equal(preview.validCount, 1);
  assert.equal(preview.missingCount, 1);
  assert.equal(preview.duplicateCount, 1);
  assert.equal(preview.actualSendCount, 0);
  assert.equal(preview.status, "previewed");
});

test("只有已预览批次可以授权且未授权批次不能标记同步", () => {
  const baseDir = fs.mkdtempSync(path.join(os.tmpdir(), "aipr-auth-"));
  const store = new OutreachAuthorizationStore(baseDir);
  assert.throws(() => store.authorize("missing-preview"), /预览/);
  assert.throws(() => store.markSynced("missing-batch", { queueId: "q-1" }), /授权/);

  const preview = store.preview({ id: "task-1", name: "唇本" }, fixtures(), ["d"]);
  const authorized = store.authorize(preview.previewId);
  const synced = store.markSynced(authorized.batchId, { queueId: "q-2" });

  assert.equal(authorized.status, "authorized");
  assert.equal(synced.status, "synced");
  assert.equal(store.list("task-1")[0].syncResult.queueId, "q-2");
});
