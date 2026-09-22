# 前端工程说明

AIPR Pro 前端 — Vite + TypeScript 重写版

---

## 背景

原前端为 React/Vue/TypeScript 编译产物（`app/dist/assets/index-*.js`，361 KB），
**源码不在当前材料中**（见根目录 README）。本工程为**源码重建版**。

### 重建依据

| 依据 | 来源 |
|---|---|
| IPC 契约 | `app/electron/preload.cjs`（34 个 invoke + 2 个事件监听）|
| 数据结构 | `app/electron/main.cjs` 的 handler 返回值 |
| DOM 结构 | 增量脚本引用的类名（`.outreach-page` / `.panel` 等）|
| 主题色 | `dist/index.html` 的 `theme-color: #18201b` |

---

## 目录结构

```
app/frontend/
├── package.json          # 构建脚本
├── tsconfig.json         # TS 配置（strict）
├── vite.config.ts        # 构建配置（输出到 ../dist）
└── src/
    ├── index.html        # HTML 模板
    ├── main.ts           # 入口：挂载 + 刷新循环 + 增量脚本加载
    ├── store.ts          # 轻量状态容器 + DOM 工具
    ├── types/
    │   └── index.ts      # 全部类型定义（Task/Creator/Bootstrap…）
    ├── api/
    │   └── bridge.ts     # IPC 封装（对齐 preload 契约）
    ├── views/
    │   └── main.ts       # 主视图（7 个面板 + 2 个表格）
    ├── styles/
    │   └── app.css       # 样式（对齐现有主题）
    └── public/           # 增量脚本（Vite 原样复制到 dist）
        ├── aipr-ai-outreach.js / .css
        └── aipr-realtime-flow.js / .css
```

---

## 开发

```bash
cd app/frontend

# 安装依赖（仅 typescript + vite）
npm install

# 类型检查
npm run typecheck

# 开发模式（热更新，端口 5173）
npm run dev

# 构建到 app/dist
npm run build
```

### dev 模式的限制

浏览器直接打开 `http://localhost:5173` 时，`window.aiprDesktop` 不存在，
界面会显示"启动失败"。**这是预期行为** —— 前端依赖 Electron 的 IPC 桥。

要在 dev 模式下调试界面，需在 Electron 中加载 dev server：

```javascript
// electron/main.cjs（临时改动）
mainWindow.loadURL("http://localhost:5173");
```

---

## 核心设计

### 1. 零框架依赖

不引入 React/Vue，用原生 DOM + 轻量状态容器。原因：

- 主 bundle 是 React 产物但源码缺失，无法复用组件
- 依赖树越小，打包产物越小（9.3 KB vs 361 KB）
- 便于与增量脚本共存

### 2. IPC 桥接层

`api/bridge.ts` 封装全部 34 个 IPC 方法：

```typescript
export const getBootstrap = (): Promise<Bootstrap> => api().getBootstrap();
export const startCollection = (task, strategy) => api().startCollection(task, strategy);
// ...
```

**契约对齐验证**：`preload.cjs` 的 34 个 invoke 与 `main.cjs` 的 34 个 handler 完全一致。

### 3. 增量脚本共存

两个增量脚本通过 DOM 注入增强界面：

```javascript
// aipr-ai-outreach.js
const page = document.querySelector(".outreach-page");
const banner = page.querySelector(".outreach-banner");
banner?.insertAdjacentElement("afterend", panel);   // 注入 AI 建联工作台
```

因此本工程的 DOM 结构**沿用原有类名**：

| 类名 | 用途 |
|---|---|
| `.outreach-page` | 主容器（增量脚本挂载点）|
| `.outreach-banner` | 顶部横幅（插入锚点）|
| `.panel` | 面板基类 |

**加载时机**：`main.ts` 在首次渲染完成后动态 import 这两个脚本。

### 4. 刷新机制

- 初始加载后每 5 秒轮询 `getBootstrap()`
- 收到 worker 事件（`progress` / `finished` / `paused`）时立即刷新
- 暴露 `window.__AIPR_REFRESH__` 供增量脚本手动触发

---

## 界面构成

| 面板 | 类名 | 数据来源 |
|---|---|---|
| 任务中心 | `.task-center-panel` | `bootstrap.tasks` |
| 平台自检 | `.connection-panel` | `bootstrap.platformReadiness` |
| 采集控制 | `.activity-panel` | `bootstrap.task` |
| 实时流程 | `.priority-panel` | `bootstrap.realtimeFlow` |
| 交付中心 | `.handoff-panel` | `bootstrap.deliveryCenter` |
| 规则配置 | `.export-panel` | 导出/导入 |
| 运行历史 | `.list-panel` | `bootstrap.runHistory` |
| 候选达人表 | `.score-panel` | `bootstrap.candidateCreators` |
| 正式名单表 | `.decision-panel` | `bootstrap.creators` |

---

## 构建配置要点

### 输出到 app/dist

```typescript
build: {
  outDir: resolve(__dirname, "../dist"),
  emptyOutDir: false,      // 保留增量脚本
  rollupOptions: {
    output: {
      entryFileNames: "assets/app.js",   // 固定文件名
      assetFileNames: "assets/[name].[ext]",
    },
  },
}
```

### publicDir

```typescript
publicDir: resolve(__dirname, "src/public"),   // 增量脚本原样复制
```

### 为什么 HTML 里不写 `<link>` 引用增量脚本

Vite 会解析 HTML 中的 `<script src>` 和 `<link href>`，找不到文件就报错。
增量脚本不在模块图内，因此改为在 `main.ts` 运行时注入。

---

## 与原版的差异

| 项 | 原版 | 重写版 |
|---|---|---|
| 源码 | ❌ 缺失 | ✅ 完整 |
| 框架 | React（推断）| 原生 DOM |
| 产物大小 | 361 KB | 9.3 KB |
| 可维护性 | 无法改 | 可改 |
| 组件复用 | - | 无（重新实现）|
| 增量脚本 | 原生支持 | ✅ 兼容 |

---

## 待完善

- [ ] 达人列表分页 / 筛选（当前只渲染前 200 条）
- [ ] 采集策略编辑表单（当前只读展示）
- [ ] 浏览器嵌入视图的布局控制（`layoutEmbeddedShop`）
- [ ] 交付物预览（`previewRobotHandoff`）
- [ ] 外联批次管理界面（`outreachBatches`）
- [ ] 错误提示 / 加载状态细化
- [ ] 单元测试（当前仅类型检查）
