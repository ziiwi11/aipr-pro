# Windows 版本构建说明

AIPR Pro 达人运营系统 — Windows x64 构建

---

## 一、前置条件

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10/11 x64 |
| Node.js | 20+ |
| Python | 3.12（用于准备运行时）|
| 浏览器 | Chrome 或 Edge（系统安装即可）|

---

## 二、准备 Python 运行时

Windows 打包需要把 Python 运行时放进 `runtime/windows-x64/python/`。

`electron/platform-runtime.cjs` 按以下顺序查找：

```
1. resources/runtime/windows-x64/python/python.exe   ← 本目录
2. resources/runtime/python/python.exe
3. %LOCALAPPDATA%/Programs/aipr-buyin-cart-talent/resources/app/runtime/python/python.exe
```

### 方式一：嵌入式包（推荐，体积小 ~15MB）

```powershell
# 1. 下载 Python 3.12 embeddable package (64-bit)
#    https://www.python.org/downloads/windows/
#    选 "Windows embeddable package (64-bit)"，解压到：
#    app\runtime\windows-x64\python\

# 2. 启用 site-packages（嵌入式包默认禁用）
#    编辑 app\runtime\windows-x64\python\python312._pth，改为：
#      python312.zip
#      .
#      Lib\site-packages
#      import site        ← 取消这一行的注释

# 3. 安装依赖
cd app
runtime\windows-x64\python\python.exe -m pip install -r requirements-windows.txt
```

### 方式二：完整安装目录（简单，体积大 ~100MB）

```powershell
# 1. 安装 Python 3.12 到自定义目录（不要勾选 Add to PATH）
#    例如 C:\Python312

# 2. 复制整个目录
xcopy /E /I C:\Python312 app\runtime\windows-x64\python

# 3. 安装依赖
cd app
runtime\windows-x64\python\python.exe -m pip install -r requirements-windows.txt
```

### 依赖清单

`app/requirements-windows.txt`：

```
openpyxl==3.1.5
playwright==1.60.0
pypdf==6.10.0
```

---

## 三、构建

```powershell
cd app

# 安装 Node 依赖
npm install

# 生成安装包 + 免安装版
npm run win:build

# 仅生成解包目录（调试用，快）
npm run win:dir
```

### 产物

在 `app/release-windows/`：

| 文件 | 说明 |
|---|---|
| `AIPR-Pro-Win-Setup-1.0.0-x64.exe` | NSIS 安装包（可选安装目录）|
| `AIPR-Pro-Win-Portable-1.0.0-x64.exe` | 免安装版（直接运行）|
| `win-unpacked/` | 解包目录（调试用）|

---

## 四、打包配置说明

`app/package.json` 的 `build` 段：

```json
{
  "win": {
    "target": [
      { "target": "nsis", "arch": ["x64"] },
      { "target": "portable", "arch": ["x64"] }
    ],
    "artifactName": "AIPR-Pro-Win-${version}-${arch}.${ext}"
  },
  "nsis": {
    "oneClick": false,
    "allowToChangeInstallationDirectory": true,
    "createDesktopShortcut": true,
    "createStartMenuShortcut": true
  },
  "portable": {
    "artifactName": "AIPR-Pro-Win-Portable-${version}-${arch}.${ext}"
  }
}
```

**extraResources** 同时包含两个平台的运行时：

```json
"extraResources": [
  { "from": "backend", "to": "backend" },
  { "from": "runtime/macos-arm64", "to": "runtime/macos-arm64" },
  { "from": "runtime/windows-x64", "to": "runtime/windows-x64" }
]
```

> 打包时只会复制存在的目录。构建 Windows 版时若 `runtime/macos-arm64` 不存在也不影响。

---

## 五、平台支持矩阵

| 平台 | 架构 | 支持 |
|---|---|---|
| macOS | arm64 (M 系列) | ✅ |
| macOS | x64 (Intel) | ❌ |
| Windows | x64 | ✅ |
| Windows | arm64 | ❌ |

由 `platform-runtime.cjs` 的 `buildPlatformReadiness` 判定：

```javascript
const supported = (platform === "darwin" && arch === "arm64")
               || (platform === "win32" && arch === "x64");
```

---

## 六、运行时行为差异

| 项 | macOS | Windows |
|---|---|---|
| Python 路径 | `runtime/macos-arm64/python/bin/python3` | `runtime/windows-x64/python/python.exe` |
| 浏览器查找 | `/Applications/Google Chrome.app/...` | `%PROGRAMFILES%/Google/Chrome/Application/chrome.exe` |
| 备选浏览器 | Chromium | Edge（`msedge.exe`）|
| 启动参数 | `detached: true` | `windowsHide: true` |
| 关闭窗口行为 | 保留进程（macOS 惯例）| 退出应用 |

---

## 七、注意事项

### 1. Playwright 浏览器

`playwright==1.60.0` 需要单独下载浏览器：

```powershell
runtime\windows-x64\python\python.exe -m playwright install chromium
```

**或**依赖系统 Chrome/Edge（`platform-runtime.cjs` 会自动查找）。

### 2. 代码签名

当前未配置签名证书，Windows SmartScreen 会提示"未知发布者"。

如需签名，在 `package.json` 添加：

```json
"win": {
  "certificateFile": "path/to/cert.pfx",
  "certificatePassword": "***"
}
```

### 3. 交叉编译限制

**electron-builder 的 Windows 目标通常需要在 Windows 上构建**，或在 macOS/Linux 上借助 Wine。

推荐：**在 Windows 机器上执行 `npm run win:build`**。

### 4. 数据目录

Windows 上数据路径：

| 项 | 路径 |
|---|---|
| 应用配置 | `%APPDATA%\AIPR Pro 达人运营系统\` |
| 品牌任务 | `%USERPROFILE%\Documents\AIPR Pro\品牌任务\` |

`restore_data.py` 会把 Windows 的 Documents 路径转换为当前平台路径。

---

## 八、验证清单

构建完成后逐项核对：

- [ ] 应用能启动，界面正常显示
- [ ] 平台自检通过（架构/Python/浏览器/目录）
- [ ] 能打开内置浏览器并登录抖店
- [ ] 能进入达人广场
- [ ] 能跑一次小量采集（3-5 个达人）
- [ ] 能生成交付物（xlsx + 队列 + 清单）
- [ ] `restore_data.py` 能正确恢复历史任务
