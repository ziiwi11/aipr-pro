# 给接手方（ChatGPT / 其他 AI）的上下文说明

本文档补充 `HANDOVER.md`，说明**本次会话做了什么**以及**容易误解的地方**。

---

## 一、当前最重要的任务

**完成 Windows 版本。**

配置和文档都已就绪，缺两样：
1. `app/runtime/windows-x64/python/` 下的 Python 运行时（我无法在 macOS 准备）
2. 在 Windows 上实际跑一次 `npm run win:build` 并验证

**详见 `HANDOVER.md` 第五节。**

---

## 二、本次会话做了什么

前一位 AI（我）在原有系统基础上完成了这些：

| 工作 | 产出 |
|---|---|
| 重写前端工程 | `app/frontend/`（原 React 源码缺失，按原版架构重建）|
| Windows 构建配置 | `package.json` win 段 + 验证脚本 + 文档 |
| JEV 集成验证 | 16 个测试 + 文档（核心逻辑是他人写的）|
| 任务队列 | `job_queue.py` + 接入采集流程 |
| ROI 看板 | `roi_dashboard.py` + 接入交付物与前端 |
| 外联回执 | `outreach_receipts.py` + 接入机器人队列 |
| JEV 证据提取 | `jev_evidence.py`（recent_titles 填充率 0%→98%）|
| 风控测试 | 测出 44 次阈值、4 分钟恢复 |

**git 记录：** `git log --oneline 23a3234..HEAD`（13 个提交）

---

## 三、⚠️ 容易误解的五件事

### 1. 前端是「重写」不是「修复」

**原前端只有 React 编译产物（361 KB bundle），源码不在仓库里。**

我根据 CDP 从已安装应用提取的真实参数（布局/颜色/类名）重建了源码。

**关键参数（已固化在 `docs/ORIGINAL-UI-SPEC.md`）：**
```
.app-shell: grid 232px 1fr
.sidebar: 232px 宽, #18201b 背景
工作区: #f2f4f2 背景
CSS 变量: --panel:#ffffff --ink:#17201b --muted:#6b746e --line:#dfe4e0
9 个页面根类名各自独立
```

**如果接手后改动前端，务必保持这些类名** —— 增量脚本（`aipr-ai-outreach.js`、`aipr-realtime-flow.js`）依赖它们。

### 2. JEV 不是我的代码

`creator_jev.py` 和 `jev_local_client.py` 是**他人写的**。我做了：
- 验证端到端可用
- 补 16 个单元测试
- 写文档 `docs/JEV-INTEGRATION.md`
- 新增 `jev_evidence.py` 补齐证据

**改 JEV 前请先理解它的设计约束：**
```python
'admission_changed': False,   # 不影响准入
'auto_send_allowed': False,   # 不自动发送
```
这两个 `False` 是硬编码的，有测试保护（`test_advisory_flags_always_safe`）。

### 3. 风控数据是实测的，不是猜的

`HANDOVER.md` 第七节的数据来自 2026-09-23 的真实测试（49 次揭示）。

**关键：平台当前没有额度提示弹窗** —— 目标文档里假设的「还剩下 N 次」在实测中不存在。

### 4. 店铺 A 登录态失效

`~/Library/Application Support/AIPR Pro 达人运营系统/` 里的店铺 A 会话过期，**需人工扫码**。

测试时只用店铺 B。

### 5. `page.close()` 会搞坏应用

**这条很重要。** 内置浏览器是 Electron 的 `WebContentsView`，调 `page.close()` 会销毁它，导致：
- 应用需要重启
- CDP 连接超时

**已在 `probe_contact_quota.py` 注释里记录。**

---

## 四、建议的处理顺序

```
1. 【高】Windows 构建 + 验证
   → 写 setup-windows.ps1 一键脚本（下载运行时+配置+构建）

2. 【高】恢复店铺 A 登录
   → 需要人工扫码，无法自动化

3. 【中】修复采集类目过宽问题
   → 个护家清混入洗洁精/内衣类达人，导致 JEV 大量 uncertain

4. 【中】验证队列重试
   → 需在真实限流中测试（可以等自然触发）

5. 【低】外联回执接真实机器人
```

---

## 五、环境信息

| 项 | 值 |
|---|---|
| 开发机 | macOS (Apple Silicon) |
| Node | v24.18.1（在 `~/.local/bin/node`）|
| Python | 3.12（在 `app/.venv/`）|
| 应用数据 | `~/Library/Application Support/AIPR Pro 达人运营系统/` |
| 品牌任务 | `~/Documents/AIPR Pro/品牌任务/` |
| CDP 端口 | 9222（已安装应用）/ 9333（测试实例）|

**注意：** 系统 PATH 里可能没有 `node`，需 `export PATH="$HOME/.local/bin:$PATH"`。

---

## 六、测试基线

**交接时全部通过：**
```
后端:    386 tests OK
前端:    96 tests passed
Electron: 13 tests passed
```

**任何改动后必须保持这些通过。**
