#!/bin/bash
set -euo pipefail
APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_ROOT"
npm run verify
npm run mac:dir
RELEASE_DIR="$APP_ROOT/release-macos"
BUILT_APP="$RELEASE_DIR/mac-arm64/千寻.app"
APP_VERSION="$(node -p 'require("./package.json").version')"
codesign --force --deep --sign "${AIPR_SIGN_IDENTITY:--}" "$BUILT_APP"
codesign --verify --deep --strict "$BUILT_APP"
if [[ -n "${AIPR_NOTARY_PROFILE:-}" ]]; then
  if [[ -z "${AIPR_SIGN_IDENTITY:-}" ]]; then echo 'Notarization requires a Developer ID identity' >&2; exit 2; fi
  ditto -c -k --keepParent "$BUILT_APP" "$RELEASE_DIR/notary-upload.zip"
  xcrun notarytool submit "$RELEASE_DIR/notary-upload.zip" --keychain-profile "$AIPR_NOTARY_PROFILE" --wait
  xcrun stapler staple "$BUILT_APP"
fi
DMG_STAGE="$(mktemp -d "$RELEASE_DIR/package-stage.XXXXXX")"
trap 'rm -rf "$DMG_STAGE"' EXIT
ditto "$BUILT_APP" "$DMG_STAGE/千寻.app"
ln -s /Applications "$DMG_STAGE/Applications"
hdiutil create -volname '千寻' -srcfolder "$DMG_STAGE" -ov -format UDZO "$RELEASE_DIR/Qianxun-Mac-M1-$APP_VERSION-arm64.dmg"
ditto -c -k --sequesterRsrc --keepParent "$BUILT_APP" "$RELEASE_DIR/Qianxun-Mac-M1-$APP_VERSION-arm64.zip"
shasum -a 256 "$RELEASE_DIR/Qianxun-Mac-M1-$APP_VERSION-arm64.dmg" "$RELEASE_DIR/Qianxun-Mac-M1-$APP_VERSION-arm64.zip" > "$RELEASE_DIR/SHA256-$APP_VERSION.txt"
