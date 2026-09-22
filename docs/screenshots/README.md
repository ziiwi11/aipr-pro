# 截图证据

## 对比验证

| 文件 | 内容 |
|---|---|
| `00-original-ui.png` | **原版界面**（已安装应用，CDP 截图）——对齐基准 |
| `03-new-shell.png` | **重写版界面**——与原版对比 |

**对齐结果：**

| 项 | 原版 | 重写版 |
|---|---|---|
| 布局 | `grid: 232px 1208px` | `232px 1208px` |
| 侧边栏宽度 | 232px | 232px |
| 侧边栏背景 | `#18201b` | `#18201b` |
| 工作区背景 | `rgb(242,244,242)` | `rgb(242,244,242)` |
| 导航项 | 9 个 | 9 个（标签一致）|

## 9 个页面

逐页截图，验证路由与根类名：

| 文件 | 页面 | 根类名 |
|---|---|---|
| `10-page-auto-collect.png` | 自动采集 | `.auto-collect-page` |
| `11-page-dashboard.png` | 任务总览 | `.dashboard-grid` |
| `12-page-brand-card.png` | 品牌手卡 | `.settings-layout` |
| `13-page-creators.png` | 达人优选 | `.panel.list-panel` |
| `14-page-contacts.png` | 联系方式 | `.contact-layout` |
| `15-page-outreach.png` | AI 建联 | `.outreach-page` |
| `16-page-delivery.png` | 交付中心 | `.delivery-center-page` |
| `17-page-settings.png` | 系统设置 | `.settings-page` |
| `18-page-browser.png` | 抖店浏览器 | `.shop-browser-page.full` |

## 增量脚本挂载证据

`15-page-outreach.png` 可见增量脚本 `aipr-ai-outreach.js` 注入的
「雷神 AI 建联系统」面板（6 个指标卡 + 操作按钮 + 达人选择 + 运行历史），
证明新界面保留了 `.outreach-page` / `.outreach-banner` 挂载点。

## 未截到的部分

**内置浏览器视图（`WebContentsView`）无法通过 Playwright 截图** ——
它是 Electron 原生层，不在网页渲染树内。

替代验证方式（API 层）：

```javascript
await window.aiprDesktop.layoutEmbeddedShop({shop:'A', bounds:{...}})
// 返回: {"ok":true,"shop":"A",
//        "bounds":{"x":256,"y":199,"width":1160,"height":550},
//        "url":"https://fxg.jinritemai.com/login/common?from=buyin"}
```

并通过 CDP 确认两个抖店视图已加载登录页。
