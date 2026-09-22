# Windows x64 Python 运行时

打包 Windows 版本前，需要把 Python 运行时放到本目录。

## 目录结构（打包后）

```
runtime/windows-x64/
└── python/
    ├── python.exe
    ├── python3.dll
    ├── Lib/
    │   └── site-packages/
    │       ├── openpyxl/
    │       ├── playwright/
    │       └── pypdf/
    └── ...
```

`electron/platform-runtime.cjs` 按以下顺序查找 Python：

1. `resources/runtime/windows-x64/python/python.exe`  ← 本目录
2. `resources/runtime/python/python.exe`
3. `%LOCALAPPDATA%/Programs/aipr-buyin-cart-talent/resources/app/runtime/python/python.exe`

## 准备步骤（在 Windows 机器上执行）

### 方式一：嵌入式 Python（推荐，体积小）

```powershell
# 1. 下载 Python 3.12 embeddable package
#    https://www.python.org/downloads/windows/ → Windows installer (64-bit) → "Windows embeddable package (64-bit)"
#    解压到 runtime\windows-x64\python\

# 2. 启用 site-packages（嵌入式包默认禁用）
#    编辑 runtime\windows-x64\python\python312._pth，取消注释 import site 行：
#      python312.zip
#      .
#      Lib\site-packages
#      import site

# 3. 安装依赖
runtime\windows-x64\python\python.exe -m pip install -r requirements-windows.txt
```

### 方式二：完整 Python 安装目录（简单，体积大）

```powershell
# 1. 安装 Python 3.12 到自定义目录（不要勾选 Add to PATH）
# 2. 把整个安装目录复制到 runtime\windows-x64\python\
# 3. 安装依赖
runtime\windows-x64\python\python.exe -m pip install -r requirements-windows.txt
```

## 依赖

见 `app/requirements-windows.txt`（与 macOS 版本一致）：

```
openpyxl==3.1.5
playwright==1.60.0
pypdf==6.10.0
```

## 构建

在 Windows 机器上：

```powershell
cd app
npm install
npm run win:build     # 生成 nsis 安装包 + portable 免安装版
npm run win:dir       # 仅生成解包目录（调试用）
```

产物在 `release-windows/`。

## 注意

- **Playwright 浏览器**：`playwright install chromium` 需要单独执行，或改用系统 Chrome/Edge
  （`platform-runtime.cjs` 会自动查找系统 Edge/Chrome）
- **架构**：仅支持 x64（`platform-runtime.cjs` 的 `buildPlatformReadiness` 检查 `win32/x64`）
- **签名**：当前未配置代码签名证书，Windows SmartScreen 会提示"未知发布者"
