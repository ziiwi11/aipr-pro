const { spawnSync } = require("node:child_process");

function terminateProcessTree(child, options = {}) {
  if (!child?.pid) return true;
  const platform = options.platform || process.platform;
  const runSync = options.runSync || spawnSync;
  if (platform === "win32") {
    const result = runSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { windowsHide: true });
    return result.status === 0;
  }
  try {
    process.kill(-child.pid, "SIGTERM");
    return true;
  } catch {
    try {
      child.kill("SIGTERM");
      return true;
    } catch {
      return false;
    }
  }
}

module.exports = { terminateProcessTree };
