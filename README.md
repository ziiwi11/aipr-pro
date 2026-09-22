# AIPR Pro 达人运营系统

macOS Apple Silicon / Windows x64 双平台桌面项目，包含 Electron 主进程、Python 采集与审核后端、前端发布资源、测试和构建脚本。

## 平台支持

| 平台 | 架构 | 状态 |
|---|---|---|
| macOS | arm64 (M 系列) | ✅ 已构建验证 |
| Windows | x64 | ✅ 配置就绪（见 [WINDOWS-BUILD.md](WINDOWS-BUILD.md)）|
| macOS | x64 (Intel) | ❌ 不支持 |
| Windows | arm64 | ❌ 不支持 |

平台判定逻辑见 `app/electron/platform-runtime.cjs`：

```javascript
const supported = (platform === "darwin" && arch === "arm64")
               || (platform === "win32" && arch === "x64");
```

## 项目完整性

此版本整理自 M1 迁移工程。`app/dist` 是现有前端编译产物及增量界面脚本；原始 React/Vue/TypeScript 前端工程不在当前材料中。因此可以打包现有界面，但不能从原始前端源码重新生成该 bundle。Python 运行环境在每台机器上安装，安装包不包含完整 Python 解释器。

## 安装与构建

**macOS**：需要 Apple Silicon Mac、arm64 Node.js 20+、npm、arm64 Python 3.12，以及安装于 Applications 的 Google Chrome 或 Chromium。

**Windows**：需要 Windows 10/11 x64、Node.js 20+、Python 3.12（准备运行时用）、系统 Chrome 或 Edge。详见 [WINDOWS-BUILD.md](WINDOWS-BUILD.md)。

构建会联网下载 npm 和 Python 依赖。

```bash
uname -m
node --version
python3.12 --version
bash ./01-构建并安装-M1.command
```

脚本建立应用专用 Python 环境、运行 `npm ci`、打包并本机签名。完成后打开 DMG，将应用拖入 Applications。构建产物位于：

```text
app/release-macos/AIPR-Pro-Mac-M1-1.0.0-arm64.dmg
app/release-macos/AIPR-Pro-Mac-M1-1.0.0-arm64.zip
```

这是本机临时签名包，未配置 Developer ID 公证。另一台 Mac 也需安装 Python 运行环境。构建不会自动恢复历史任务；如需迁移，按下面的数据迁移步骤操作。

## 使用流程

1. 启动应用，检查架构、Python、浏览器和 Documents 可写状态。
2. 在应用内置 A/B 店浏览器分别手动登录，并确认可进入达人广场。
3. 创建品牌任务，配置产品、视频达人类型、类目、画像、销售额和目标数量。
4. 使用结构化筛选分页发现达人。实时流程逐个审核，合适后查看平台授权联系方式，通过去重才进入名单。
5. 在正式名单、联系方式和运行记录中查看结果并导出。候选数、“有联系方式”标记、已揭示明文数和最终名单数是不同指标。
6. 平台出现请求频繁、验证码或登录失效时停止，保留断点，待恢复后续跑。

平台页面会变化，筛选点击日志不等于实际筛选结果；首次部署应以少量达人核对类目、内容类型、画像、联系方式和导出。现有自动审核仍需人工抽查真实视频及场景适配。

## AI 建联（雷神）

本项目包含雷神客户端适配器，不包含雷神服务。默认在本机 `127.0.0.1:19628`、`127.0.0.1:19627` 查找就绪的 `brand-referral` 项目。先启动兼容的雷神服务，再在 AI 建联界面选择名单、批量确认授权；同步与启动由界面确认控制。采集名单本身不会授权发送消息。

## 数据位置与迁移

- 应用配置和会话：`~/Library/Application Support/AIPR Pro 达人运营系统/`
- 品牌任务与交付：`~/Documents/AIPR Pro/品牌任务/`
- 仓库不附带真实达人名单、任务、联系方式、登录会话或密钥。

如需导入自己保存的历史任务，将数据放入本地 `migration-data/tasks/`（可选 `migration-data/integrations/`），关闭应用后执行 `python3.12 restore_data.py`。脚本先备份现有 tasks/integrations，再恢复文件，并将 Windows 用户 Documents 路径转换为当前 Mac Documents。仅放入可信任务配置；不要把浏览器目录或凭据加入迁移目录。

## 开发与验证

```bash
cd app
npm ci
node --test electron/*.test.cjs
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-macos.txt
.venv/bin/python -m unittest discover -s backend -p 'test_*.py'
npm run mac:dir
```

后端可通过命令行运行，但日常操作建议从应用启动，以便任务状态、历史记录和进程管理同步。测试通过不代表平台在线功能已验证；在线采集依赖当前账号权限和平台页面。

## 目录

- `app/electron/`：窗口、内置浏览器、任务、交付与雷神集成。
- `app/backend/`：发现、证据审核、联系方式、去重、导出及测试。
- `app/dist/`：已有前端发布资源。
- `app/runtime/`：调用本机专用 Python 环境的包装脚本。
- `restore_data.py`：可选历史任务迁移工具。

未指定开源许可证；本次整理不改变原项目及第三方组件的权利归属。
