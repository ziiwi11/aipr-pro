const fs = require("node:fs");
const path = require("node:path");

class TaskStore {
  constructor(userDataDir) {
    this.dir = path.join(userDataDir, "tasks");
    this.file = path.join(this.dir, "tasks.json");
    fs.mkdirSync(this.dir, { recursive: true });
  }

  read() {
    if (!fs.existsSync(this.file)) return { currentTaskId: "", tasks: [] };
    try {
      const parsed = JSON.parse(fs.readFileSync(this.file, "utf8"));
      return {
        currentTaskId: String(parsed?.currentTaskId || ""),
        tasks: Array.isArray(parsed?.tasks)
          ? parsed.tasks.filter((task) => task && typeof task === "object")
          : [],
      };
    } catch {
      return { currentTaskId: "", tasks: [] };
    }
  }

  write(state) {
    const temp = `${this.file}.tmp`;
    fs.writeFileSync(temp, JSON.stringify(state, null, 2), "utf8");
    fs.renameSync(temp, this.file);
    return state;
  }

  upsert(task) {
    const state = this.read();
    const index = state.tasks.findIndex((item) => item.id === task.id);
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
