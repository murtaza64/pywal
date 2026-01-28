"""OKLab/OKLCH conversion helpers.

No pywal-specific types here to avoid circular imports.

References:
- https://bottosson.github.io/posts/oklab/
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def srgb_to_linear(u: float) -> float:
    if u <= 0.04045:
        return u / 12.92
    return ((u + 0.055) / 1.055) ** 2.4


def linear_to_srgb(u: float) -> float:
    if u <= 0.0031308:
        return 12.92 * u
    return 1.055 * (u ** (1.0 / 2.4)) - 0.055


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
    r, g, b = rgb
    lr = srgb_to_linear(r)
    lg = srgb_to_linear(g)
    lb = srgb_to_linear(b)

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

    r = linear_to_srgb(lr)
    g = linear_to_srgb(lg)
    b = linear_to_srgb(lb)
    return (r, g, b)


def oklab_to_oklch(lab: OKLab) -> OKLCH:
    C = math.hypot(lab.a, lab.b)
    h = math.atan2(lab.b, lab.a)
    return OKLCH(L=lab.L, C=C, h_rad=h)


def oklch_to_oklab(lch: OKLCH) -> OKLab:
    a = lch.C * math.cos(lch.h_rad)
    b = lch.C * math.sin(lch.h_rad)
    return OKLab(L=lch.L, a=a, b=b)
