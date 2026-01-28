#!/usr/bin/env -S uv run --script

"""Visualize ensure_contrast() adjustments.

Prints ANSI color squares for a seed candidate list, then applies the same
contrast adjustment logic as `pywal.palette.ensure_contrast()` for a range
of ratios.

This is a terminal-only script.
"""

from __future__ import annotations

import colorsys

from pywal import colorthief
from pywal import palette as palette_mod
from pywal import util
from pywal.color import Color
RESET = "\033[0m"


def _cell(bg: Color, fg: Color, text: str, width: int = 9) -> str:
    br, bgc, bb = bg.rgb8
    fr, fg_c, fb = fg.rgb8
    t = text[:width].ljust(width)
    return f"\033[48;2;{br};{bgc};{bb}m\033[38;2;{fr};{fg_c};{fb}m{t}{RESET}"


def cells_on_bg(bg: Color, fgs: list[Color], text: str = "xxx") -> str:
    # Use the fg hex as text by default for readability.
    out = []
    for fg in fgs:
        label = fg.hex_color if text == "hex" else text
        out.append(_cell(bg, fg, label))
    return "".join(out)


def _binary_luminance_adjust(
    luminance_desired: float,
    hue: float,
    s_min: float,
    s_max: float,
    v_min: float,
    v_max: float,
    iterations: int = 10,
) -> Color:
    s = (s_min + s_max) / 2
    v = (v_min + v_max) / 2
    for _ in range(iterations):
        s = (s_min + s_max) / 2
        v = (v_min + v_max) / 2
        if Color.from_srgb01(colorsys.hsv_to_rgb(hue, s, v)).w3_luminance >= luminance_desired:
            s_min = s
            v_max = v
        else:
            s_max = s
            v_min = v
    return Color.from_srgb01(colorsys.hsv_to_rgb(hue, s, v))


def ensure_contrast_demo(candidates: list[Color], background: Color, contrast: float, light: bool) -> list[Color]:
    bg_lum = background.w3_luminance
    if light:
        lum_desired = (bg_lum + 0.05) / float(contrast) - 0.05
    else:
        lum_desired = (bg_lum + 0.05) * float(contrast) - 0.05

    if lum_desired >= 0.99:
        lum_desired = 0.99
    if lum_desired <= 0.01:
        lum_desired = 0.01

    out = candidates[:]
    for i, c in enumerate(out):
        if light and c.w3_luminance <= lum_desired:
            continue
        if (not light) and c.w3_luminance >= lum_desired:
            continue

        h, s, v = colorsys.rgb_to_hsv(float(c.red), float(c.green), float(c.blue))

        if (
            (not light)
            and Color.from_srgb01(colorsys.hsv_to_rgb(h, s, 1)).w3_luminance >= lum_desired
        ):
            out[i] = _binary_luminance_adjust(lum_desired, h, s, s, v, 1)
        elif not light:
            out[i] = _binary_luminance_adjust(lum_desired, h, 0, s, 1, 1)
        else:
            out[i] = _binary_luminance_adjust(lum_desired, h, s, 1, 0, v)

    return out


def line(label: str, colors: list[Color]) -> None:
    hexes = " ".join(c.hex_color for c in colors)
    print(f"{label:<16} {cells_on_bg(Color.from_hex('#000000'), colors, text='hex')}  {hexes}")


def dump_luminance(colors: list[Color]) -> None:
    parts = [f"{c.hex_color}:{c.w3_luminance:.3f}" for c in colors]
    print(" ".join(parts))


def main() -> None:
    wal_path = util.get_cache_file("wal")
    try:
        wallpaper = util.read_file(wal_path)[0].strip()
    except Exception as e:
        raise SystemExit(f"Failed to read current wallpaper from {wal_path}: {e}")

    colors = colorthief.seed(wallpaper)
    background = Color(util.image_average_color(wallpaper))
    background_darker = background.darken_amount(0.12)

    def _yiq(c: Color) -> float:
        return float(colorsys.rgb_to_yiq(*c.srgb)[0])

    darkest = min(colors, key=_yiq)
    brightest_pool = [c for c in colors if c != darkest]
    brightest = max(brightest_pool if brightest_pool else colors, key=_yiq)
    candidates = [c for c in colors if c != darkest and c != brightest]

    ratios = [1.5, 2.0, 3.0, 4.5, 7.0, 10.0, 14.0, 21.0]

    print("Contrast Adjustment Demo")
    print(f"Wallpaper: {wallpaper}")
    print(f"Avg bg:    {background.hex_color}:{background.w3_luminance:.3f}")
    print(f"Avg bg-:   {background_darker.hex_color}:{background_darker.w3_luminance:.3f}")
    print()

    print(f"darkest:   {darkest.hex_color}:{darkest.w3_luminance:.3f}")
    print(f"brightest: {brightest.hex_color}:{brightest.w3_luminance:.3f}")
    print()

    print("candidates on avg bg (fg text is hex)")
    print(cells_on_bg(background, candidates, text="hex"))
    dump_luminance(candidates)
    print()

    for light in (False, True):
        mode = "dark theme" if not light else "light theme"
        print(mode)
        print("-" * len(mode))

        pipeline_bg = palette_mod.adjust_background(darkest, light)
        backgrounds = [
            ("avg", background),
            ("avg-", background_darker),
            ("bg", pipeline_bg),
        ]

        for bg_label, bg in backgrounds:
            print(f"base {bg_label:<4} {bg.hex_color}:{bg.w3_luminance:.3f}")
            for r in ratios:
                adjusted = ensure_contrast_demo(candidates, bg, r, light)
                print(f"ratio {r:<4} {cells_on_bg(bg, adjusted, text='hex')}")
                dump_luminance(adjusted)
            print()


if __name__ == "__main__":
    main()
