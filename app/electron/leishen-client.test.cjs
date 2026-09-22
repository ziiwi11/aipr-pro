const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");

const { LeiShenClient } = require("./leishen-client.cjs");

async function withServer(handler, run) {
  const server = http.createServer(handler);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const address = server.address();
    await run(`http://127.0.0.1:${address.port}`);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

test("读取雷神状态并在离线时返回结构化结果", async () => {
  await withServer((request, response) => {
    assert.equal(request.url, "/api/automation/status");
    response.setHeader("content-type", "application/json");
    response.end(JSON.stringify({ ok: true, result: { state: "idle" } }));
  }, async (baseUrl) => {
    const client = new LeiShenClient({ baseUrl, projectId: "brand-referral" });
    const online = await client.getStatus();
    assert.equal(online.online, true);
    assert.equal(online.result.state, "idle");
  });

  const offlineClient = new LeiShenClient({ baseUrl: "http://127.0.0.1:1", projectId: "brand-referral", timeoutMs: 100 });
  const offline = await offlineClient.getStatus();
  assert.equal(offline.online, false);
  assert.match(offline.error, /ECONNREFUSED|连接|socket/i);
});

test("拒绝非回环雷神地址", () => {
  assert.throws(() => new LeiShenClient({ baseUrl: "http://192.168.1.10:19627" }), /127\.0\.0\.1/);
});

test("自动选择包含就绪 brand-referral 项目的最新雷神端口", async () => {
  const first = http.createServer((request, response) => {
    response.setHeader("content-type", "application/json");
    response.end(JSON.stringify({ ok: true, result: request.url === "/api/projects" ? { projects: [] } : { state: "old" } }));
  });
  const second = http.createServer((request, response) => {
    response.setHeader("content-type", "application/json");
    response.end(JSON.stringify({
      ok: true,
      result: request.url === "/api/projects" ? { projects: [{ id: "brand-referral", ready: true }] } : { state: "latest" },
    }));
  });
  await new Promise((resolve) => first.listen(0, "127.0.0.1", resolve));
  await new Promise((resolve) => second.listen(0, "127.0.0.1", resolve));
  try {
    const urls = [first, second].map((server) => `http://127.0.0.1:${server.address().port}`);
    const client = new LeiShenClient({ baseUrls: urls, projectId: "brand-referral" });
    const status = await client.getStatus();
    assert.equal(status.online, true);
    assert.equal(status.result.state, "latest");
    assert.equal(status.baseUrl, urls[1]);
  } finally {
    await new Promise((resolve) => first.close(resolve));
    await new Promise((resolve) => second.close(resolve));
  }
});

test("授权批次按雷神契约同步但不会自动启动", async () => {
  const calls = [];
  await withServer(async (request, response) => {
    let body = "";
    for await (const chunk of request) body += chunk;
    calls.push({ url: request.url, body: body ? JSON.parse(body) : {} });
    response.setHeader("content-type", "application/json");
    response.end(JSON.stringify({ ok: true, result: { exactMatch: true } }));
  }, async (baseUrl) => {
    const client = new LeiShenClient({ baseUrl, projectId: "brand-referral" });
    const result = await client.syncAuthorizedBatch({
      batchId: "batch-1",
      status: "authorized",
      task: { name: "唇本" },
      valid: [{ name: "达人A", contactType: "wechat", contactValue: "wx_a" }],
    });
    assert.equal(result.ok, true);
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/automation/queue/sync");
  assert.equal(calls[0].body.confirmed, true);
  assert.equal(calls[0].body.authorizationSource, "explicit_ui_click");
  assert.equal(calls[0].body.projectId, "brand-referral");
  assert.match(calls[0].body.filename, /\.csv$/);
  assert.match(calls[0].body.content, /wechat,note,project,brand/);
  assert.match(calls[0].body.content, /wx_a/);
});

test("显式启动要求当次界面确认", async () => {
  let called = false;
  await withServer((_request, response) => {
    called = true;
    response.setHeader("content-type", "application/json");
    response.end(JSON.stringify({ ok: true }));
  }, async (baseUrl) => {
    const client = new LeiShenClient({ baseUrl, projectId: "brand-referral" });
    await assert.rejects(() => client.startAuthorizedBatch("batch-1", { explicitUiClick: false }), /明确点击/);
  });
  assert.equal(called, false);
});
