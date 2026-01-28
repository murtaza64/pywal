#!/usr/bin/env -S uv run --script

"""Visual demo for legacy vs OKLab/OKLCH-style operations.

This is a terminal-only script: it prints ANSI colored squares and hex values.

It intentionally does NOT change pywal behavior; it re-implements proposed
OKLab/OKLCH operations locally for side-by-side comparison.
"""

from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass

from pywal import util


RESET = "\033[0m"


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _srgb_to_linear(u: float) -> float:
    if u <= 0.04045:
        return u / 12.92
    return ((u + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(u: float) -> float:
    if u <= 0.0031308:
        return 12.92 * u
    return 1.055 * (u ** (1.0 / 2.4)) - 0.055


def hex_to_srgb01(hex_color: str) -> tuple[float, float, float]:
    r8, g8, b8 = util.hex_to_rgb(hex_color)
    return (r8 / 255.0, g8 / 255.0, b8 / 255.0)


def srgb01_to_hex(rgb: tuple[float, float, float]) -> str:
    r, g, b = rgb
    r8 = int(round(_clamp01(r) * 255.0))
    g8 = int(round(_clamp01(g) * 255.0))
    b8 = int(round(_clamp01(b) * 255.0))
    return util.rgb_to_hex((r8, g8, b8))


@dataclass(frozen=True, slots=True)
class OKLab:
    L: float
    a: float
    b: float


@dataclass(frozen=True, slots=True)
class OKLCH:
    L: float
    C: float
    h_rad: float


def srgb01_to_oklab(rgb: tuple[float, float, float]) -> OKLab:
    # https://bottosson.github.io/posts/oklab/
    r, g, b = rgb
    lr = _srgb_to_linear(r)
    lg = _srgb_to_linear(g)
    lb = _srgb_to_linear(b)

    l = 0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb
    m = 0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb
    s = 0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb

    l_ = l ** (1.0 / 3.0)
    m_ = m ** (1.0 / 3.0)
    s_ = s ** (1.0 / 3.0)

    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return OKLab(L=L, a=a, b=b)


def oklab_to_srgb01(lab: OKLab) -> tuple[float, float, float]:
    # https://bottosson.github.io/posts/oklab/
    L, a, b = lab.L, lab.a, lab.b

    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b

    l = l_**3
    m = m_**3
    s = s_**3

    lr = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    lg = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    lb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    r = _linear_to_srgb(lr)
    g = _linear_to_srgb(lg)
    b = _linear_to_srgb(lb)
    return (r, g, b)


def oklab_to_oklch(lab: OKLab) -> OKLCH:
    C = math.hypot(lab.a, lab.b)
    h = math.atan2(lab.b, lab.a)
    return OKLCH(L=lab.L, C=C, h_rad=h)


def oklch_to_oklab(lch: OKLCH) -> OKLab:
    a = lch.C * math.cos(lch.h_rad)
    b = lch.C * math.sin(lch.h_rad)
    return OKLab(L=lch.L, a=a, b=b)


def _in_gamut_srgb01(rgb: tuple[float, float, float]) -> bool:
    r, g, b = rgb
    return 0.0 <= r <= 1.0 and 0.0 <= g <= 1.0 and 0.0 <= b <= 1.0


def oklch_to_hex_gamut_mapped(lch: OKLCH) -> str:
    # Simple mapping: reduce chroma until sRGB is in gamut.
    lo = 0.0
    hi = max(0.0, lch.C)
    best = OKLCH(L=lch.L, C=lo, h_rad=lch.h_rad)

    # If already in gamut, keep it.
    rgb0 = oklab_to_srgb01(oklch_to_oklab(lch))
    if _in_gamut_srgb01(rgb0):
        return srgb01_to_hex(rgb0)

    # Binary search chroma.
    for _ in range(30):
        mid = (lo + hi) / 2.0
        candidate = OKLCH(L=lch.L, C=mid, h_rad=lch.h_rad)
        rgb = oklab_to_srgb01(oklch_to_oklab(candidate))
        if _in_gamut_srgb01(rgb):
            best = candidate
            lo = mid
        else:
            hi = mid

    return srgb01_to_hex(oklab_to_srgb01(oklch_to_oklab(best)))


def square(hex_color: str, width: int = 2) -> str:
    r, g, b = util.hex_to_rgb(hex_color)
    return f"\033[48;2;{r};{g};{b}m" + (" " * width) + RESET


def show_row(label: str, colors: list[str]) -> None:
    blocks = "".join(square(c) for c in colors)
    values = " ".join(c for c in colors)
    print(f"{label:<18} {blocks}  {values}")


def legacy_fill_palette_hsv(existing_hex: list[str], target_count: int) -> list[str]:
    existing_rgb8 = [util.hex_to_rgb(c) for c in existing_hex]
    if len(existing_rgb8) >= target_count:
        return existing_hex[:]

    existing_hsv = [colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0) for (r, g, b) in existing_rgb8]
    hues = sorted(h for (h, _s, _v) in existing_hsv)
    avg_s = sum(s for (_h, s, _v) in existing_hsv) / len(existing_hsv)
    avg_v = sum(v for (_h, _s, v) in existing_hsv) / len(existing_hsv)

    def circle_distance(a: float, b: float) -> float:
        return min(abs(a - b), abs(b - a + 1.0), abs(a - b + 1.0))

    def circle_midpoint(a: float, b: float) -> float:
        m1 = (a + b) / 2.0
        m2 = (a + b + 1.0) / 2.0
        d1 = circle_distance(a, m1) + circle_distance(b, m1)
        d2 = circle_distance(a, m2) + circle_distance(b, m2)
        return m1 if d1 < d2 else m2

    needed = target_count - len(existing_rgb8)
    working = hues[:]
    added: list[str] = []

    for _ in range(needed):
        max_gap = -1.0
        best_mid = 0.0
        for i in range(len(working)):
            h0 = working[i]
            h1 = working[(i + 1) % len(working)]
            gap = circle_distance(h0, h1)
            if gap > max_gap:
                max_gap = gap
                best_mid = circle_midpoint(h0, h1) % 1.0

        r, g, b = colorsys.hsv_to_rgb(best_mid, avg_s, avg_v)
        added.append(srgb01_to_hex((r, g, b)))
        working.append(best_mid)
        working.sort()

    return existing_hex[:] + added


def new_fill_palette_oklch(existing_hex: list[str], target_count: int) -> list[str]:
    if len(existing_hex) >= target_count:
        return existing_hex[:]

    lchs: list[OKLCH] = []
    for c in existing_hex:
        lab = srgb01_to_oklab(hex_to_srgb01(c))
        lchs.append(oklab_to_oklch(lab))

    # Hue is unstable near neutral; still compute, but this demo keeps it simple.
    hues = sorted(((lch.h_rad % (2.0 * math.pi)) for lch in lchs))
    avg_L = sum(lch.L for lch in lchs) / len(lchs)
    avg_C = sum(lch.C for lch in lchs) / len(lchs)

    def circle_distance_rad(a: float, b: float) -> float:
        d = abs(a - b) % (2.0 * math.pi)
        return min(d, 2.0 * math.pi - d)

    def circle_midpoint_rad(a: float, b: float) -> float:
        # midpoint along shortest arc
        da = (b - a) % (2.0 * math.pi)
        if da > math.pi:
            da -= 2.0 * math.pi
        return (a + da / 2.0) % (2.0 * math.pi)

    needed = target_count - len(existing_hex)
    working = hues[:]
    added: list[str] = []

    for _ in range(needed):
        max_gap = -1.0
        best_mid = 0.0
        for i in range(len(working)):
            h0 = working[i]
            h1 = working[(i + 1) % len(working)]
            gap = circle_distance_rad(h0, h1)
            if gap > max_gap:
                max_gap = gap
                best_mid = circle_midpoint_rad(h0, h1)

        added.append(oklch_to_hex_gamut_mapped(OKLCH(L=avg_L, C=avg_C, h_rad=best_mid)))
        working.append(best_mid)
        working.sort()

    return existing_hex[:] + added


def legacy_blend_srgb(a: str, b: str, t: float) -> str:
    r1, g1, b1 = util.hex_to_rgb(a)
    r2, g2, b2 = util.hex_to_rgb(b)
    r = int(round((1.0 - t) * r1 + t * r2))
    g = int(round((1.0 - t) * g1 + t * g2))
    bb = int(round((1.0 - t) * b1 + t * b2))
    return util.rgb_to_hex((r, g, bb))


def new_blend_oklab(a: str, b: str, t: float) -> str:
    la = srgb01_to_oklab(hex_to_srgb01(a))
    lb = srgb01_to_oklab(hex_to_srgb01(b))
    mixed = OKLab(
        L=(1.0 - t) * la.L + t * lb.L,
        a=(1.0 - t) * la.a + t * lb.a,
        b=(1.0 - t) * la.b + t * lb.b,
    )
    rgb = oklab_to_srgb01(mixed)
    if _in_gamut_srgb01(rgb):
        return srgb01_to_hex(rgb)

    lch = oklab_to_oklch(mixed)
    return oklch_to_hex_gamut_mapped(lch)


def legacy_lighten(hex_color: str, amount: float) -> str:
    r, g, b = util.hex_to_rgb(hex_color)
    nr = int(r + (255 - r) * amount)
    ng = int(g + (255 - g) * amount)
    nb = int(b + (255 - b) * amount)
    return util.rgb_to_hex((nr, ng, nb))


def new_lighten_oklch(hex_color: str, amount: float) -> str:
    lch = oklab_to_oklch(srgb01_to_oklab(hex_to_srgb01(hex_color)))
    L = lch.L + (1.0 - lch.L) * amount
    return oklch_to_hex_gamut_mapped(OKLCH(L=L, C=lch.C, h_rad=lch.h_rad))


def legacy_darken(hex_color: str, amount: float) -> str:
    r, g, b = util.hex_to_rgb(hex_color)
    nr = int(r * (1.0 - amount))
    ng = int(g * (1.0 - amount))
    nb = int(b * (1.0 - amount))
    return util.rgb_to_hex((nr, ng, nb))


def new_darken_oklch(hex_color: str, amount: float) -> str:
    lch = oklab_to_oklch(srgb01_to_oklab(hex_to_srgb01(hex_color)))
    L = lch.L * (1.0 - amount)
    return oklch_to_hex_gamut_mapped(OKLCH(L=L, C=lch.C, h_rad=lch.h_rad))


def section(title: str) -> None:
    print("\n" + title)
    print("-" * len(title))


def demo_palette_completion() -> None:
    section("Palette completion: legacy HSV vs OKLCH hue-gap fill")

    cases: list[tuple[str, list[str], int]] = [
        (
            "primary RGB",
            ["#ff0000", "#00ff00", "#0000ff"],
            6,
        ),
        (
            "warm-only",
            ["#ff6b6b", "#ffb86c", "#f1fa8c"],
            6,
        ),
        (
            "mixed-mid",
            ["#2a9d8f", "#e76f51", "#264653", "#e9c46a"],
            8,
        ),
    ]

    for name, base, n in cases:
        print(f"\nCase: {name}")
        show_row("existing", base)
        show_row("legacy HSV", legacy_fill_palette_hsv(base, n))
        show_row("new OKLCH", new_fill_palette_oklch(base, n))


def demo_blend() -> None:
    section("Blend: sRGB lerp vs OKLab lerp")
    a = "#1e90ff"  # dodgerblue
    b = "#ffd166"  # warm yellow
    steps = [0.0, 0.25, 0.5, 0.75, 1.0]

    legacy = [legacy_blend_srgb(a, b, t) for t in steps]
    new = [new_blend_oklab(a, b, t) for t in steps]

    show_row("A", [a])
    show_row("B", [b])
    show_row("legacy sRGB", legacy)
    show_row("new OKLab", new)


def demo_lighten_darken() -> None:
    section("Lighten/darken: legacy sRGB vs OKLCH L")
    base = "#2b2d42"
    amounts = [0.1, 0.2, 0.35, 0.5]

    show_row("base", [base])
    show_row(
        "legacy +",
        [legacy_lighten(base, a) for a in amounts],
    )
    show_row(
        "new +",
        [new_lighten_oklch(base, a) for a in amounts],
    )
    show_row(
        "legacy -",
        [legacy_darken(base, a) for a in amounts],
    )
    show_row(
        "new -",
        [new_darken_oklch(base, a) for a in amounts],
    )


def main() -> None:
    print("ANSI Color Ops Visual Demo")
    print("(legacy pywal ops vs proposed OKLab/OKLCH ops)")

    demo_palette_completion()
    demo_blend()
    demo_lighten_darken()

    print("\nDone.")


if __name__ == "__main__":
    main()
