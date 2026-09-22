const assert = require("node:assert");
const { test } = require("node:test");
const path = require("node:path");

const {
  resolvePythonExecutable,
  resolveBrowserExecutable,
  buildBrowserLaunch,
  buildPlatformReadiness,
} = require("./platform-runtime.cjs");

// ---- Python 解析 ----

test("darwin/arm64 解析 macos-arm64 内置 Python", () => {
  const wanted = path.posix.join("/res", "runtime", "macos-arm64", "python", "bin", "python3");
  const got = resolvePythonExecutable({
    platform: "darwin",
    arch: "arm64",
    resourcesPath: "/res",
    env: {},
    existsSync: (p) => p === wanted,
  });
  assert.strictEqual(got, wanted);
});

test("darwin 非 arm64 返回空（不支持 Intel Mac）", () => {
  const got = resolvePythonExecutable({
    platform: "darwin",
    arch: "x64",
    resourcesPath: "/res",
    env: {},
    existsSync: () => true,
  });
  assert.strictEqual(got, "");
});

test("win32 优先解析 runtime/windows-x64/python/python.exe", () => {
  const wanted = path.win32.join("C:\\res", "runtime", "windows-x64", "python", "python.exe");
  const got = resolvePythonExecutable({
    platform: "win32",
    arch: "x64",
    resourcesPath: "C:\\res",
    env: {},
    existsSync: (p) => p === wanted,
  });
  assert.strictEqual(got, wanted);
});

test("win32 回退到 runtime/python/python.exe", () => {
  const fallback = path.win32.join("C:\\res", "runtime", "python", "python.exe");
  const got = resolvePythonExecutable({
    platform: "win32",
    arch: "x64",
    resourcesPath: "C:\\res",
    env: {},
    existsSync: (p) => p === fallback,
  });
  assert.strictEqual(got, fallback);
});

test("win32 回退到 LOCALAPPDATA 安装目录", () => {
  const local = path.win32.join(
    "C:\\Users\\u\\AppData\\Local",
    "Programs", "aipr-buyin-cart-talent", "resources", "app", "runtime", "python", "python.exe",
  );
  const got = resolvePythonExecutable({
    platform: "win32",
    arch: "x64",
    resourcesPath: "C:\\res",
    env: { LOCALAPPDATA: "C:\\Users\\u\\AppData\\Local" },
    existsSync: (p) => p === local,
  });
  assert.strictEqual(got, local);
});

test("win32 全部缺失时返回空", () => {
  const got = resolvePythonExecutable({
    platform: "win32",
    arch: "x64",
    resourcesPath: "C:\\res",
    env: {},
    existsSync: () => false,
  });
  assert.strictEqual(got, "");
});

// ---- 浏览器解析 ----

test("win32 解析系统 Edge", () => {
  const edge = path.win32.join("C:\\PF", "Microsoft", "Edge", "Application", "msedge.exe");
  const got = resolveBrowserExecutable({
    platform: "win32",
    env: { PROGRAMFILES: "C:\\PF" },
    existsSync: (p) => p === edge,
  });
  assert.strictEqual(got, edge);
});

test("win32 解析系统 Chrome", () => {
  const chrome = path.win32.join("C:\\PF", "Google", "Chrome", "Application", "chrome.exe");
  const got = resolveBrowserExecutable({
    platform: "win32",
    env: { PROGRAMFILES: "C:\\PF" },
    existsSync: (p) => p === chrome,
  });
  assert.strictEqual(got, chrome);
});

// ---- 启动参数 ----

test("win32 启动参数带 windowsHide", () => {
  const launch = buildBrowserLaunch({
    platform: "win32",
    executable: "C:\\chrome.exe",
    profile: "C:\\profile",
    port: 9222,
    url: "https://example.com",
  });
  assert.strictEqual(launch.options.windowsHide, true);
  assert.ok(launch.args.some((a) => a.includes("--remote-debugging-port=9222")));
});

// ---- 就绪检查 ----

test("win32/x64 被判定为受支持平台", () => {
  const r = buildPlatformReadiness({
    platform: "win32",
    arch: "x64",
    pythonExe: "C:\\py.exe",
    browserExe: "C:\\chrome.exe",
    documentsDir: "C:\\Docs",
    writable: true,
  });
  assert.strictEqual(r.supported, true);
  assert.strictEqual(r.ready, true);
});

test("win32/arm64 不被支持", () => {
  const r = buildPlatformReadiness({
    platform: "win32",
    arch: "arm64",
    pythonExe: "C:\\py.exe",
    browserExe: "C:\\chrome.exe",
    documentsDir: "C:\\Docs",
    writable: true,
  });
  assert.strictEqual(r.supported, false);
  assert.strictEqual(r.ready, false);
});

test("缺少 Python 时 ready 为 false", () => {
  const r = buildPlatformReadiness({
    platform: "win32",
    arch: "x64",
    pythonExe: "",
    browserExe: "C:\\chrome.exe",
    documentsDir: "C:\\Docs",
    writable: true,
  });
  assert.strictEqual(r.ready, false);
  assert.strictEqual(r.checks.find((c) => c.key === "python").passed, false);
});

test("darwin/arm64 仍被判定为受支持", () => {
  const r = buildPlatformReadiness({
    platform: "darwin",
    arch: "arm64",
    pythonExe: "/py",
    browserExe: "/chrome",
    documentsDir: "/Docs",
    writable: true,
  });
  assert.strictEqual(r.supported, true);
  assert.strictEqual(r.ready, true);
});
