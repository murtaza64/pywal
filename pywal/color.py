"""Color value object.

This is a compatibility-focused replacement for the old `util.Color` class.
Behavior of legacy color operations is intentionally unchanged.
"""

from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass
from functools import cached_property
from typing import ClassVar, Optional

import colorsys

from . import oklab


VERBOSE = 5


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    """Convert a hex color to RGB (0-255)."""
    rgb = tuple(bytes.fromhex(color.strip("#")))
    # Keep behavior loose: accept anything bytes.fromhex accepts.
    return (int(rgb[0]), int(rgb[1]), int(rgb[2]))


def rgb_to_hex(color: tuple[int, int, int]) -> str:
    """Convert RGB (0-255) to hex."""
    r, g, b = color
    return "#%02x%02x%02x" % (r, g, b)


def hex_to_xrgba(color: str) -> str:
    """Convert a hex color to xrdb rgba."""
    col = color.lower().strip("#")
    return "%s%s/%s%s/%s%s/ff" % (*col,)


def alpha_integrify(alpha_value: str) -> str:
    """Ensure alpha string is an int between 0 and 100 (as a string)."""
    a = float(alpha_value)
    if a < 0:
        a = abs(a)
    if a < 1:
        a = a * 100
    if a > 100:
        a = 100
    return str(int(a))


def print_color_change(old_color: str, new_color: str, operation: str, level: int = VERBOSE) -> None:
    """Log a color change with visual representation."""
    r1, g1, b1 = hex_to_rgb(old_color)
    r2, g2, b2 = hex_to_rgb(new_color)
    logging.log(
        level,
        f"    {operation}: \033[48;2;{r1};{g1};{b1}m  \033[0m {old_color} -> \033[48;2;{r2};{g2};{b2}m  \033[0m {new_color}",
    )


def darken_color(color: str, amount: float, debug: bool = False) -> str:
    _ = debug
    return Color.from_hex(color).darken_amount(amount).hex_color


def lighten_color(color: str, amount: float, debug: bool = False) -> str:
    _ = debug
    return Color.from_hex(color).lighten_amount(amount).hex_color


def blend_color(color: str, color2: str) -> str:
    return Color.from_hex(color).blend_oklab(Color.from_hex(color2), t=0.5).hex_color


def saturate_color(color: str, amount: float, debug: bool = False) -> str:
    _ = debug
    return Color.from_hex(color).saturate_to(amount).hex_color


def brighten_color(color: str, min_brightness: float, debug: bool = False) -> str:
    _ = debug
    return Color.from_hex(color).brighten_min_lightness(min_brightness).hex_color


def add_saturation(color: str, amount: float, debug: bool = False) -> str:
    _ = debug
    return Color.from_hex(color).add_saturation_amount(amount).hex_color


def rgb_to_yiq(color: str):
    """Sort helper (legacy behavior; uses colorsys directly on 0-255 channels)."""
    return colorsys.rgb_to_yiq(*hex_to_rgb(color))


@dataclass
class Color:
    """Hex-backed color with helpers for templates/exports."""

    hex_color: str
    alpha_num_override: Optional[str] = None

    # Global alpha defaults (mutated by CLI / config).
    alpha_num: ClassVar[str] = "100"
    passed_alpha_num: ClassVar[Optional[str]] = None

    GREYISH_CHROMA_THRESHOLD: ClassVar[float] = 0.04

    def __str__(self) -> str:
        return self.hex_color

    @classmethod
    def from_hex(cls, hex_color: str) -> "Color":
        return cls(hex_color)

    @classmethod
    def from_rgb8(cls, r: int, g: int, b: int) -> "Color":
        return cls(rgb_to_hex((int(r), int(g), int(b))))

    @staticmethod
    def _clamp01(x: float) -> float:
        if x < 0.0:
            return 0.0
        if x > 1.0:
            return 1.0
        return x

    @staticmethod
    def _in_gamut_srgb01(rgb: tuple[float, float, float]) -> bool:
        r, g, b = rgb
        return 0.0 <= r <= 1.0 and 0.0 <= g <= 1.0 and 0.0 <= b <= 1.0

    @classmethod
    def from_srgb01(cls, rgb: tuple[float, float, float]) -> "Color":
        r, g, b = rgb
        r8 = int(round(cls._clamp01(r) * 255.0))
        g8 = int(round(cls._clamp01(g) * 255.0))
        b8 = int(round(cls._clamp01(b) * 255.0))
        return cls(rgb_to_hex((r8, g8, b8)))

    @classmethod
    def from_oklch(cls, lch: oklab.OKLCH) -> "Color":
        rgb0 = oklab.oklab_to_srgb01(oklab.oklch_to_oklab(lch))
        if cls._in_gamut_srgb01(rgb0):
            return cls.from_srgb01(rgb0)

        # Gamut map by reducing chroma (keep L/h).
        lo = 0.0
        hi = max(0.0, lch.C)
        best = oklab.OKLCH(L=lch.L, C=0.0, h_rad=lch.h_rad)
        for _ in range(30):
            mid = (lo + hi) / 2.0
            candidate = oklab.OKLCH(L=lch.L, C=mid, h_rad=lch.h_rad)
            rgb = oklab.oklab_to_srgb01(oklab.oklch_to_oklab(candidate))
            if cls._in_gamut_srgb01(rgb):
                best = candidate
                lo = mid
            else:
                hi = mid
        return cls.from_srgb01(oklab.oklab_to_srgb01(oklab.oklch_to_oklab(best)))

    @cached_property
    def rgb8(self) -> tuple[int, int, int]:
        r, g, b = hex_to_rgb(self.hex_color)
        return (int(r), int(g), int(b))

    @cached_property
    def srgb(self) -> tuple[float, float, float]:
        r, g, b = self.rgb8
        return (r / 255.0, g / 255.0, b / 255.0)

    @cached_property
    def oklab(self) -> oklab.OKLab:
        return oklab.srgb01_to_oklab(self.srgb)

    @cached_property
    def oklch(self) -> oklab.OKLCH:
        return oklab.oklab_to_oklch(self.oklab)

    def with_oklch(
        self,
        *,
        L: float | None = None,
        C: float | None = None,
        h_rad: float | None = None,
    ) -> "Color":
        """Return a new color with overridden OKLCH components."""
        lch = self.oklch
        return Color.from_oklch(
            oklab.OKLCH(
                L=lch.L if L is None else L,
                C=lch.C if C is None else C,
                h_rad=lch.h_rad if h_rad is None else h_rad,
            )
        )

    @cached_property
    def hsv(self) -> tuple[float, float, float]:
        return colorsys.rgb_to_hsv(*self.srgb)

    @cached_property
    def hls(self) -> tuple[float, float, float]:
        return colorsys.rgb_to_hls(*self.srgb)

    def is_greyish(self, chroma_threshold: float | None = None) -> bool:
        """Return True if color is near-neutral.

        Uses OKLCH chroma, which is more stable than HSV saturation for very
        dark/light colors.
        """
        t = Color.GREYISH_CHROMA_THRESHOLD if chroma_threshold is None else chroma_threshold
        return self.oklch.C < t

    @property
    def rgb(self) -> str:
        """Convert a hex color to rgb."""
        return "%s,%s,%s" % (*self.rgb8,)

    @property
    def rgbspace(self) -> str:
        """Convert a hex color to rgb separated by spaces."""
        return "%s %s %s" % (*self.rgb8,)

    @property
    def xrgba(self) -> str:
        """Convert a hex color to xrdb rgba."""
        return hex_to_xrgba(self.hex_color)

    @property
    def rgba(self) -> str:
        """Convert a hex color to rgba."""
        return "rgba(%s,%s,%s,%s)" % (
            *self.rgb8,
            self.alpha_dec,
        )

    @property
    def hex_argb(self) -> str:
        """Convert an alpha hex color to argb hex."""
        al_val = alpha_integrify(self.alpha_num_override or Color.alpha_num)
        return "#%02X%s" % (
            int(int(al_val) * 255 / 100),
            self.hex_color[1:],
        )

    @property
    def alpha(self) -> str:
        """Add URxvt alpha value to color."""
        al_val = alpha_integrify(self.alpha_num_override or Color.alpha_num)
        return "[%s]%s" % (al_val, self.hex_color)

    @property
    def alpha_dec(self) -> float:
        """Export the alpha value as a decimal number in [0, 1]."""
        al_val = alpha_integrify(self.alpha_num_override or Color.alpha_num)
        return int(al_val) / 100

    @property
    def alpha_hex(self) -> str:
        """Export the alpha value as a hexdecimal number in [00, FF]."""
        al_val = alpha_integrify(self.alpha_num_override or Color.alpha_num)
        return "%02X" % (int(int(al_val) * 255 / 100))

    @property
    def decimal(self) -> str:
        """Export color in decimal."""
        return "%s%s" % ("#", int(self.hex_color[1:], 16))

    @property
    def decimal_strip(self) -> int:
        """Strip '#' from decimal color."""
        return int(self.hex_color[1:], 16)

    @property
    def octal(self) -> str:
        """Export color in octal."""
        return "%s%s" % ("#", oct(int(self.hex_color[1:], 16))[2:])

    @property
    def octal_strip(self) -> str:
        """Strip '#' from octal color."""
        return oct(int(self.hex_color[1:], 16))[2:]

    @property
    def strip(self) -> str:
        """Strip '#' from color."""
        return self.hex_color[1:]

    @property
    def red(self) -> str:
        """Red value as float between 0 and 1."""
        return "%.3f" % (self.rgb8[0] / 255.0)

    @property
    def green(self) -> str:
        """Green value as float between 0 and 1."""
        return "%.3f" % (self.rgb8[1] / 255.0)

    @property
    def blue(self) -> str:
        """Blue value as float between 0 and 1."""
        return "%.3f" % (self.rgb8[2] / 255.0)

    @property
    def red_hex(self) -> str:
        """Red value as hex."""
        return "%s" % (self.hex_color)[1:3]

    @property
    def green_hex(self) -> str:
        """Green value as hex."""
        return "%s" % (self.hex_color)[3:5]

    @property
    def blue_hex(self) -> str:
        """Blue value as hex."""
        return "%s" % (self.hex_color)[5:]

    @property
    def red_dec(self) -> str:
        """Red value as decimal."""
        return "%s" % self.rgb8[0]

    @property
    def green_dec(self) -> str:
        """Green value as decimal."""
        return "%s" % self.rgb8[1]

    @property
    def blue_dec(self) -> str:
        """Blue value as decimal."""
        return "%s" % self.rgb8[2]

    @property
    def w3_luminance(self) -> float:
        """Luminance value of the color according to W3 formula."""
        color_channels = [float(self.red), float(self.green), float(self.blue)]
        for index, channel in enumerate(color_channels):
            if channel <= 0.04045:
                color_channels[index] = channel / 12.92
            else:
                color_channels[index] = ((channel + 0.055) / 1.055) ** 2.4

        return (
            (0.2126 * color_channels[0])
            + (0.7152 * color_channels[1])
            + (0.0722 * color_channels[2])
        )

    # Legacy template helpers (behavior intentionally unchanged)
    def lighten(self, percent):
        """Lighten color by percent."""
        percent = float(re.sub(r"[\D\.]", "", str(percent)))
        return self.lighten_amount(percent / 100)

    def darken(self, percent):
        """Darken color by percent."""
        percent = float(re.sub(r"[\D\.]", "", str(percent)))
        return self.darken_amount(percent / 100)

    def saturate(self, percent):
        """Saturate a color."""
        percent = float(re.sub(r"[\D\.]", "", str(percent)))
        return self.saturate_to(percent / 100)

    def lighten_amount(self, amount: float) -> "Color":
        lch = self.oklch
        new_lch = oklab.OKLCH(
            L=lch.L + (1.0 - lch.L) * amount,
            C=lch.C,
            h_rad=lch.h_rad,
        )
        new_color = Color.from_oklch(new_lch)
        print_color_change(self.hex_color, new_color.hex_color, f"lighten({amount})")
        return new_color

    def darken_amount(self, amount: float) -> "Color":
        lch = self.oklch
        new_lch = oklab.OKLCH(
            L=lch.L * (1.0 - amount),
            C=lch.C,
            h_rad=lch.h_rad,
        )
        new_color = Color.from_oklch(new_lch)
        print_color_change(self.hex_color, new_color.hex_color, f"darken({amount})")
        return new_color

    def blend_oklab(self, other: "Color", t: float = 0.5) -> "Color":
        a = self.oklab
        b = other.oklab
        mixed = oklab.OKLab(
            L=(1.0 - t) * a.L + t * b.L,
            a=(1.0 - t) * a.a + t * b.a,
            b=(1.0 - t) * a.b + t * b.b,
        )
        rgb = oklab.oklab_to_srgb01(mixed)
        if Color._in_gamut_srgb01(rgb):
            new_color = Color.from_srgb01(rgb)
        else:
            new_color = Color.from_oklch(oklab.oklab_to_oklch(mixed))

        print_color_change(
            self.hex_color,
            new_color.hex_color,
            f"blend({t}, {other.hex_color})",
        )
        return new_color

    def saturate_to(self, amount: float) -> "Color":
        """Set HLS saturation to `amount` (legacy behavior)."""
        h, l, _s = self.hls
        r, g, b = colorsys.hls_to_rgb(h, l, amount)
        new_color = Color.from_srgb01((r, g, b))
        print_color_change(self.hex_color, new_color.hex_color, f"saturate({amount})")
        return new_color

    def add_saturation_amount(self, amount: float) -> "Color":
        """Add to HLS saturation (legacy behavior, clamps to [-1, 1])."""
        h, l, s = self.hls
        s = s + amount
        if s > 1.0:
            s = 1.0
        if s < -1.0:
            s = -1.0
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        new_color = Color.from_srgb01((r, g, b))
        print_color_change(self.hex_color, new_color.hex_color, f"add_saturation({amount})")
        return new_color

    def brighten_min_lightness(self, min_brightness: float) -> "Color":
        """Clamp HLS lightness to at least `min_brightness` (legacy behavior)."""
        h, l, s = self.hls
        l = max(min_brightness, l)
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        new_color = Color.from_srgb01((r, g, b))
        print_color_change(self.hex_color, new_color.hex_color, f"brighten({min_brightness})")
        return new_color

    def adjust_alpha(self, alpha="100"):
        return Color(self.hex_color, alpha_num_override=alpha)
