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
        palette_size = 8 + i
        logging.debug(f"ColorThief iteration {i + 1} (requesting {palette_size} colors):")
        
        raw_colors_rgb = color_cmd(color_count=palette_size)
        raw_colors_hex = [util.rgb_to_hex(color) for color in raw_colors_rgb]
        
        logging.debug(f"Raw colors from ColorThief ({len(raw_colors_rgb)} colors):")
        colors.palette_absolute(raw_colors_hex)
        
        raw_colors = [color for color in raw_colors_rgb if not match.is_greyish(*color)]
        filtered_hex = [util.rgb_to_hex(color) for color in raw_colors]
        
        logging.debug(f"After filtering greyish colors ({len(raw_colors)} colors remaining):")
        colors.palette_absolute(filtered_hex)

        if len(raw_colors) >= 8:
            return filtered_hex
        else:
            logging.debug(f"Need at least 8 colors, only got {len(raw_colors)}. Trying larger palette...")

    logging.error("ColorThief couldn't generate a suitable palette.")
    sys.exit(1)



def adjust(cols, light):
    """Create palette."""
    
    # Find darkest color for background
    darkest = min(cols, key=util.rgb_to_yiq)
    
    # Remove darkest from original list, preserve original order for rest
    remaining = [c for c in cols if c != darkest]
    
    # New order: [darkest_for_background, ...original_colorThief_order...]
    # This preserves the brightest color instead of losing it to generated colors
    cols = [darkest] + remaining[:7]  # Take only first 7 of remaining
    
    logging.debug("After reordering (darkest first, rest preserve original order):")
    colors.palette_absolute(cols)
    
    # Return only 8 colors - shade_16 will expand to 16
    raw_colors = cols

    return colors.generic_adjust(raw_colors, light)


def get(img, light=False):
    """Get colorscheme."""
    
    cols = gen_colors(img)
    return adjust(cols, light)
