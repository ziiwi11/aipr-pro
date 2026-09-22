const http = require("node:http");

class LeiShenClient {
  constructor({ baseUrl, baseUrls, projectId = "brand-referral", timeoutMs = 3000 } = {}) {
    const candidates = baseUrl ? [baseUrl] : (baseUrls || ["http://127.0.0.1:19628", "http://127.0.0.1:19627"]);
    this.baseUrls = candidates.map((value) => validateBaseUrl(value));
    this.baseUrl = this.baseUrls.length === 1 ? this.baseUrls[0] : null;
    this.projectId = String(projectId || "brand-referral");
    this.timeoutMs = Math.max(100, Number(timeoutMs) || 3000);
  }

  async getStatus() {
    try {
      const payload = await this.request("GET", "/api/automation/status");
      return { online: true, baseUrl: this.baseUrl.origin, ...payload };
    } catch (error) {
      return { online: false, ok: false, error: error.message };
    }
  }

  async getPermissions() {
    try {
      const payload = await this.request("GET", "/api/system/permissions");
      return { online: true, ...payload };
    } catch (error) {
      return { online: false, ok: false, error: error.message };
    }
  }

  async getProjects() {
    try {
      const payload = await this.request("GET", "/api/projects");
      return { online: true, ...payload };
    } catch (error) {
      return { online: false, ok: false, error: error.message };
    }
  }

  async syncAuthorizedBatch(batch = {}) {
    if (batch.status !== "authorized") throw new Error("只有已授权批次可以同步到雷神");
    const content = buildCsv(batch, this.projectId);
    if (!content) throw new Error("授权批次没有可同步的微信或手机号");
    return this.request("POST", "/api/automation/queue/sync", {
      confirmed: true,
      authorizationSource: "explicit_ui_click",
      projectId: this.projectId,
      filename: `aipr-${safeId(batch.batchId || "batch")}.csv`,
      content,
    });
  }

  async startAuthorizedBatch(_batchId, confirmation = {}) {
    if (confirmation.explicitUiClick !== true) throw new Error("开始 AI 建联需要用户当次明确点击确认");
    return this.request("POST", "/api/automation/control", {
      action: "start",
      confirmed: true,
      authorizationSource: "explicit_ui_click",
    });
  }

  request(method, pathname, body) {
    return this.resolveBaseUrl().then((baseUrl) => this.requestAt(baseUrl, method, pathname, body));
  }

  async resolveBaseUrl() {
    if (this.baseUrl) return this.baseUrl;
    for (const candidate of this.baseUrls) {
      try {
        const payload = await this.requestAt(candidate, "GET", "/api/projects");
        const projects = payload?.result?.projects || payload?.projects || [];
        if (projects.some((project) => project.id === this.projectId && project.ready === true)) {
          this.baseUrl = candidate;
          return candidate;
        }
      } catch {}
    }
    throw new Error("未找到包含就绪 brand-referral 项目的最新雷神服务");
  }

  requestAt(baseUrl, method, pathname, body) {
    const target = new URL(pathname, baseUrl);
    return new Promise((resolve, reject) => {
      const contents = body === undefined ? "" : JSON.stringify(body);
      const request = http.request(target, {
        method,
        timeout: this.timeoutMs,
        headers: contents ? { "content-type": "application/json", "content-length": Buffer.byteLength(contents) } : {},
      }, (response) => {
        let raw = "";
        response.setEncoding("utf8");
        response.on("data", (chunk) => { raw += chunk; });
        response.on("end", () => {
          let parsed;
          try { parsed = raw ? JSON.parse(raw) : {}; } catch { return reject(new Error("雷神接口返回了无效 JSON")); }
          if (response.statusCode < 200 || response.statusCode >= 300 || parsed?.ok === false) {
            return reject(new Error(String(parsed?.error || `雷神接口错误 ${response.statusCode}`)));
          }
          resolve(parsed);
        });
      });
      request.on("timeout", () => request.destroy(new Error("雷神接口连接超时")));
      request.on("error", reject);
      if (contents) request.write(contents);
      request.end();
    });
  }
}

function validateBaseUrl(value) {
  const baseUrl = new URL(value);
  if (baseUrl.protocol !== "http:" || baseUrl.hostname !== "127.0.0.1") {
    throw new Error("雷神接口只允许连接 127.0.0.1 回环地址");
  }
  return baseUrl;
}

function buildCsv(batch, projectId) {
  const rows = (batch.valid || []).filter((item) => item.contactValue && ["wechat", "phone", "contact"].includes(item.contactType));
  if (!rows.length) return "";
  return [
    ["wechat", "note", "project", "brand"],
    ...rows.map((item) => [item.contactValue, item.name || item.contactValue, projectId, batch.task?.name || ""]),
  ].map((row) => row.map(csvCell).join(",")).join("\n") + "\n";
}

function csvCell(value) {
  const text = String(value || "");
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function safeId(value) {
  return String(value || "batch").toLowerCase().replace(/[^a-z0-9_-]/g, "-") || "batch";
}

module.exports = { LeiShenClient, buildCsv };
