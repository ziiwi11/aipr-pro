const path = require("node:path");

function resolvePythonExecutable({ platform, arch, resourcesPath, env = {}, existsSync }) {
  const paths = platform === "darwin"
    ? [path.posix.join(resourcesPath, "runtime", "macos-arm64", "python", "bin", "python3")]
    : [
        path.win32.join(resourcesPath, "runtime", "windows-x64", "python", "python.exe"),
        path.win32.join(resourcesPath, "runtime", "python", "python.exe"),
        path.win32.join(env.LOCALAPPDATA || "", "Programs", "aipr-buyin-cart-talent", "resources", "app", "runtime", "python", "python.exe"),
      ];
  if (platform === "darwin" && arch !== "arm64") return "";
  return paths.find((target) => target && existsSync(target)) || "";
}

function resolveBrowserExecutable({ platform, env = {}, existsSync }) {
  const candidates = platform === "darwin"
    ? [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        env.HOME ? path.posix.join(env.HOME, "Applications", "Google Chrome.app", "Contents", "MacOS", "Google Chrome") : "",
      ]
    : [
        path.win32.join(env.PROGRAMFILES || "", "Microsoft", "Edge", "Application", "msedge.exe"),
        path.win32.join(env["PROGRAMFILES(X86)"] || "", "Microsoft", "Edge", "Application", "msedge.exe"),
        path.win32.join(env.PROGRAMFILES || "", "Google", "Chrome", "Application", "chrome.exe"),
        path.win32.join(env.LOCALAPPDATA || "", "Google", "Chrome", "Application", "chrome.exe"),
      ];
  return candidates.find((target) => target && existsSync(target)) || "";
}

function buildBrowserLaunch({ platform, executable, profile, port, url }) {
  if (!executable) throw new Error("Browser executable is required");
  return {
    command: executable,
    args: [`--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "--new-window", url],
    options: { detached: true, stdio: "ignore", shell: false, windowsHide: platform === "win32" },
  };
}

function resolveWorkerCwd(outputDir, fallbackDir) {
  const target = String(outputDir || fallbackDir || "").trim();
  if (!target) throw new Error("Worker directory is required");
  return target;
}

function buildPlatformReadiness({ platform, arch, pythonExe, browserExe, documentsDir, writable }) {
  const supported = (platform === "darwin" && arch === "arm64") || (platform === "win32" && arch === "x64");
  const checks = [
    { key: "architecture", label: "系统架构", passed: supported, detail: `${platform}/${arch}` },
    { key: "python", label: "内置 Python", passed: Boolean(pythonExe), detail: pythonExe || "未找到" },
    { key: "browser", label: "Chrome / Edge", passed: Boolean(browserExe), detail: browserExe || "未找到" },
    { key: "documents", label: "品牌任务目录", passed: Boolean(documentsDir) && Boolean(writable), detail: documentsDir || "不可用" },
  ];
  return {
    platform,
    arch,
    supported,
    python: pythonExe || "",
    browser: browserExe || "",
    documents: documentsDir || "",
    checks,
    ready: checks.every((item) => item.passed),
  };
}

module.exports = {
  buildBrowserLaunch,
  buildPlatformReadiness,
  resolveBrowserExecutable,
  resolvePythonExecutable,
  resolveWorkerCwd,
};
