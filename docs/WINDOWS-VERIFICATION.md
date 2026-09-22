# Windows 构建验证清单

在 Windows 上首次构建/运行 AIPR Pro 时，按本清单逐项确认。

---

## 一、自动检查（构建前）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-windows-build.ps1
```

该脚本检查 7 大类共 20+ 项前置条件：

| # | 检查项 | 说明 |
|---|---|---|
| 1 | 平台与架构 | Windows + x64 |
| 2 | Node 环境 | node / npm 可用，Node ≥ 20 |
| 3 | 项目文件 | package.json、win 配置、extraResources |
| 4 | 前端产物 | dist/index.html、app.js、增量脚本 |
| 5 | Python 运行时 | python.exe、3 个依赖模块 |
| 6 | 系统浏览器 | Chrome 或 Edge |
| 7 | 后端脚本 | 4 个核心 .py 文件 |

**全部通过才建议执行构建。**

---

## 二、构建（Windows 上）

```powershell
cd app
npm install
npm run win:build
```

**产物：**

| 文件 | 说明 |
|---|---|
| `release-windows\AIPR-Pro-Win-Setup-1.0.0-x64.exe` | NSIS 安装包 |
| `release-windows\AIPR-Pro-Win-Portable-1.0.0-x64.exe` | 免安装版 |
| `release-windows\win-unpacked\` | 解包目录（调试用）|

---

## 三、安装后验证（人工）

### 3.1 启动与自检

- [ ] 应用能启动，无白屏
- [ ] 左侧导航栏显示 9 个菜单项
- [ ] 「系统设置」页显示平台自检结果
- [ ] 自检 4 项全绿：架构 / 内置 Python / Chrome-Edge / 品牌任务目录

**自检失败时的排查：**

| 失败项 | 原因 | 处理 |
|---|---|---|
| 内置 Python | `runtime\windows-x64\python\python.exe` 缺失 | 见 `runtime/windows-x64/README.md` |
| Chrome / Edge | 系统未安装浏览器 | 装 Chrome 或 Edge |
| 品牌任务目录 | 文档目录不可写 | 检查权限 |

### 3.2 内置浏览器

- [ ] 点击「抖店浏览器」页
- [ ] 点击「启动浏览器」
- [ ] 两个内置视图出现（抖店 A / 抖店 B）
- [ ] 能导航到抖店登录页
- [ ] 后退 / 前进 / 刷新 按钮生效

### 3.3 登录态

- [ ] 抖店 A 登录成功
- [ ] 抖店 B 登录成功
- [ ] 进入精选联盟后角色选择正常

> **注意**：若页面跳到 `www.douyinec.com`，说明需要重新选择角色。
> 导航到 `/mpa/account/roles-select` 并点击「登录商家工作台」。

### 3.4 采集链路（小量验证）

用 3-5 个达人验证，不要直接跑大批量：

- [ ] 创建任务（如「Windows验证任务」）
- [ ] 编辑策略：类目=美妆个护，等级=LV1-2，店铺=A+B，目标=5
- [ ] 保存策略 → 提示「策略已保存」
- [ ] 点击「开始采集」
- [ ] 任务状态变为 `running`
- [ ] 实时流面板数字开始增长
- [ ] 任务目录出现 `aipr_realtime_creator_flow.json`

### 3.5 交付物

- [ ] 采集完成后点「交付中心」
- [ ] 显示 xlsx / 机器人队列 / 交接清单
- [ ] 点「打开」能用系统程序打开文件

---

## 四、已知差异（Windows vs macOS）

| 项 | macOS | Windows |
|---|---|---|
| Python 路径 | `runtime/macos-arm64/python/bin/python3` | `runtime/windows-x64/python/python.exe` |
| 浏览器查找 | `/Applications/Google Chrome.app/...` | `%PROGRAMFILES%\Google\Chrome\Application\chrome.exe` |
| 备选浏览器 | Chromium | Edge |
| 进程启动 | `detached: true` | `windowsHide: true` |
| 关闭窗口 | 保留进程 | 退出应用 |
| 数据目录 | `~/Library/Application Support/...` | `%APPDATA%\AIPR Pro 达人运营系统\` |
| 品牌任务 | `~/Documents/AIPR Pro/品牌任务/` | `%USERPROFILE%\Documents\AIPR Pro\品牌任务\` |

---

## 五、未验证项（需在 Windows 上确认）

以下内容**未在 macOS 上验证过**，Windows 首次运行时需重点确认：

1. **打包本身** —— electron-builder 的 Windows 目标通常需在 Windows 上构建
2. **Python 嵌入式包的 `._pth` 配置** —— 需手动取消 `import site` 注释
3. **Playwright 浏览器** —— 若用内置 Python，需 `playwright install chromium`；或依赖系统 Chrome/Edge
4. **代码签名** —— 未配置证书，SmartScreen 会提示「未知发布者」
5. **长路径问题** —— Windows 路径长度限制可能影响深层目录
6. **中文路径** —— 品牌任务目录含中文，确认 Python 正确处理编码

---

## 六、回滚

若 Windows 构建出现问题，macOS 版本不受影响：

- Windows 配置是**追加**的（`win` 段 + `win:build` 脚本）
- macOS 的 `mac` 段与 `mac:build` 脚本未改动
- `extraResources` 同时包含两个平台的运行时，打包时只复制存在的目录

**验证 macOS 未受影响：**

```bash
cd app && npm run mac:dir
```
