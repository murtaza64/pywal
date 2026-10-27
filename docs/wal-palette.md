# wal-palette/1

Shared palette contract for agent artifacts, briefs, generated visuals and app surfaces.
Code: `pywal/contract.py` (stdlib only). Helper: `bin/wal-palette` (symlink onto PATH).

## Files

Written by the fork's export (every `wal` run, every Palette Studio Apply) next to `colors.json`:

- `palette.json`: `{schema, revision, scheme, roles, highlights, terminal, checks}`
- `palette.css`: `:root{color-scheme; --wal-revision; --wal-<role>; --wal-hl1..8; --<role>; --hl1..8}`

No wallpaper path, no prose. `revision` = hash of scheme + roles + highlights.
Hosts without `colors.json` (e.g. the Mini) can receive `palette.json` alone; viewing devices keep their own appearance.

## Roles (pinned)

| Role | Use | Guarantee vs `surface` |
|---|---|---|
| `bg` | page | |
| `surface` | panels, drawing ground | |
| `raised` | fields, hover, selection | |
| `line` | rules, strokes, axes | 3:1 |
| `fg` | body text | 7:1 |
| `muted` | secondary text | 4.5:1 |
| `faint` | tertiary marks, gridlines | 3:1 |
| `accent` | links, focus, primary action | 4.5:1 |
| `on_accent` | text on an accent fill | best of bg/black/white |
| `ok` / `warn` / `risk` / `info` | status | 4.5:1; ok vs risk separated under deuteranopia/protanopia (`checks.ok_risk_cvd_safe`, false on 2/271 builtin themes: consumers keep their own ok/risk) |
| `hl1`..`hl4` | series, grouping; no meaning | 3:1; every pair ≥ 0.10 OKLab apart under normal, protan, deutan and tritan simulation (`checks.hl_distinct_safe`, false on 2/271 builtin themes with mid-grey surfaces) |
| `hl5`..`hl8` | extra decoration | 3:1 only |
| `hl1_bg`..`hl4_bg` | text-highlight fill (pair with a 2px `hlN` underline) | `fg` 7:1 on it, else equals `surface` |

Derivation: status/accent from the fork's hue-matched ANSI names (`red`, `bright_green`, ...). Highlights from raw `color0..7` (generation order): hl1..hl4 take the first four hues ≥ 50° apart in that order (manadj deck hues fill gaps) on a four-rung OKLCH lightness ladder from the 3.5:1 point outward, rung assignment chosen for the widest worst-case pair; hl5..hl8 are the remaining raw colours lifted to 3:1. Missing role = consumer default.

Artifact rules: status colour always travels with a word or glyph; chart series hl1→hl4, lines also differ by dash (solid, `6 3`, `2 3`, `8 3 2 3`), more than four series → group or facet; diagram nodes `raised` fill with an `hlN` border; radius 0.

## Use

- Live HTML/SVG: write `var(--wal-accent)` etc.; `wal-palette inject FILE` embeds one `<style id="wal-palette">` (idempotent, re-run to refresh).
- Fixed PNG/PDF: store `wal-palette snapshot` (schema, revision, colours) with the export.
- Agents: opencode core `palette/artifacts` System Context source names roles + scheme only; colour changes add no context.
- Overrides: an artifact's brand/accessibility needs win.
