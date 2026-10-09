const fs = require("node:fs");
const path = require("node:path");

class TaskStore {
  constructor(userDataDir) {
    this.dir = path.join(userDataDir, "tasks");
    this.file = path.join(this.dir, "tasks.json");
    this.backupFile = `${this.file}.bak`;
    fs.mkdirSync(this.dir, { recursive: true });
  }

  read() {
    for (const file of [this.file, this.backupFile]) {
      if (!fs.existsSync(file)) continue;
      try {
      const parsed = JSON.parse(fs.readFileSync(file, "utf8"));
      if (!Array.isArray(parsed?.tasks)) throw new Error("Invalid task store");
      return {
        currentTaskId: String(parsed?.currentTaskId || ""),
        tasks: Array.isArray(parsed?.tasks)
          ? parsed.tasks.filter((task) => task && typeof task === "object")
          : [],
      };
      } catch {}
    }
    if (fs.existsSync(this.file) || fs.existsSync(this.backupFile)) {
      throw new Error("任务数据无法读取，备份也不可用。请恢复数据备份；现有文件已保留。");
    }
    return { currentTaskId: "", tasks: [] };
  }

  write(state) {
    if (!state || !Array.isArray(state.tasks)) {
      throw new Error("任务保存数据无效，现有文件已保留。");
    }
    const temp = `${this.file}.tmp`;
    // Flush complete snapshots before replacing either durable file.
    const flush = file => {
      const fd = fs.openSync(file, "r+");
      try { fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    };
    try {
      fs.writeFileSync(temp, JSON.stringify(state, null, 2), { encoding: "utf8", mode: 0o600 });
      flush(temp);
      let previousValid = false;
      if (fs.existsSync(this.file)) {
        try {
          previousValid = Array.isArray(JSON.parse(fs.readFileSync(this.file, "utf8"))?.tasks);
        } catch {}
      }
      // Backup I/O failures must abort the save, rather than silently discard recovery.
      if (previousValid) {
        fs.copyFileSync(this.file, `${this.backupFile}.tmp`);
        flush(`${this.backupFile}.tmp`);
        fs.renameSync(`${this.backupFile}.tmp`, this.backupFile);
      } else if (!fs.existsSync(this.backupFile)) {
        fs.copyFileSync(temp, `${this.backupFile}.tmp`);
        flush(`${this.backupFile}.tmp`);
        fs.renameSync(`${this.backupFile}.tmp`, this.backupFile);
      }
      fs.renameSync(temp, this.file);
    } finally {
      for (const pending of [temp, `${this.backupFile}.tmp`]) {
        try { fs.unlinkSync(pending); } catch {}
      }
    }
    return state;
  }

  upsert(task) {
    const state = this.read();
    const index = state.tasks.findIndex((item) => item.id === task.id);
    const previous = index >= 0 ? state.tasks[index] : null;
    const comparable = value => {
      const { updatedAt, ...fields } = value || {};
      return JSON.stringify(Object.fromEntries(Object.entries(fields).sort(([a], [b]) => a.localeCompare(b))));
    };
    if (previous && state.currentTaskId === task.id && comparable(previous) === comparable(task)) return previous;
    const next = { ...task, updatedAt: new Date().toISOString() };
    if (index >= 0) state.tasks[index] = next;
    else state.tasks.push(next);
    state.currentTaskId = next.id;
    this.write(state);
    return next;
  }

  list() {
    return [...this.read().tasks];
  }

  current() {
    const state = this.read();
    return (
      state.tasks.find((task) => task.id === state.currentTaskId) ||
      state.tasks[0] ||
      null
    );
  }

  create(task) {
    const state = this.read();
    const requestedId = String(task?.id || "task")
      .trim()
      .replace(/[^a-zA-Z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "");
    const baseId = requestedId || "task";
    let id = baseId;
    let suffix = 2;

    while (state.tasks.some((item) => item.id === id)) {
      id = `${baseId}-${suffix}`;
      suffix += 1;
    }

    const now = new Date().toISOString();
    const next = {
      ...task,
      id,
      createdAt: task?.createdAt || now,
      updatedAt: now,
    };
    state.tasks.push(next);
    state.currentTaskId = id;
    this.write(state);
    return next;
  }

  select(id) {
    const state = this.read();
    const task = state.tasks.find((item) => item.id === id);
    if (!task) throw new Error(`Task not found: ${id}`);
    state.currentTaskId = id;
    this.write(state);
    return task;
  }
}

module.exports = { TaskStore };
