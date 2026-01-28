"""Color value object.

This is a compatibility-focused replacement for the old `util.Color` class.
Behavior of legacy color operations is intentionally unchanged.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import ClassVar, Optional


def _util():
    # Local import to avoid circular imports (util -> color).
    from . import util

    return util


@dataclass
class Color:
    """Hex-backed color with helpers for templates/exports."""

    hex_color: str

    # Global alpha defaults (mutated by CLI / config).
    alpha_num: ClassVar[str] = "100"
    passed_alpha_num: ClassVar[Optional[str]] = None

    def __str__(self) -> str:
        return self.hex_color

    @property
    def rgb(self) -> str:
        """Convert a hex color to rgb."""
        return "%s,%s,%s" % (*_util().hex_to_rgb(self.hex_color),)

    @property
    def rgbspace(self) -> str:
        """Convert a hex color to rgb separated by spaces."""
        return "%s %s %s" % (*_util().hex_to_rgb(self.hex_color),)

    @property
    def xrgba(self) -> str:
        """Convert a hex color to xrdb rgba."""
        return _util().hex_to_xrgba(self.hex_color)

    @property
    def rgba(self) -> str:
        """Convert a hex color to rgba."""
        return "rgba(%s,%s,%s,%s)" % (
            *_util().hex_to_rgb(self.hex_color),
            self.alpha_dec,
        )

    @property
    def hex_argb(self) -> str:
        """Convert an alpha hex color to argb hex."""
        al_val = _util().alpha_integrify(self.alpha_num)
        return "#%02X%s" % (
            int(int(al_val) * 255 / 100),
            self.hex_color[1:],
        )

    @property
    def alpha(self) -> str:
        """Add URxvt alpha value to color."""
        al_val = _util().alpha_integrify(self.alpha_num)
        return "[%s]%s" % (al_val, self.hex_color)

    @property
    def alpha_dec(self) -> float:
        """Export the alpha value as a decimal number in [0, 1]."""
        al_val = _util().alpha_integrify(self.alpha_num)
        return int(al_val) / 100

    @property
    def alpha_hex(self) -> str:
        """Export the alpha value as a hexdecimal number in [00, FF]."""
        al_val = _util().alpha_integrify(self.alpha_num)
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
        return "%.3f" % (_util().hex_to_rgb(self.hex_color)[0] / 255.0)

    @property
    def green(self) -> str:
        """Green value as float between 0 and 1."""
        return "%.3f" % (_util().hex_to_rgb(self.hex_color)[1] / 255.0)

    @property
    def blue(self) -> str:
        """Blue value as float between 0 and 1."""
        return "%.3f" % (_util().hex_to_rgb(self.hex_color)[2] / 255.0)

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
        return "%s" % _util().hex_to_rgb(self.hex_color)[0]

    @property
    def green_dec(self) -> str:
        """Green value as decimal."""
        return "%s" % _util().hex_to_rgb(self.hex_color)[1]

    @property
    def blue_dec(self) -> str:
        """Blue value as decimal."""
        return "%s" % _util().hex_to_rgb(self.hex_color)[2]

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
        return Color(_util().lighten_color(self.hex_color, percent / 100))

    def darken(self, percent):
        """Darken color by percent."""
        percent = float(re.sub(r"[\D\.]", "", str(percent)))
        return Color(_util().darken_color(self.hex_color, percent / 100))

    def saturate(self, percent):
        """Saturate a color."""
        percent = float(re.sub(r"[\D\.]", "", str(percent)))
        return Color(_util().saturate_color(self.hex_color, percent / 100))

    def adjust_alpha(self, alpha="100"):
        adjusted = copy.copy(self)
        adjusted.alpha_num = alpha
        return adjusted
