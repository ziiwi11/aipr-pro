# 千寻 Windows x64 构建

客户不需另装 Python、pip 或 Node。软件内置 Electron 浏览器及平台 Python 运行环境。目标系统为 Windows 10/11 x64；ARM 版未支持。安装包构建与文件检查通过不等于 Windows 实机通过。

## 构建机

准备 Node/npm、Python 与 pip；执行 `npm ci` 及 `npm --prefix frontend ci`。已有 `app/runtime/windows-x64` 包含 CPython 3.12.10 嵌入式 x64 及固定依赖，清单记录来源和文件哈希。如需重建，先保留旧目录，再运行 `app/scripts/bundle-windows-runtime.py`；不要将客户密钥或浏览器会话放入运行环境。

从 `app` 执行：

```sh
npm run runtime:windows
npm run win:build
```

第一步校验 x64 可执行文件、后端模块搜索路径及清单内每个文件的 SHA256。第二步重复运行环境检查，执行全量回归、类型检查、前端构建，再打包 NSIS 与 portable。优先在 Windows 构建机生成；其他平台生成的 EXE 仍需 Windows 实机测试。

产物位于 `app/release-windows`：

- `Qianxun-Win-Setup-<version>-x64.exe`
- `Qianxun-Win-Portable-<version>-x64.exe`
- `win-unpacked` 解包目录

版本必须与冻结源码和Mac客户包一致。当前旧版产物不能作为最终发布包。包内仅包含 Windows 运行时，不夹带 Mac 运行时。

## 实机验证与签名

按 [Windows 原生验收](docs/WINDOWS-VERIFICATION.md) 核对，保存软件版本、OS架构、每项证据和失败原因。当前 Windows 实机尚未完成，不能宣称已通过。尚无发布者证书；SmartScreen提示和签名状态须据最终产物如实记录，不通过工具绕过系统安全。

应用配置沿用 `%APPDATA%\AIPR Pro 达人运营系统\`；任务保存在系统 Documents 下的 `AIPR Pro/品牌任务`。数据迁移用软件内备份恢复，恢复任务不自动采集；不要复制登录会话、密钥或发送授权到其他电脑。
