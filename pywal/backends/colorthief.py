"""
Generate a colorscheme using ColorThief.
"""

import logging
import sys

try:
    from colorthief import ColorThief

except ImportError:
    logging.error("ColorThief wasn't found on your system.")
    logging.error("Try another backend. (wal --backend)")
    sys.exit(1)

from .. import colors
from .. import util
from .. import match


def gen_colors(img):
    """Loop until 16 colors are generated."""
    color_cmd = ColorThief(img).get_palette

    for i in range(0, 10, 1):
        raw_colors = color_cmd(color_count=8 + i)
        raw_colors = [color for color in raw_colors if not match.is_greyish(*color)]

        if len(raw_colors) >= 8:
            break

        if i == 10:
            logging.error("ColorThief couldn't generate a suitable palette.")
            sys.exit(1)

        else:
            logging.warning("ColorThief couldn't generate a palette.")
            logging.warning("Trying a larger palette size %s", 8 + i)

    return [util.rgb_to_hex(color) for color in raw_colors]


def adjust(cols, light, **kwargs):
    """Create palette.
    :keyword-args:
    -    c16: use 16 colors through specified method - [ "lighten" | "darken" ]
    -    ansi_match: rearrange palette to match ANSI colors - bool
    """
    if "c16" in kwargs:
        cols16 = kwargs["c16"]
    else:
        cols16 = False
    
    if "ansi_match" in kwargs:
        ansi_match = kwargs["ansi_match"]
    else:
        ansi_match = False
    
    cols.sort(key=util.rgb_to_yiq)
    
    print("Initial sorted colors (colorthief):")
    colors.palette_absolute(cols)
    
    if ansi_match:
        logging.info("rearranging palette to match ansi colors")
        raw_colors = match.rearrange_palette(cols)
        print("After ANSI color matching:")
        colors.palette_absolute(raw_colors[:8])  # Show first 8 before duplication
        # print('raw0', raw_colors)
        raw_colors = [*raw_colors, *raw_colors]
        # print('raw', raw_colors)
    else:
        raw_colors = [*cols, *cols]

    return colors.generic_adjust(raw_colors, light, c16=cols16)


def get(img, light=False, **kwargs):
    """Get colorscheme.
    :keyword-args:
    -    c16: use 16 colors through specified method - [ "lighten" | "darken" ]
    -    ansi_match: rearrange palette to match ANSI colors - bool
    """
    if "c16" in kwargs:
        cols16 = kwargs["c16"]
    else:
        cols16 = False
    
    if "ansi_match" in kwargs:
        ansi_match = kwargs["ansi_match"]
    else:
        ansi_match = False
    
    cols = gen_colors(img)
    return adjust(cols, light, c16=cols16, ansi_match=ansi_match)
