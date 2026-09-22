# AIPR Pro Windows 构建验证脚本
#
# 用法（在 Windows PowerShell 中）：
#   powershell -ExecutionPolicy Bypass -File scripts/verify-windows-build.ps1
#
# 该脚本逐项检查构建前置条件，不实际打包（打包用 npm run win:build）。

$ErrorActionPreference = "Continue"

$Pass = 0
$Fail = 0
$Warn = 0

function Check($name, $ok, $detail) {
    if ($ok) {
        Write-Host "  [OK]   $name" -ForegroundColor Green
        if ($detail) { Write-Host "         $detail" -ForegroundColor DarkGray }
        $script:Pass++
    } else {
        Write-Host "  [FAIL] $name" -ForegroundColor Red
        if ($detail) { Write-Host "         $detail" -ForegroundColor DarkGray }
        $script:Fail++
    }
}

function Warn($name, $detail) {
    Write-Host "  [WARN] $name" -ForegroundColor Yellow
    if ($detail) { Write-Host "         $detail" -ForegroundColor DarkGray }
    $script:Warn++
}

Write-Host ""
Write-Host "AIPR Pro Windows 构建验证" -ForegroundColor Cyan
Write-Host "=========================" -ForegroundColor Cyan
Write-Host ""

# ---------- 1. 平台 ----------

Write-Host "[1/7] 平台与架构" -ForegroundColor White

$isWindows = $env:OS -eq "Windows_NT"
Check "运行在 Windows" $isWindows $env:OS

$arch = $env:PROCESSOR_ARCHITECTURE
Check "x64 架构" ($arch -eq "AMD64") "PROCESSOR_ARCHITECTURE=$arch"

# ---------- 2. Node 环境 ----------

Write-Host ""
Write-Host "[2/7] Node.js 环境" -ForegroundColor White

$node = Get-Command node -ErrorAction SilentlyContinue
Check "node 可用" ($null -ne $node) $(if ($node) { $node.Source } else { "未找到 node" })

if ($node) {
    $nodeVersion = (node --version) -replace '^v', ''
    $major = [int]($nodeVersion -split '\.')[0]
    Check "Node >= 20" ($major -ge 20) "当前 v$nodeVersion"
}

$npm = Get-Command npm -ErrorAction SilentlyContinue
Check "npm 可用" ($null -ne $npm) $(if ($npm) { $npm.Source } else { "未找到 npm" })

# ---------- 3. 项目文件 ----------

Write-Host ""
Write-Host "[3/7] 项目文件" -ForegroundColor White

$appDir = Join-Path $PSScriptRoot "..\app"
Check "app 目录存在" (Test-Path $appDir) $appDir

$pkgJson = Join-Path $appDir "package.json"
Check "package.json 存在" (Test-Path $pkgJson) $pkgJson

if (Test-Path $pkgJson) {
    $pkg = Get-Content $pkgJson -Raw | ConvertFrom-Json
    Check "win:build 脚本存在" ($null -ne $pkg.scripts.'win:build') $pkg.scripts.'win:build'
    Check "win 打包配置存在" ($null -ne $pkg.build.win) ""
    if ($pkg.build.win) {
        $targets = ($pkg.build.win.target | ForEach-Object { $_.target }) -join "+"
        Check "win target 含 nsis 与 portable" ($targets -eq "nsis+portable") $targets
        $winArch = $pkg.build.win.target[0].arch -join ","
        Check "win 架构为 x64" ($winArch -eq "x64") $winArch
    }
    $res = $pkg.build.extraResources | ForEach-Object { $_.to }
    Check "extraResources 含 windows-x64" ($res -contains "runtime/windows-x64") ($res -join ", ")
    Check "extraResources 含 backend" ($res -contains "backend") ($res -join ", ")
}

# ---------- 4. 前端产物 ----------

Write-Host ""
Write-Host "[4/7] 前端构建产物" -ForegroundColor White

$distDir = Join-Path $appDir "dist"
Check "dist 目录存在" (Test-Path $distDir) $distDir

if (Test-Path $distDir) {
    $indexHtml = Join-Path $distDir "index.html"
    Check "dist/index.html 存在" (Test-Path $indexHtml) $indexHtml

    $appJs = Join-Path $distDir "assets\app.js"
    Check "dist/assets/app.js 存在" (Test-Path $appJs) $appJs

    foreach ($extra in @("aipr-ai-outreach.js", "aipr-realtime-flow.js")) {
        $p = Join-Path $distDir $extra
        Check "增量脚本 $extra 存在" (Test-Path $p) $p
    }
}

# ---------- 5. Python 运行时 ----------

Write-Host ""
Write-Host "[5/7] Python 运行时" -ForegroundColor White

$pyDir = Join-Path $appDir "runtime\windows-x64\python"
$pyExe = Join-Path $pyDir "python.exe"

if (Test-Path $pyExe) {
    Check "内置 Python 存在" $true $pyExe
    $pyVer = & $pyExe --version 2>&1
    Check "Python 可执行" ($LASTEXITCODE -eq 0) $pyVer

    # 依赖检查
    foreach ($mod in @("openpyxl", "playwright", "pypdf")) {
        $r = & $pyExe -c "import $mod; print('ok')" 2>&1
        Check "依赖 $mod 已安装" ($r -match "ok") $(if ($r -match "ok") { "" } else { "缺失，运行 pip install -r requirements-windows.txt" })
    }
} else {
    Check "内置 Python 存在" $false "未找到 $pyExe"
    Warn "准备运行时" "见 app/runtime/windows-x64/README.md"
}

# ---------- 6. 浏览器 ----------

Write-Host ""
Write-Host "[6/7] 系统浏览器" -ForegroundColor White

$chrome = @(
    "$env:PROGRAMFILES\Google\Chrome\Application\chrome.exe",
    "${env:PROGRAMFILES(X86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

$edge = @(
    "$env:PROGRAMFILES\Microsoft\Edge\Application\msedge.exe",
    "${env:PROGRAMFILES(X86)}\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($chrome) {
    Check "Chrome 可用" $true $chrome
} elseif ($edge) {
    Check "Edge 可用（Chrome 未找到）" $true $edge
} else {
    Check "Chrome 或 Edge 可用" $false "两者都未找到，platform-runtime.cjs 无法启动内置浏览器"
}

# ---------- 7. 后端脚本 ----------

Write-Host ""
Write-Host "[7/7] 后端脚本" -ForegroundColor White

$backendDir = Join-Path $appDir "backend"
Check "backend 目录存在" (Test-Path $backendDir) $backendDir

foreach ($script in @(
    "collect_and_contact_pipeline.py",
    "collect_buyin_creators_cdp.py",
    "scrape_buyin_profile_contact_icons_cdp.py",
    "finalize_creator_delivery.py"
)) {
    $p = Join-Path $backendDir $script
    Check "脚本 $script 存在" (Test-Path $p) ""
}

# ---------- 汇总 ----------

Write-Host ""
Write-Host "=========================" -ForegroundColor Cyan
Write-Host "通过: $Pass   失败: $Fail   警告: $Warn" -ForegroundColor $(if ($Fail -eq 0) { "Green" } else { "Red" })
Write-Host ""

if ($Fail -eq 0) {
    Write-Host "前置条件就绪，可以执行构建：" -ForegroundColor Green
    Write-Host "  cd app" -ForegroundColor White
    Write-Host "  npm install" -ForegroundColor White
    Write-Host "  npm run win:build" -ForegroundColor White
    Write-Host ""
    Write-Host "产物将输出到 app\release-windows\" -ForegroundColor White
    exit 0
} else {
    Write-Host "存在 $Fail 项失败，请先修复后再构建。" -ForegroundColor Red
    Write-Host "详见 WINDOWS-BUILD.md" -ForegroundColor White
    exit 1
}
