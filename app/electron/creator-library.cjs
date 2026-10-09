const {taskLineage}=require("./delivery-exclusions.cjs");
// Aggregate saved deliveries without changing the active collection task.
function buildCreatorLibrary(tasks, readSnapshot, readLive = () => null) {
  const records = new Map();
  const batches = [];
  const groups=new Map();
  for(const task of tasks){const lineage=taskLineage(task),prior=groups.get(lineage);if(!prior || task.id===lineage)groups.set(lineage,task);}
  for (const task of groups.values()) {
    const live = readLive(task);
    const rows = Array.isArray(live) ? live : readSnapshot(task.deliveryPath)?.creators || [];
    if (!rows.length) continue;
    batches.push({ id: task.id, name: task.name, count: rows.length, status: task.status || "idle" });
    for (const row of rows) {
      const identity = String(row.douyinId || row.id || '').trim().toLowerCase();
      const key = identity || `${task.id}:${row.id}`;
      const saved = records.get(key);
      records.set(key, {
        ...saved, ...row,
        wechat: row.wechat || saved?.wechat || '',
        phone: row.phone || saved?.phone || '',
        email: row.email || saved?.email || '',
        libraryTaskIds: [...new Set([...(saved?.libraryTaskIds || []), task.id])],
        libraryTaskNames: [...new Set([...(saved?.libraryTaskNames || []), task.name])],
      });
    }
  }
  return { creators: [...records.values()], batches };
}
module.exports = { buildCreatorLibrary };
