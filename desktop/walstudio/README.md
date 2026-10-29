# WalStudio

Palette Studio as a macOS app. The app starts its own Studio backend on a free loopback port and stops it on quit.

## Build and run

    desktop/walstudio/bundle.sh          # -> desktop/walstudio/dist/WalStudio.app (unsigned, ad-hoc)
    open desktop/walstudio/dist/WalStudio.app

Needs: this pywal checkout, `uv`, ImageMagick (`/opt/homebrew/bin/magick`). Electron 42.3.3 comes from `~/Library/Caches/electron`.

## Where it reads and writes

- Wallpapers: File > Choose Wallpapers… (folder or one image); remembered in `~/Library/Application Support/WalStudio/config.json`.
- Apply writes theme files to its own profile (`…/WalStudio/profile/live`) unless `WALSTUDIO_LIVE_DIR` or `liveDir` in config points elsewhere.
- Targets: `files` by default; `files,es-desktop` when liveDir is `~/.cache/wal` (Editspace follows only that cache). Override `WALSTUDIO_TARGETS` or `targets` in config; the backend refuses others.
- Backups (Undo), scratch and the backend log live under `~/Library/Application Support/WalStudio/`.

Apps opened from Finder do not see shell variables: put settings in `~/Library/Application Support/WalStudio/config.json`, e.g. `{"pywal": "~/pywal"}`.

The app is unsigned: the first time, right-click > Open and confirm.

Release build (records `~/pywal` rather than this checkout): `WALSTUDIO_BUNDLE_PYWAL='~/pywal' desktop/walstudio/bundle.sh`. Users clone the fork to `~/pywal`, or set `pywal` in config.json.

Overrides: `WALSTUDIO_PYWAL`, `WALSTUDIO_PYTHON`, `WALSTUDIO_WALLPAPERS`, `WALSTUDIO_LIVE_DIR`, `WALSTUDIO_TARGETS`, `WALSTUDIO_ES_RECEIPT`.
