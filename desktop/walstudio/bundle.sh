#!/bin/zsh
# Build an unpacked macOS WalStudio.app from Electron's prebuilt app (no npm install, unsigned).
# Usage: desktop/walstudio/bundle.sh [electron-zip] [out-dir]
set -euo pipefail
HERE=${0:a:h}
ZIP=${1:-$(ls ~/Library/Caches/electron/*/electron-v42.3.3-darwin-arm64.zip | head -1)}
OUT=${2:-$HERE/dist}
APP=$OUT/WalStudio.app
rm -rf "$APP" && mkdir -p "$OUT"
ditto -x -k "$ZIP" "$OUT/.electron"
mv "$OUT/.electron/Electron.app" "$APP" && rm -rf "$OUT/.electron"
mkdir -p "$APP/Contents/Resources/app"
# App icon (Electron's Info.plist already names electron.icns).
cp "$HERE/icon/WalStudio.icns" "$APP/Contents/Resources/electron.icns"
cp "$HERE"/{main.cjs,preload.cjs,package.json} "$APP/Contents/Resources/app/"
# The bundle runs the Studio from this pywal checkout (WALSTUDIO_PYWAL overrides it).
python3 - "$APP/Contents/Resources/app/package.json" "${HERE:h:h}" <<'PY'
import json, sys
p, root = sys.argv[1], sys.argv[2]
d = json.load(open(p)); d["walstudio"] = {"pywal": root}; json.dump(d, open(p, "w"), indent=2)
PY
PLIST=$APP/Contents/Info.plist
/usr/libexec/PlistBuddy -c "Set :CFBundleName WalStudio" -c "Set :CFBundleDisplayName WalStudio" -c "Set :CFBundleIdentifier com.murtaza.walstudio" -c "Set :CFBundleShortVersionString 0.1.0" "$PLIST"
mv "$APP/Contents/MacOS/Electron" "$APP/Contents/MacOS/WalStudio"
/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable WalStudio" "$PLIST"
# Bundle contents changed after Electron's ad-hoc signature; re-sign ad hoc so macOS will launch it.
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
echo "$APP"
