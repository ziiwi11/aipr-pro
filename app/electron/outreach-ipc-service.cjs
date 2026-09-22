class OutreachIpcService {
  constructor({ history, authorizations, leishen }) {
    this.history = history;
    this.authorizations = authorizations;
    this.leishen = leishen;
  }

  preview(task, creators, selectedIds) {
    const result = this.authorizations.preview(task, creators, selectedIds);
    this.history.append(task.id, {
      type: "outreach-previewed",
      status: "previewed",
      batchId: result.batchId,
      candidate_count: result.validCount,
      message: `选择 ${result.selectedCount}，可同步 ${result.validCount}，缺失 ${result.missingCount}，重复 ${result.duplicateCount}`,
    });
    return result;
  }

  authorize(previewId) {
    const batch = this.authorizations.authorize(previewId);
    this.history.append(batch.task.id, {
      type: "outreach-authorized",
      status: "authorized",
      batchId: batch.batchId,
      candidate_count: batch.validCount,
    });
    return batch;
  }

  async sync(batchId) {
    const batch = this.authorizations.get(batchId, { includeContacts: true });
    if (!batch || batch.status !== "authorized") throw new Error("批次尚未授权，不能同步到雷神");
    const result = await this.leishen.syncAuthorizedBatch(batch);
    const synced = this.authorizations.markSynced(batchId, result.result || result);
    this.history.append(batch.task.id, {
      type: "leishen-synced",
      status: "synced",
      batchId,
      queueId: result?.result?.queueId || "",
      candidate_count: batch.validCount,
    });
    return { ok: true, batch: synced, result };
  }

  async start(batchId, confirmation = {}) {
    if (confirmation.explicitUiClick !== true) throw new Error("开始 AI 建联前必须二次确认");
    const batch = this.authorizations.get(batchId, { includeContacts: true });
    if (!batch || batch.status !== "synced") throw new Error("批次尚未同步，不能开始 AI 建联");
    const result = await this.leishen.startAuthorizedBatch(batchId, confirmation);
    const running = this.authorizations.markStarted(batchId, result.result || result);
    this.history.append(batch.task.id, {
      type: "leishen-started",
      status: "running",
      batchId,
      candidate_count: batch.validCount,
    });
    return { ok: true, batch: running, result };
  }

  async getState(task = {}, taskDir = "") {
    if (taskDir) this.history.recover(task.id, taskDir);
    const [status, permissions, projects] = await Promise.all([
      this.leishen.getStatus(),
      this.leishen.getPermissions(),
      this.leishen.getProjects(),
    ]);
    return {
      taskId: task.id,
      leishen: { status, permissions, projects },
      batches: this.authorizations.list(task.id),
      history: this.history.list(task.id, 100),
    };
  }

  getHistory(taskId, limit = 100) {
    return this.history.list(taskId, limit);
  }
}

module.exports = { OutreachIpcService };
