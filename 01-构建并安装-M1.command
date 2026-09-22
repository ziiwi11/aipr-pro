#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
KIT_DIR="$SCRIPT_DIR"
APP_DIR="$KIT_DIR/app"
USER_DATA="$HOME/Library/Application Support/AIPR Pro 达人运营系统"
USER_RUNTIME="$USER_DATA/runtime/python"

pause_on_exit() {
  status=$?
  echo
  if [[ $status -eq 0 ]]; then
    echo "处理完成。"
  else
    echo "处理失败，错误码：$status"
  fi
  if [[ -t 0 ]]; then
    read -r -p "按回车键关闭窗口……" _
  fi
  exit $status
}
trap pause_on_exit EXIT

echo "=== AIPR Pro M1 原生版构建与迁移 ==="

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "本构建包仅适用于 Apple Silicon（M1/M2/M3/M4）Mac。"
  exit 2
fi

for command_name in node npm codesign hdiutil ditto xattr; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "缺少命令：$command_name"
    echo "请先安装 Node.js 20 或更高版本，以及 arm64 Python 3.12。"
    exit 3
  fi
done

if command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.12)"
elif [[ -x "/opt/homebrew/bin/python3.12" ]]; then
  PYTHON_BIN="/opt/homebrew/bin/python3.12"
else
  echo "缺少 Apple Silicon Python 3.12。"
  exit 3
fi

NODE_VERSION="$(node --version)"
NODE_MAJOR="${NODE_VERSION#v}"
NODE_MAJOR="${NODE_MAJOR%%.*}"
if [[ "$NODE_MAJOR" -lt 20 ]]; then
  echo "Node.js 版本过低：$(node --version)。请安装 Node.js 20 或更高版本。"
  exit 3
fi

if ! "$PYTHON_BIN" -c 'import platform, sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and platform.machine() == "arm64" else 1)'; then
  echo "当前 Python 不是 arm64 Python 3.12，请安装 Apple Silicon 版 Python 3.12。"
  exit 4
fi

if [[ ! -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" && ! -x "/Applications/Chromium.app/Contents/MacOS/Chromium" ]]; then
  echo "未找到 Google Chrome 或 Chromium，请先安装 Chrome。"
  exit 5
fi

echo "[1/5] 安装 AIPR Python 运行环境……"
mkdir -p "$USER_DATA/runtime"
"$PYTHON_BIN" -m venv "$USER_RUNTIME"
"$USER_RUNTIME/bin/python3" -m pip install --upgrade pip
"$USER_RUNTIME/bin/python3" -m pip install --no-cache-dir -r "$APP_DIR/requirements-macos.txt"
"$USER_RUNTIME/bin/python3" -c 'import openpyxl, playwright, pypdf; print("Python 依赖检查通过")'

echo "[2/5] 保留本机任务数据。历史迁移可单独运行 restore_data.py。"

echo "[3/5] 安装 Mac 打包依赖……"
cd "$APP_DIR"
chmod +x "$APP_DIR/runtime/macos-arm64/python/bin/python3"
npm ci --no-audit --no-fund

echo "[4/5] 构建并进行本机签名……"
npm run mac:dir
APP_PATH="$APP_DIR/release-macos/mac-arm64/AIPR Pro 达人运营系统.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "未找到构建后的 .app。"
  exit 6
fi
codesign --force --deep --sign - "$APP_PATH"
codesign --verify --deep --strict "$APP_PATH"
xattr -dr com.apple.quarantine "$APP_PATH" 2>/dev/null || true

echo "[5/5] 生成 DMG 和 ZIP……"
RELEASE_DIR="$APP_DIR/release-macos"
DMG_PATH="$RELEASE_DIR/AIPR-Pro-Mac-M1-1.0.0-arm64.dmg"
ZIP_PATH="$RELEASE_DIR/AIPR-Pro-Mac-M1-1.0.0-arm64.zip"
DMG_STAGE="$(mktemp -d "$RELEASE_DIR/dmg-stage.XXXXXX")"
ditto "$APP_PATH" "$DMG_STAGE/AIPR Pro 达人运营系统.app"
ln -s /Applications "$DMG_STAGE/Applications"
hdiutil create -volname "AIPR Pro 达人运营系统" -srcfolder "$DMG_STAGE" -ov -format UDZO "$DMG_PATH"
ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ZIP_PATH"

echo
echo "Mac 安装包：$DMG_PATH"
echo "备用 ZIP：$ZIP_PATH"
echo "正在打开 DMG；请把应用拖入 Applications。"
open "$DMG_PATH"
