const { terminateProcessTree } = require('./process-tree.cjs');
// Do not advertise a stopped task before its process and inherited pipes close.
function stopWorker(child, { terminate = terminateProcessTree, timeoutMs = 5000 } = {}) {
  if (!child) return Promise.resolve(true);
  return new Promise(resolve => {
    const timers = [];
    let done = false;
    const finish = result => {
      if (done) return;
      done = true;
      for (const timer of timers) clearTimeout(timer);
      child.removeListener('close', onClose);
      resolve(result);
    };
    const onClose = () => finish(true);
    child.once('close', onClose);
    if (!terminate(child)) { finish(false); return; }
    if (done) return;
    timers.push(setTimeout(() => {
      if (!terminate(child, { signal: 'SIGKILL' })) { finish(false); return; }
      if (!done) timers.push(setTimeout(() => finish(false), 1000));
    }, timeoutMs));
  });
}
function taskWorkerStatus(task, child, workerTaskId) {
  const ownsWorker = Boolean(child && workerTaskId === task.id);
  return task.status === 'running' && !ownsWorker ? 'paused' : task.status;
}
function collectionWorkerRunning(task, child, workerTaskId, action) {
  return Boolean(child && workerTaskId === task.id
    && ['collect-creators', 'contact-icons'].includes(action));
}
module.exports = { stopWorker, taskWorkerStatus, collectionWorkerRunning };
