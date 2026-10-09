const path = require("node:path");
function resolveUserDataPath(appData, override) {
  return override ? path.resolve(override) : path.join(appData, "AIPR Pro 达人运营系统");
}
module.exports = { resolveUserDataPath };
