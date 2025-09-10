"""
Generate a colorscheme using fast_colorthief.
"""

import logging
import sys

try:
    import fast_colorthief

except ImportError:
    logging.error("fast_colorthief wasn't found on your system.")
    logging.error("Try another backend. (wal --backend)")
    sys.exit(1)

from .. import util
from .. import colors


def gen_colors(img):
    """Ask backend to generate 16 colors."""
    raw_colors = fast_colorthief.get_palette(img, 16)

    return [util.rgb_to_hex(color) for color in raw_colors]


def adjust(cols, light):
    """Create palette."""
    cols.sort(key=util.rgb_to_yiq)
    # Take first 8 colors and darken the background
    raw_colors = cols[:8]
    raw_colors[0] = util.darken_color(cols[0], 0.80)

    return colors.generic_adjust(raw_colors, light)


def get(img, light=False):
    """Get colorscheme."""
    cols = gen_colors(img)
    return adjust(cols, light)
