const { test } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { resolveUserDataPath } = require("./product-identity.cjs");
test("renaming preserves existing user data and session storage", () => {
 assert.equal(resolveUserDataPath("/tmp/appdata"), path.join("/tmp/appdata", "AIPR Pro 达人运营系统"));
 assert.equal(resolveUserDataPath("/tmp/appdata", "/tmp/isolated"), "/tmp/isolated");
});
