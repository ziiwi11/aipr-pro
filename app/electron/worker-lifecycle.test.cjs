const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { stopWorker, taskWorkerStatus, collectionWorkerRunning } = require('./worker-lifecycle.cjs');
test('pause waits for process close before permitting a restart', async () => {
  const child = new EventEmitter(); child.pid = 123;
  let settled = false;
  const pause = stopWorker(child, { terminate: () => true }).then(result => { settled = true; return result; });
  await Promise.resolve();
  assert.equal(settled, false);
  child.emit('close', null);
  assert.equal(await pause, true);
});
test('failure to stop is reported rather than claiming successful pause', async () => {
  const child = new EventEmitter(); child.pid = 123;
  assert.equal(await stopWorker(child, { terminate: () => false }), false);
  assert.equal(child.listenerCount('close'), 0);
});
test('unresponsive worker is force stopped after grace period', async () => {
  const child = new EventEmitter(); child.pid = 123;
  const signals = [];
  const result = await stopWorker(child, { timeoutMs: 5, terminate: (_child, options) => {
    signals.push(options?.signal || 'SIGTERM');
    if (options?.signal === 'SIGKILL') child.emit('close', null);
    return true;
  }});
  assert.equal(result, true);
  assert.deepEqual(signals, ['SIGTERM', 'SIGKILL']);
});
test('exited parent still waits for inherited pipes and children to close', async () => {
  const child = new EventEmitter(); child.pid = 123; child.exitCode = 0;
  let settled = false;
  const pause = stopWorker(child, { terminate: () => true }).then(result => { settled = true; return result; });
  await Promise.resolve(); assert.equal(settled, false);
  child.emit('close', 0); assert.equal(await pause, true);
});

test('restored running task is paused when its worker is absent', () => {
  assert.equal(taskWorkerStatus({ id: 'brand-a', status: 'running' }, null, ''), 'paused');
});
test('a worker from another task cannot make a stopped task appear running', () => {
  assert.equal(taskWorkerStatus({ id: 'brand-a', status: 'running' }, {}, 'brand-b'), 'paused');
});
test('live task status and completed or failed outcomes are preserved', () => {
  assert.equal(taskWorkerStatus({ id: 'brand-a', status: 'running' }, {}, 'brand-a'), 'running');
  for (const status of ['completed', 'failed', 'paused', 'idle']) {
    assert.equal(taskWorkerStatus({ id: 'brand-a', status }, null, ''), status);
  }
});
test('login probes and workbook exports never advertise live collection', () => {
  const task = { id: 'brand-a', status: 'completed' };
  for (const action of ['probe-login', 'export-original', '', undefined]) {
    assert.equal(collectionWorkerRunning(task, {}, 'brand-a', action), false);
  }
  for (const action of ['collect-creators', 'contact-icons']) {
    assert.equal(collectionWorkerRunning(task, {}, 'brand-a', action), true);
    assert.equal(collectionWorkerRunning(task, null, 'brand-a', action), false);
    assert.equal(collectionWorkerRunning(task, {}, 'brand-b', action), false);
  }
});
