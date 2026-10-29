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
mv "$OUT/.electron/Electron.app" "$APP"
# Electron (MIT) and Chromium licences travel inside the app for redistribution.
mkdir -p "$APP/Contents/Resources/licenses"
cp "$OUT/.electron/LICENSE" "$APP/Contents/Resources/licenses/electron-LICENSE"
cp "$OUT/.electron/LICENSES.chromium.html" "$APP/Contents/Resources/licenses/"
cp "${HERE:h:h}/LICENSE.md" "$APP/Contents/Resources/licenses/walstudio-LICENSE.md"
rm -rf "$OUT/.electron"
mkdir -p "$APP/Contents/Resources/app"
# App icon (Electron's Info.plist already names electron.icns).
cp "$HERE/icon/WalStudio.icns" "$APP/Contents/Resources/electron.icns"
cp "$HERE"/{main.cjs,preload.cjs,package.json} "$APP/Contents/Resources/app/"
# The bundle runs the Studio from the pywal checkout it records: this one by default; a release build
# records the documented clone location instead (WALSTUDIO_BUNDLE_PYWAL='~/pywal'). WALSTUDIO_PYWAL or
# "pywal" in config.json override it at run time.
python3 - "$APP/Contents/Resources/app/package.json" "${WALSTUDIO_BUNDLE_PYWAL:-${HERE:h:h}}" <<'PY'
import json, sys
p, root = sys.argv[1], sys.argv[2]
d = json.load(open(p)); d["walstudio"] = {"pywal": root}; json.dump(d, open(p, "w"), indent=2)
PY
PLIST=$APP/Contents/Info.plist
/usr/libexec/PlistBuddy -c "Set :CFBundleName WalStudio" -c "Set :CFBundleDisplayName WalStudio" -c "Set :CFBundleIdentifier io.github.murtaza64.walstudio" -c "Set :CFBundleShortVersionString 0.1.0" "$PLIST"
mv "$APP/Contents/MacOS/Electron" "$APP/Contents/MacOS/WalStudio"
/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable WalStudio" "$PLIST"
# Bundle contents changed after Electron's ad-hoc signature; re-sign ad hoc so macOS will launch it.
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
echo "$APP"
