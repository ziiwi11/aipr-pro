const test = require("node:test");
const assert = require("node:assert/strict");
const { collectionEventStatus } = require("./collection-event-status.cjs");
test("retryable shop error keeps the live collection running", () => {
  assert.equal(collectionEventStatus({workerAction:"collect-creators",type:"error",status:"shop_error"},true),"running");
});
test("retry and resumed filter confirmation restore running display", () => {
  for (const status of ["collection_started","collection_retry_scheduled","platform_filters_confirmed"])
    assert.equal(collectionEventStatus({workerAction:"collect-creators",type:"progress",status},true),"running");
});
test("late events cannot reactivate a stopped worker", () => {
  assert.equal(collectionEventStatus({workerAction:"collect-creators",type:"error",status:"shop_error"},false),null);
});
test("fatal and explicit pause events retain terminal handling", () => {
  for (const payload of [{type:"error",status:"pipeline_error"},{type:"paused",status:"paused"},{type:"finished",code:1}])
    assert.equal(collectionEventStatus({workerAction:"collect-creators",...payload},true),null);
});
