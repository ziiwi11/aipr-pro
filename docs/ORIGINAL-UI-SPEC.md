# 原版界面规格（CDP 提取）

通过 CDP 连接已安装应用（端口 9222）提取的真实参数。

---

## 一、整体布局

```
.app-shell  { display: grid; grid-template-columns: 232px 1208px; background: #f2f4f2; }
├── aside.sidebar
│   ├── .brand-lockup        Logo + "AIPR Pro / 达人运营系统"
│   ├── .context-label       "当前品牌任务"
│   ├── .task-switch-wrap    .task-switch（任务切换按钮）
│   ├── nav                  9 个页面按钮
│   └── .sidebar-foot
│       ├── .system-state    "本机服务正常 / 数据已保存"
│       └── .user            "运营管理员 / 全部权限"
└── main.workspace
    ├── header.topbar
    │   ├── 面包屑（"宫草集萃七子霜挂车 / 200 人提报"）
    │   └── .top-actions（抖店 A/B 状态卡 + 刷新按钮）
    └── .page-body
        └── <当前页面>
```

**尺寸：**

| 项 | 值 |
|---|---|
| 侧边栏宽 | 232px |
| 侧边栏背景 | `#18201b` |
| 侧边栏 padding | `22px 14px 18px` |
| 工作区背景 | `#f2f4f2` |

---

## 二、CSS 变量（浅色主题）

```css
--panel: #ffffff;
--ink:   #17201b;
--muted: #6b746e;
--line:  #dfe4e0;
```

> ⚠️ 我此前的实现用了深色主题（`--bg: #18201b`），与原版不符。

---

## 三、导航菜单（9 项）

| # | 标签 | 页面根类名 |
|---|---|---|
| 0 | 自动采集 | `.auto-collect-page` |
| 1 | 任务总览 | `.dashboard-grid` |
| 2 | 品牌手卡 | `.settings-layout` |
| 3 | 达人优选 | `.panel.list-panel` |
| 4 | 联系方式（带角标数字）| `.contact-layout` |
| 5 | AI 建联 | `.outreach-page` |
| 6 | 交付中心 | `.delivery-center-page` |
| 7 | 系统设置 | `.settings-page` |
| 8 | 抖店浏览器 | `.shop-browser-page.full` |

**导航实现：** `<nav>` 内为 `<button>` 列表，当前页按钮带 `.active` 类。

---

## 四、增量脚本挂载点

| 脚本 | 依赖 |
|---|---|
| `aipr-ai-outreach.js` | `.outreach-page`（页 5）+ `.outreach-banner` |
| `aipr-realtime-flow.js` | 无（固定悬浮，`position: fixed; z-index: 9000`）|

**注意：** `aipr-realtime-flow.js` 的面板固定悬浮在右下角。原版主区域是内置浏览器（大块空白），所以不遮挡；若主区域是表单密集页面，会遮挡。

---

## 五、与原版对齐的检查项

- [ ] `.app-shell` 使用 grid `232px 1fr`
- [ ] 侧边栏 232px 宽、深色 `#18201b`
- [ ] 工作区浅色 `#f2f4f2`
- [ ] CSS 变量与上表一致
- [ ] 9 个导航项，标签文字一致
- [ ] 页面根类名与上表一致
- [ ] `.outreach-page` 与 `.outreach-banner` 存在（增量脚本挂载）
- [ ] `.topbar` 含店铺状态与刷新
