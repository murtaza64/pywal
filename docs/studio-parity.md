# Palette Studio: parity inventory

Run: `uv run -m pywal.studio [--port 4790] [--allow-apply]`. Loopback only. Preview-only unless `--allow-apply`.

## Sources (read 2026-10-27)

- Engine: `murtaza64/pywal` (pywal16 fork, 71 commits ahead), on disk `~/pywal`. Flags `pywal/args.py`; persisted settings `OPTIONS_TO_SAVE` -> `colors.json.settings`.
- Wrappers (`~/dotfiles`): `bin/wallpaper`, `bin/walcolor`, `bin/wofi-wallpaper`, `zsh/aliases.zsh` (`wal`, `walm`, `wals`).
- Consumers: `kitty/kitty.conf` + `per-machine.conf`, `nvim/lua/pywalcolors.lua`, `tmux/theme.py`, `python/murtaza/colors.py`, `opencode/themes/pywal.json`, `hypr/hyprland.conf`, `waybar/style.css`, `wofi/*.css`, es-desktop `src/appearance.ts`.
- Prior GUI: `~/pywal/webui` + `scripts/palette_web_flask.py` (generate/shuffle/browse), `yellow_zone` tuner.

## Commands -> stories -> studio

| CLI | Story | Outputs / reload | Studio |
|---|---|---|---|
| `wallpaper` | random wallpaper from `~/wallpapers`, wrapper defaults (colorthief, lighten, contrast 1.5) | full run | Random |
| `wallpaper <file>` | pick a wallpaper | full run | strip, ←/→; tuning resets to wrapper defaults |
| `wallpaper --flag…` | re-generate current wallpaper with tweaks, no cache | full run | any control |
| `walm` (`--modify`) | tweak current palette, keep saved settings | no wallpaper set | "Keep tuning" + controls |
| `wals` (`--modify --shuffle`) | shuffle post-processing | | Shuffle / Shuffle all (same ranges) |
| `--light/--dark`, `--contrast`, `--saturate`, `--brightness`, `--shading`, `--choose`, `--gen`, `--si`, `--bg-strategy`, `--bg-lightness`, `--bg-chroma`, `--seed` | tune generator | | rail controls; seed reroll |
| `--bg/--fg` | pin background/foreground | | slot pin (any ANSI slot, superset) |
| `-S/--show`, `--print-term-colors` | inspect current | | original layer, Compare, swatches with live band |
| `wofi-wallpaper` (Linux) | thumbnail grid picker | | wallpaper strip |
| `walcolor N\|key` | read one colour | `colors.properties` | slot readout (CLI unchanged) |
| `-R/--restore` | restore previous | | Revert (draft); Undo list loads any Apply backup (`~/.cache/pywal-studio/backups`) as the draft, applied through the normal plan + proofs |
| `--theme`, `-p/--save-theme` | builtin/saved themes | `~/.config/wal/colorschemes` (empty on this Mac) | Themes menu on the Wallpaper title: single-column rows with a color0-7 band; filter, load as draft for the chosen wallpaper, save draft (gated like Apply). Builtin themes get named ANSI slots + derived surfaces/diff so every template renders |
| (cache) | browse cached schemes | `<live>/schemes/*.json` | Film strip: solid color0-7 band under wallpapers with a cached scheme. Themes menu `Cached` group, newest first: loads the scheme exactly, with its generation settings, for its wallpaper (or the current one if its wallpaper is not served) |
| `-c` | clear cached schemes | | not planned |
| `-i <dir> --iterative/--recursive` | cycle dir | | not planned (strip covers it) |
| `-a/--alpha`, `--vte`, `-t`, `-o/--then` | terminal alpha, tty, hooks | | not planned unless asked |
| `-n/-s/-e` | skip wallpaper/sequences/reload | | per-target checkboxes |
| `WAL_KITTY_SET_BACKGROUND` + `magick -blur 0x16` + kitty `background_tint 0.95` | blurred, darkened terminal glass | `wallpaper.blurred` | Blur + Darken sliders, Exact render |

## Sync targets

| Target | Mechanism | Proof | This Mac |
|---|---|---|---|
| files | write `colors.json` + templates into the live cache, `wal`, `wallpaper` link; backup first | re-read `colors.json` | yes |
| kitty | `kitty @ --to /tmp/kitty-*.sock set-colors --all --configured colors-kitty.conf background_tint=…`, `set-background-image` | `get-colors` per socket | 1 instance |
| es-desktop | none: polls `colors.json`, blurs wallpaper itself | `~/Library/Application Support/Editspace/appearance-receipt.json` (es-appearance-receipt/1: background, foreground, wal revision; written by the app on each change). `verified` = served background matches and a page's `applied[].walRevision` equals the revision Apply wrote; background only = `loaded`; no receipt = `sent` | running; receipt needs the es-desktop pin |
| pywalfox | `pywalfox update` | none (native messaging, no readback) | installed + host manifest |
| tmux | `tmux source-file ~/.config/tmux/tmux.conf` | exit status | running |
| opencode, nvim, delta, jjui | read template outputs on next load | file written | via files |
| system wallpaper | `pywal.wallpaper.change` (macOS rewrites wallpaper plist, restarts WallpaperAgent) | | off by default |
| hyprland, waybar, mako, wofi | `reload.env` on Linux | | personal Linux machine only |

`background_tint` via `set-colors` confirmed with kitty 0.47.1 `kitty.colors.parse_colors` (no live change).

## Decisions

- Home: the pywal fork (`pywal/studio/`), stdlib server, no new runtime deps. es-app stays a consumer.
- Safety: `PYWAL_CACHE_DIR` points at scratch before import; generation and template export never touch the live cache. Apply is a startup flag plus a confirm showing the exact plan.
- Viewing device vs host: studio chrome is fixed neutral grey, never the viewer's or host's palette. Apply edits the host the studio runs on, so the instance that applies must run on the machine whose theme it is (laptop). A Mini instance is for development against its own or a fixture cache (`--live-dir`).
- Privacy: loopback bind, images served only from `~/wallpapers`, the live wallpaper and scratch.

## Proof run (2026-10-27, laptop, no-change draft)

Draft regenerated from live settings + seed: 0 colour diffs; rendered templates byte-identical except `colors.json` (adds `studio`).
Apply: files verified (backup kept, now in `~/.cache/pywal-studio/backups/20261027-170938`), kitty verified (`get-colors` identical to before), blurred wallpaper pixel-identical (RMSE 0) now in `~/.cache/wal/blurred/`, es-desktop/pywalfox/tmux sent.

## Open

- es-desktop proof: receipt (opencode 540b5f8a) + page acknowledgement `applied[]` (RHC 1318cf86); proven on fixture with a stand-in app, not live.
- pywalfox proof: no readback; visual only.
- Next slices: light-mode es-app variant.
