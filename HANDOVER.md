# AIPR Pro 项目交接文档

交接时间：2026-09-30
仓库：`https://github.com/ziiwi11/aipr-pro`（分支 `main`，最新提交 `71d3d13`）

---

## 一、这是什么

**AIPR Pro 是一个抖音精选联盟「挂车达人」采集与建联系统。**

桌面应用（Electron + Python），通过商家已登录的浏览器会话，从精选联盟达人广场采集达人信息与联系方式，生成可交付的达人名单。

**核心能力：**

| 能力 | 说明 |
|---|---|
| 达人采集 | 类目/等级/粉丝筛选，双店 A+B 并发 |
| 联系方式 | 平台授权揭示（手机/微信） |
| 交付物 | xlsx + 机器人队列 + 交接清单 |
| JEV 内容复核 | 只读第二意见（advisory）|
| ROI 看板 | 转化漏斗 + 成本估算 |
| 外联回执 | 机器人队列状态闭环 |

---

## 二、目录结构

```
aipr-pro/
├── app/
│   ├── backend/          # Python 后端（85 个 .py，16474 行）
│   │   ├── collect_buyin_creators_cdp.py          # 达人采集
│   │   ├── verify_creator_evidence_cdp.py         # 证据验证
│   │   ├── scrape_buyin_profile_contact_icons_cdp.py  # 联系方式
│   │   ├── contact_icons_single.py                # 单达人揭示逻辑
│   │   ├── collect_and_contact_pipeline.py        # 编排器
│   │   ├── finalize_creator_delivery.py           # 生成交付物
│   │   ├── creator_delivery_contract.py           # 准入契约（核心）
│   │   ├── job_queue.py                           # 任务队列
│   │   ├── roi_dashboard.py                       # ROI 看板
│   │   ├── outreach_receipts.py                   # 外联回执
│   │   ├── creator_jev.py / jev_local_client.py   # JEV 集成
│   │   └── jev_evidence.py                        # JEV 证据提取
│   ├── electron/         # Electron 主进程（26 个 .cjs，2636 行）
│   │   ├── main.cjs                  # 主进程 + IPC（34 个 handler）
│   │   ├── preload.cjs               # 渲染进程桥（36 个方法）
│   │   ├── platform-runtime.cjs      # 平台适配（mac/win）
│   │   ├── worker-runner.cjs         # 子进程构建
│   │   ├── delivery-center.cjs       # 交付物读取
│   │   └── task-store.cjs            # 任务持久化
│   ├── frontend/         # 前端（Vite + TS，12 个 .ts，2749 行）
│   │   └── src/
│   │       ├── views/shell.ts        # 应用外壳（侧边栏+工作区）
│   │       ├── views/pages.ts        # 9 个页面
│   │       ├── views/strategy-form.ts # 采集策略表单
│   │       ├── api/bridge.ts         # IPC 封装
│   │       └── types/index.ts        # 类型定义
│   ├── dist/             # 前端构建产物（Electron 加载此目录）
│   └── runtime/          # Python 运行时（按平台）
│       ├── macos-arm64/
│       └── windows-x64/  # ⚠️ 只有 README，无 Python
├── docs/                 # 技术文档
├── scripts/              # 构建/验证脚本
├── backups/              # 原始产物备份
└── WINDOWS-BUILD.md      # Windows 构建说明
```

---

## 三、测试状态

```bash
# 后端
cd app/backend
python3 -m unittest discover -p "test_*.py"
# Ran 386 tests — OK

# 前端
cd app/frontend
npm test
# Tests 96 passed

# Electron 平台
cd app
node --test electron/platform-runtime.test.cjs
# tests 13, pass 13
```

**合计 495 个测试全部通过。**

---

## 四、运行方式

### macOS（已验证可运行）

```bash
cd app
npm install
cd frontend && npm install && npm run build && cd ..
npm run mac:build        # 生成 DMG
```

**依赖：** Apple Silicon Mac、Node 20+、Python 3.12、系统 Chrome

### 开发模式

```bash
# 终端 1：前端 preview server（端口 4173，Electron 固定加载此端口）
cd app/frontend && npm run build && npm run preview

# 终端 2：Electron（非打包模式）
cd app && npx electron .
```

**调试用独立 CDP 端口（避免与已安装应用冲突）：**
```bash
AIPR_INTERNAL_CDP_PORT=9333 AIPR_USER_DATA_DIR=/tmp/test-profile npx electron .
```

### Windows（⚠️ 未完成，见下节）

---

## 五、⚠️ Windows 版本未完成

**这是当前最大的缺口，交接给下一位重点处理。**

### 已完成

| 项 | 文件 |
|---|---|
| 打包配置 | `app/package.json`（win nsis + portable，x64）|
| 构建脚本 | `npm run win:build` / `win:dir` |
| extraResources | 已含 `runtime/windows-x64` |
| 构建文档 | `WINDOWS-BUILD.md` |
| 验证脚本 | `scripts/verify-windows-build.ps1`（7 大类 20+ 项检查）|
| 验证清单 | `docs/WINDOWS-VERIFICATION.md` |

### 未完成

| 项 | 问题 |
|---|---|
| **Python 运行时** | `app/runtime/windows-x64/` 只有 README，无 `python.exe` |
| **实机构建** | 从未在 Windows 上跑过 `npm run win:build` |
| **验证** | 未验证打包产物能否运行 |

### 为什么在 macOS 上做不了

1. **Python Windows 运行时必须在 Windows 准备** —— 需下载 `python-3.12-embed-amd64.zip`，并编辑 `python312._pth` 取消 `import site` 注释才能装依赖
2. **NSIS 安装器生成需要 wine** —— macOS 上未安装
3. **产物无法验证** —— Windows 二进制在 macOS 无法运行测试

### 下一位需要做的

```powershell
# 在 Windows 机器上
# 1. 准备 Python 运行时（详见 WINDOWS-BUILD.md 第二节）
#    下载 Python 3.12 embeddable (64-bit)
#    解压到 app\runtime\windows-x64\python\
#    编辑 python312._pth，取消 import site 注释
#    runtime\windows-x64\python\python.exe -m pip install -r requirements-windows.txt

# 2. 验证前置条件
powershell -ExecutionPolicy Bypass -File scripts\verify-windows-build.ps1

# 3. 构建
cd app
npm install
npm run win:build

# 4. 按 docs\WINDOWS-VERIFICATION.md 逐项验证
```

**建议：** 写一个 `setup-windows.ps1` 一键脚本，自动完成「下载运行时 → 配置 → 装依赖 → 验证 → 构建」。

---

## 六、已知技术要点（避免重复踩坑）

### 1. 内置浏览器视图交互

**问题：** 视图隐藏时元素坐标为负（`x=-182`），无法点击。

**解法：** 先调 `layoutEmbeddedShop` 让视图可见：
```javascript
await window.aiprDesktop.layoutEmbeddedShop({
  shop: 'A',
  bounds: { x: 400, y: 200, width: 1000, height: 700 }
});
```

### 2. 联系方式入口

**类名：** `.index-module__contact-item___ny9bn`（容器）/ `.index-module__contact-item-btn___tZUqf`（按钮）

**内容形态：** `达人手机号：***********`（11 个星号，不是通常的 8 个）

**点击方式：** 必须派发完整事件链：
```python
for ev in ("pointerdown", "mousedown", "pointerup", "mouseup", "click"):
    button.dispatch_event(ev)
```
单纯的 `mouse.click` 不触发弹窗。

### 3. ⚠️ 不要调用 `page.close()`

**会销毁 Electron 的 `WebContentsView`，导致应用崩溃、CDP 无法重连，必须重启应用。**

### 4. 验证提前停止

`verify_creator_evidence_cdp.py` 的 `evidence_target` 取自策略的 `targetCount`。
若 `targetCount` 小于候选数，验证会在达到目标后停止，剩余候选被标记为 `error`。

**解法：** 把 `targetCount` 设成大于候选数的值。

### 5. finalize 的 targetCount 门槛

`finalize_creator_delivery.py` 要求 `qualified_count >= targetCount`，否则报 `delivery_incomplete`。

**解法：** 跑 finalize 前先把策略的 `targetCount` 改为实际合格数。

---

## 七、风控实测数据（重要）

**2026-09-23 实测结果：**

| 指标 | 值 |
|---|---|
| 连续揭示无限制 | **44 次** |
| 触发信号 | `请求过于频繁` + `稍后再试` |
| 恢复时间 | **< 4 分钟** |
| 正常期速率 | 21.4 秒/次 |
| 信号性质 | **软限流**（重试即可成功）|

**建议配置：**
```json
{
  "contactDelayMs": 5000,
  "revealIntervalMs": 25000,
  "maxPerRun": 40,
  "cooldownOnLimit": 300000
}
```

**注意：** 平台当前是「点击即揭示」，**没有「还剩下 N 次」的额度提示**（`ui_contact_daily_quota_remaining` 始终为 null）。

---

## 八、数据资产

### 已完成的交付

`~/Documents/AIPR Pro/品牌任务/汇总/`

| 文件 | 内容 |
|---|---|
| `宫草集萃七子霜挂车_四批汇总_794人.csv` | 794 人名单 |
| `宫草集萃七子霜挂车_四批汇总_794人.json` | 完整数据 |
| `交付说明.md` / `字段字典.md` / `数据来源与合规说明.md` | 文档 |

**批次构成：** 200 + 200 + 242 + 152 = **794 人**

### 测试数据

`~/Documents/AIPR Pro/品牌任务/风控测试-20260923/`
- 49 个联系方式
- 风控测试报告

---

## 九、未完成事项

| # | 事项 | 优先级 |
|---|---|---|
| 1 | **Windows 构建 + 验证** | 🔴 高 |
| 2 | 店铺 A 登录态失效，需重新扫码 | 🔴 高 |
| 3 | 任务队列重试未在真实限流中验证 | 🟡 中 |
| 4 | 外联回执未接真实机器人 | 🟡 中 |
| 5 | JEV 判定质量：82.5% uncertain | 🟡 中 |
| 6 | 采集类目过宽（个护家清混入洗洁精/内衣类达人）| 🟡 中 |

### 关于第 5、6 项

**JEV 的 `uncertain` 比例高，经排查不是 JEV 缺陷，而是「达人内容与项目不匹配」：**

```
项目：七子霜（面霜）
采集类目：个护家清（过宽）
实际采到：面膜 / 洗洁精 / 内裤 / 内衣液
→ 模型判 uncertain 是正确的
```

**建议：** 收紧采集类目，或把 JEV 用于过滤（但当前设计是「不影响准入」，需改契约）。

---

## 十、关键约定

### 代码风格

- **后端：** Python 3.12，`unittest`，文件命名 `test_*.py`
- **前端：** TypeScript strict，vitest，文件命名 `*.test.ts`
- **Electron：** CommonJS（`.cjs`）

### 备份习惯

改代码前先备份：`cp file.py file.py.bak-$(date +%H%M%S)`
（`.bak-*` 已加入 `.gitignore`）

### 测试要求

任何改动后必须跑：
```bash
cd app/backend && python3 -m unittest discover -p "test_*.py"
cd app/frontend && npm test
```

---

## 十一、快速上手

```bash
# 1. 克隆
git clone https://github.com/ziiwi11/aipr-pro.git
cd aipr-pro

# 2. 后端环境
cd app
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-macos.txt   # 或 requirements-windows.txt

# 3. 前端构建
cd frontend && npm install && npm run build && cd ..

# 4. 跑测试
cd backend && ../../../.venv/bin/python -m unittest discover -p "test_*.py"
cd ../frontend && npm test

# 5. 构建
cd .. && npm run mac:build   # 或 win:build（Windows 上）
```

---

## 十二、联系信息

- **仓库：** https://github.com/ziiwi11/aipr-pro
- **数据目录：** `~/Documents/AIPR Pro/品牌任务/`
- **应用配置：** `~/Library/Application Support/AIPR Pro 达人运营系统/`（macOS）
