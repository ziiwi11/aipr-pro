const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { RunHistoryStore } = require("./run-history-store.cjs");
const { OutreachAuthorizationStore } = require("./outreach-authorization-store.cjs");
const { OutreachIpcService } = require("./outreach-ipc-service.cjs");

function setup() {
  const baseDir = fs.mkdtempSync(path.join(os.tmpdir(), "aipr-outreach-service-"));
  const calls = { sync: 0, start: 0 };
  const leishen = {
    getStatus: async () => ({ online: true, ok: true, result: { state: "idle" } }),
    getPermissions: async () => ({ online: true, ok: true, result: { accessibility: true } }),
    getProjects: async () => ({ online: true, ok: true, projects: [{ id: "brand-referral", ready: true }] }),
    syncAuthorizedBatch: async (batch) => { calls.sync += 1; return { ok: true, result: { queueId: `q-${batch.batchId}` } }; },
    startAuthorizedBatch: async (_batchId, confirmation) => {
      if (confirmation.explicitUiClick !== true) throw new Error("需要明确点击");
      calls.start += 1;
      return { ok: true, result: { state: "running" } };
    },
  };
  const history = new RunHistoryStore(baseDir);
  const authorizations = new OutreachAuthorizationStore(baseDir);
  const service = new OutreachIpcService({ history, authorizations, leishen });
  return { service, calls };
}

test("未授权批次不能同步且同步不会自动启动", async () => {
  const { service, calls } = setup();
  const preview = service.preview(
    { id: "task-1", name: "唇本" },
    [{ id: "a", name: "达人A", wechat: "wx_a", plainContact: "wx_a" }],
    ["a"],
  );

  await assert.rejects(() => service.sync(preview.batchId), /授权/);
  service.authorize(preview.previewId);
  const synced = await service.sync(preview.batchId);

  assert.equal(synced.batch.status, "synced");
  assert.equal(calls.sync, 1);
  assert.equal(calls.start, 0);
});

test("启动要求二次确认并写入运行历史", async () => {
  const { service, calls } = setup();
  const preview = service.preview(
    { id: "task-2", name: "唇本" },
    [{ id: "a", name: "达人A", phone: "13800138000", plainContact: "13800138000" }],
    ["a"],
  );
  service.authorize(preview.previewId);
  await service.sync(preview.batchId);

  await assert.rejects(() => service.start(preview.batchId, { explicitUiClick: false }), /确认/);
  assert.equal(calls.start, 0);
  const started = await service.start(preview.batchId, { explicitUiClick: true });
  const state = await service.getState({ id: "task-2" });

  assert.equal(started.batch.status, "running");
  assert.equal(calls.start, 1);
  assert.equal(state.history.some((event) => event.type === "leishen-started"), true);
});

test("状态接口合并雷神健康、权限、项目和批次", async () => {
  const { service } = setup();
  const state = await service.getState({ id: "task-3" });

  assert.equal(state.leishen.status.online, true);
  assert.equal(state.leishen.permissions.result.accessibility, true);
  assert.equal(state.leishen.projects.projects[0].id, "brand-referral");
  assert.deepEqual(state.batches, []);
});
