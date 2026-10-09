const { spawnSync } = require("node:child_process");

const detachedDescendants=new WeakMap();
function terminateProcessTree(child, options = {}) {
  if (!child?.pid) return true;
  const platform = options.platform || process.platform;
  const runSync = options.runSync || spawnSync;
  if (platform === "win32") {
    const result = runSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { windowsHide: true });
    return result.status === 0;
  }
  // Python stages start independent sessions: the pipeline group alone cannot stop them.
  let descendants=detachedDescendants.get(child) || [];
  try {
    const result=runSync("ps",["-axo","pid=,ppid="],{encoding:"utf8",timeout:2000});
    if(result.status !== 0) return false;
    const rows=String(result.stdout || "").trim().split(/\n/).map(line=>line.trim().split(/\s+/).map(Number));
    const owned=new Set([child.pid,...descendants]);
    let changed=true;
    while(changed){changed=false;for(const [pid,ppid] of rows){if(owned.has(ppid)&&!owned.has(pid)){owned.add(pid);changed=true;}}}
    descendants=[...owned].filter(pid=>pid!==child.pid);
    detachedDescendants.set(child,descendants);
  } catch { return false; }
  for(const pid of descendants.reverse()) {
    try { process.kill(-pid,options.signal || "SIGTERM"); }
    catch { try { process.kill(pid,options.signal || "SIGTERM"); } catch {} }
  }
  try {
    process.kill(-child.pid, options.signal || "SIGTERM");
    return true;
  } catch {
    try {
      return child.kill(options.signal || "SIGTERM") !== false;
    } catch {
      return false;
    }
  }
}

module.exports = { terminateProcessTree };
