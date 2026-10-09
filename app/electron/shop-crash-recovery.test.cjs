const { test } = require("node:test");
const assert = require("node:assert/strict");
const { createShopCrashRecovery } = require("./shop-crash-recovery.cjs");
test("crash reloads original profile on the same logged in contents", async () => {
  const url = "https://buyin.jinritemai.com/dashboard/servicehall/daren-profile?uid=test";
  const loads = [], events = [];
  const contents = { isDestroyed: () => false, getURL: () => url, loadURL: async (target) => loads.push(target) };
  const recover = createShopCrashRecovery(contents, { emit: (...args) => events.push(args) });
  assert.equal(await recover({ reason: "crashed" }), true);
  assert.deepEqual(loads, [url]);
  assert.equal(events.at(-1)[0], "recovered");
});
test("repeated renderer crashes have a bounded recovery window", async () => {
  let clock = 0, loads = 0;
  const recover = createShopCrashRecovery({ isDestroyed: () => false, getURL: () => "https://buyin.jinritemai.com/", loadURL: async () => loads++ }, { now: () => clock });
  for (let i = 0; i < 3; i++) assert.equal(await recover({ reason: "crashed" }), true);
  assert.equal(await recover({ reason: "crashed" }), false);
  assert.equal(loads, 3);
  clock = 600001;
  assert.equal(await recover({ reason: "crashed" }), true);
});
test("clean exit and destroyed contents do not reload", async () => {
  let loads = 0;
  const contents = { isDestroyed: () => false, getURL: () => "", loadURL: async () => loads++ };
  assert.equal(await createShopCrashRecovery(contents)({ reason: "clean-exit" }), false);
  contents.isDestroyed = () => true;
  assert.equal(await createShopCrashRecovery(contents)({ reason: "crashed" }), false);
  assert.equal(loads, 0);
});
