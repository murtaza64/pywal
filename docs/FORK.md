# What this fork changes

Fork of [eylles/pywal16](https://github.com/eylles/pywal16) (itself a fork of [dylanaraps/pywal](https://github.com/dylanaraps/pywal)), MIT. Base: pywal16 `3207382`. Everything below is relative to that base.

## Colour generation

- One backend: a built-in colorthief variant (`pywal/colorthief.py`). The pywal16 backends (`colorthief`, `colorz`, `fast_colorthief`, `haishoku`, `modern_colorthief`, `okthief`, `schemer2`, `wal`) and `--backend` are removed.
- ANSI association: generated colours are matched to the nearest red, green, yellow, blue, magenta and cyan (OKLCH hue), so colour 1 reads as red, 2 as green, and so on. A hue with no close match is interpolated from its neighbours.
- Named slots in `colors.json`: `red`, `bright_red`, … `bright_white`, plus surfaces (`surface0..5`, `subsurface0..`) and diff colours for templates. `color0..15` remain.
- Background: OKLCH lightness and chroma, set from the image or by `--bg-lightness` / `--bg-chroma`; `--bg-strategy average` uses the image average instead of the darkest candidate.
- Reproducible: `--seed N`; the seed and settings are saved in `colors.json` and reused by `--modify`.

## Command line

New or changed flags (see `uv run -m pywal -h`):

| Flag | Change |
|---|---|
| `--image/-i`, `--restore/-R`, `--wallpaper/-w`, `--save-theme/-p`, `--then/-o`, `--clear-cache/-c`, `--quiet/-q`, `--version/-v`, `--alpha/-a`, `--bg/-b` | long names added; behaviour as in pywal16 |
| `--no-set-wallpaper/-n`, `--skip-sequences/-s`, `--skip-reload/-e`, `--skip-tty/-t` | long names added |
| `--light/-l`, `--dark` | `--dark` overrides a saved `--light` |
| `--saturate` | now `-100..100` (was `-1.0..1.0`) |
| `--brightness` | new: minimum palette brightness |
| `--contrast` | default `2.0` (pywal16: off); `0` disables. Needs ImageMagick |
| `--shading {darken,lighten}` | replaces `--cols16`; default `lighten` |
| `--choose`, `--generation-strategy/--gen`, `--subtractive-initial/--si` | new: how the 8 base colours are picked |
| `--bg-strategy`, `--bg-lightness`, `--bg-chroma`, `--seed` | new |
| `--modify`, `--shuffle [post|all]` | new: retune the current scheme; randomise settings |
| `--show/-S`, `--print-term-colors` | replace `--preview` |
| `--no-cache` | new: always regenerate |
| `--reload/-r` | reloads open apps and exits (pywal16: deprecated) |
| `--debug` | new |
| removed | `--backend`, `--cols16`, `--preview` |

## Templates

- Added: `colors-opencode.json`, `colors-jjui.toml`, `delta.gitconfig`, `colors.py`.
- Changed: `colors-kitty.conf` (named slots, tab bar).
- Removed from this fork (still in pywal16): alacritty, foot, fuzzel, ghostty, konsole, leftwm, mako, nqq, oomox, polybar, putty, retroarch, rio, rofi, speedcrunch, sway, themer.js, tilix, tofi, tty.sh, vscode, dmenu/dwl/dwm/st/tabbed headers, vim, zathura, zed, `Colors.hs`. Copy them from pywal16 into `~/.config/wal/templates/` if you use them.

## New: wal-palette/1

Every export also writes `palette.json` and `palette.css`: semantic roles (`bg`, `surface`, `fg`, `accent`, `ok`, `warn`, `risk`, …) with contrast guarantees, for documents and apps. See [wal-palette.md](wal-palette.md).

## New: Palette Studio and WalStudio

A local web UI (`uv run -m pywal.studio`) and a macOS app around it. See [walstudio.md](walstudio.md).

## Also in the tree

- `webui/`, `scripts/`: earlier experiments (palette tuning, contrast demos). Not part of the CLI or Studio.
- `color-test.html`: a static colour test page.
- Removed: `donation.py`, `eastereggs.py`, CI configuration.

## Provenance

- Code added in this fork: written by the fork author (git history from `3207382`), MIT.
- `pywal/colorschemes/`, the remaining templates and all other pywal code: from pywal / pywal16, MIT.
- `desktop/walstudio/icon/`: drawn by `make.py` in this repo (no third-party artwork).
- Electron (WalStudio app shell): downloaded at build time, not stored in the repo; MIT.
- No wallpapers or other images are shipped; screenshots in the docs use generated test images.
