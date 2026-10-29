# WalStudio

Palette Studio as a macOS app. The app starts its own Studio backend on a free loopback port and stops it on quit.

## Build and run

    desktop/walstudio/bundle.sh          # -> desktop/walstudio/dist/WalStudio.app (unsigned, ad-hoc)
    open desktop/walstudio/dist/WalStudio.app

Needs: this pywal checkout, `uv`, ImageMagick (`/opt/homebrew/bin/magick`). Electron 42.3.3 comes from `~/Library/Caches/electron`.

## Where it reads and writes

- Wallpapers: File > Choose Wallpapers… (folder or one image); remembered in `~/Library/Application Support/WalStudio/config.json`.
- Apply writes theme files to its own profile (`…/WalStudio/profile/live`) unless `WALSTUDIO_LIVE_DIR` or `liveDir` in config points elsewhere.
- Targets: `files,es-desktop` by default (`WALSTUDIO_TARGETS`); the backend refuses others.
- Backups (Undo), scratch and the backend log live under `~/Library/Application Support/WalStudio/`.

Overrides: `WALSTUDIO_PYWAL`, `WALSTUDIO_PYTHON`, `WALSTUDIO_WALLPAPERS`, `WALSTUDIO_LIVE_DIR`, `WALSTUDIO_TARGETS`, `WALSTUDIO_ES_RECEIPT`.
