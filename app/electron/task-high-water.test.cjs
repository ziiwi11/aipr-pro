const test = require('node:test');
const assert = require('node:assert/strict');
const { normalizeDelivery } = require('./delivery-normalizer.cjs');
const { mergeTaskDeliverySnapshot } = require('./task-high-water.cjs');

test('cached completed delivery preserves an expanded task target and remaining work across refreshes', () => {
  const saved = { targetCount: 1000, plainContacts: 500, wechat: 474, phone: 358, remaining: 500 };
  const snapshot = normalizeDelivery({ target_count: 500, plain_contact_count: 500,
    wechat_contact_count: 474, phone_contact_count: 358, pending_contact_count: 0, rows: [] });
  const refreshed = mergeTaskDeliverySnapshot(saved, snapshot.metrics, { preserveTarget: true });
  assert.equal(refreshed.targetCount, 1000);
  assert.equal(refreshed.remaining, 500);
  assert.equal(refreshed.plainContacts, 500);
  assert.equal(refreshed.wechat, 474);
  assert.deepEqual(mergeTaskDeliverySnapshot(refreshed, snapshot.metrics, { preserveTarget: true }), refreshed);
});

test('cached delivery keeps a completed task completed when its target is unchanged', () => {
  const refreshed = mergeTaskDeliverySnapshot({ targetCount: 500, plainContacts: 500 },
    { targetCount: 500, plainContacts: 500, remaining: 0 }, { preserveTarget: true });
  assert.equal(refreshed.targetCount, 500);
  assert.equal(refreshed.remaining, 0);
});

test('explicit delivery import still adopts the imported target and exact contact counts', () => {
  const imported = mergeTaskDeliverySnapshot({ targetCount: 1000, plainContacts: 600 },
    { targetCount: 200, plainContacts: 200, wechat: 180, phone: 171, remaining: 0 });
  assert.equal(imported.targetCount, 200);
  assert.equal(imported.plainContacts, 200);
  assert.equal(imported.remaining, 0);
});
