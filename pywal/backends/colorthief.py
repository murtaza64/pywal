"""
Generate a colorscheme using ColorThief.
"""

import colorsys
import logging
import sys

from pywal.types import RGB, HexColor, RGBNormalized

from modern_colorthief import get_palette as color_cmd

from .. import colors
from .. import util
from .. import match
from ..match import circle_distance, circle_midpoint
from ..args import ARGS

def get_colored_square(r, g, b):
    """Return a colored square for terminal output."""
    return f"\033[48;2;{r};{g};{b}m  \033[0m"

def sorted_by_yiq(colors):
    """Sort colors by YIQ value."""
    return list(sorted(colors, key=util.rgb_to_yiq))

def format_hsv(h, s, v):
    """ example: (180*, 50%, 75%) """
    return f"({h * 360:.0f}°, {s*100:.0f}%, {v*100:.0f}%)"

def sorted_by_saturation(colors: list[HexColor]) -> list[HexColor]:
    rgb_colors = [util.hex_to_rgb(color) for color in colors]
    rgb_normalized = [(r / 255.0, g / 255.0, b / 255.0) for r, g, b in rgb_colors]
    hsv_colors = [colorsys.rgb_to_hsv(r, g, b) for r, g, b in rgb_normalized]
    for rgb, hsv in sorted(zip(rgb_colors, hsv_colors), key=lambda pair: pair[1][1]):
        sq = get_colored_square(*rgb)
        hsv = format_hsv(*hsv)
        logging.debug(f"{sq*2} RGB: {rgb} -> HSV: {hsv}")
    sorted_colors = [color for _, color in sorted(zip(hsv_colors, colors), key=lambda pair: pair[0][1])]
    return sorted_colors

def sorted_by_value(colors: list[HexColor]) -> list[HexColor]:
    rgb_colors = [util.hex_to_rgb(color) for color in colors]
    rgb_normalized = [(r / 255.0, g / 255.0, b / 255.0) for r, g, b in rgb_colors]
    hsv_colors = [colorsys.rgb_to_hsv(r, g, b) for r, g, b in rgb_normalized]
    # for rgb, hsv in sorted(zip(rgb_colors, hsv_colors), key=lambda pair: pair[1][2]):
    #     sq = get_colored_square(*rgb)
    #     hsv = format_hsv(*hsv)
    #     logging.debug(f"{sq*2} RGB: {rgb} -> HSV: {hsv}")
    sorted_colors = [color for _, color in sorted(zip(hsv_colors, colors), key=lambda pair: pair[0][2])]
    return sorted_colors

def gen_colors(img: str):
    """Loop until 8 colors are generated (original iterative strategy)."""
    from modern_colorthief import get_palette as color_cmd

    for i in range(0, 10, 1):
        palette_size = 8 + i
        logging.debug(f"ColorThief iteration {i + 1} (requesting {palette_size} colors):")
        
        raw_colors_rgb = color_cmd(img, color_count=palette_size)
        raw_colors_hex = [util.rgb_to_hex(color) for color in raw_colors_rgb]
        
        logging.debug(f"Raw colors from ColorThief ({len(raw_colors_rgb)} colors):")
        colors.palette_absolute(raw_colors_hex)
        
        # Filter out greyish colors
        raw_colors = [color for color in raw_colors_rgb if not match.is_greyish(*color)]
        filtered_hex = [util.rgb_to_hex(color) for color in raw_colors]
        
        logging.debug(f"After filtering greyish colors ({len(raw_colors)} colors remaining):")
        colors.palette_absolute(filtered_hex)

        if len(raw_colors) >= 8:
            cols = filtered_hex
            darkest = min(cols, key=util.rgb_to_yiq)
            remaining = [c for c in cols if c != darkest]
            cols = [darkest] + remaining[:7]  # Take only first 7 of remaining
            logging.debug("After reordering (darkest first, rest preserve original order):")
            colors.palette_absolute(cols)
            return cols
        else:
            logging.debug(f"Need at least 8 colors, only got {len(raw_colors)}. Trying larger palette...")

    logging.error("ColorThief couldn't generate a suitable palette.")
    sys.exit(1)


def gen_colors_brightness(img):
    """Generate 16 colors immediately, select darkest/lightest for bg/fg and 6 brightest middle colors."""
    from modern_colorthief import get_palette as color_cmd
    
    logging.debug("Using brightness strategy - requesting 16 colors immediately:")
    
    # Get 16 colors directly
    raw_colors_rgb: list[RGB] = color_cmd(img, color_count=ARGS.subtractive_initial or 16)
    raw_colors_hex = [util.rgb_to_hex(color) for color in raw_colors_rgb]
    
    logging.debug(f"Raw 16 colors from ColorThief:")
    colors.palette_absolute(raw_colors_hex)

    # Get darkest and brightest colors
    darkest = min(raw_colors_rgb, key=lambda rgb: colorsys.rgb_to_yiq(*rgb))
    lightest = max(raw_colors_rgb, key=lambda rgb: colorsys.rgb_to_yiq(*rgb))

    remaining_colors_rgb = [rgb for rgb in raw_colors_rgb if rgb != darkest and rgb != lightest]
    
    # Filter out greyish colors  
    remaining_colors_rgb = [color for color in remaining_colors_rgb if not match.is_greyish(*color)]
    
    logging.debug(f"After filtering greyish colors ({len(remaining_colors_rgb)} colors remaining):")
    colors.palette_absolute([util.rgb_to_hex(color) for color in remaining_colors_rgb])
    
    if len(remaining_colors_rgb) < 6:
        logging.debug(f"Not enough non-grey colors ({len(remaining_colors_rgb)}), filling with interpolated colors...")
        remaining_colors_rgb = fill_palette_with_interpolated_colors(remaining_colors_rgb, 6)
    
    # Sort remaining colors by brightness (V in HSV)
    def get_brightness(rgb):
        r, g, b = [x / 255.0 for x in rgb]
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        return v
    
    # if ARGS.shuffle:
    #     import random
    #     random.shuffle(remaining_colors_rgb)
    #     logging.debug("Remaining colors shuffled randomly:")
    # else:
    #     logging.debug("Remaining colors sorted by brightness (V in HSV):")
    #     remaining_colors_rgb = sorted(remaining_colors_rgb, key=get_brightness, reverse=True)
    # colors.palette_absolute([util.rgb_to_hex(color) for color in remaining_colors_rgb])
    # top_6 = remaining_colors_rgb[:6]
    #
    # logging.debug("Selected colors - darkest (bg), 6 brightest middle colors, lightest (fg):")

    selected = [darkest] + remaining_colors_rgb + [lightest]

    # selected = sorted(remaining_colors_rgb, key=get_brightness)
    selected_hex = [util.rgb_to_hex(color) for color in selected]
    logging.debug(f"Final selected colors ({len(selected_hex)} colors):")
    colors.palette_absolute(selected_hex)
    
    return selected_hex


def fill_palette_with_interpolated_colors(existing_colors_rgb: list[RGB], target_count: int = 8) -> list[RGB]:
    """Fill palette by interpolating between existing hues using circle math."""
    
    if len(existing_colors_rgb) >= target_count:
        return existing_colors_rgb
    
    logging.debug(f"Filling palette from {len(existing_colors_rgb)} to {target_count} colors")
    
    # Convert to HSV and analyze existing colors
    existing_hsv = [colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0) for r, g, b in existing_colors_rgb]
    existing_hues = [hsv[0] for hsv in existing_hsv]
    
    # Calculate average saturation and value for consistency
    avg_s = sum(hsv[1] for hsv in existing_hsv) / len(existing_hsv)
    avg_v = sum(hsv[2] for hsv in existing_hsv) / len(existing_hsv)
    
    logging.debug(f"Average S: {avg_s:.2f}, Average V: {avg_v:.2f}")
    
    # Sort hues for gap analysis
    sorted_hues = sorted(existing_hues)
    
    interpolated_colors = []
    needed = target_count - len(existing_colors_rgb)
    
    # Generate interpolated colors by filling largest gaps
    working_hues = sorted_hues[:]
    
    for i in range(needed):
        # Find largest gap between consecutive hues
        max_gap = 0
        best_midpoint = 0
        
        for j in range(len(working_hues)):
            current_hue = working_hues[j]
            next_hue = working_hues[(j + 1) % len(working_hues)]
            
            gap = circle_distance(current_hue, next_hue)
            if gap > max_gap:
                max_gap = gap
                best_midpoint = circle_midpoint(current_hue, next_hue)
        
        # Create color with interpolated hue and average S/V
        new_rgb_normalized = colorsys.hsv_to_rgb(best_midpoint, avg_s, avg_v)
        new_rgb = tuple(int(c * 255) for c in new_rgb_normalized)
        
        interpolated_colors.append(new_rgb)
        working_hues.append(best_midpoint)
        working_hues.sort()
    
    result = existing_colors_rgb + interpolated_colors
    logging.debug(f"Added {len(interpolated_colors)} interpolated colors")
    colors.palette_absolute([util.rgb_to_hex(color) for color in result])
    
    return result


def adjust(cols, light):
    """Create palette."""
    # Return only 8 colors - shade_16 will expand to 16
    raw_colors = cols

    return colors.generic_adjust(raw_colors, light)


def get(img, light=False):
    """Get colorscheme."""
    
    if ARGS.generation_strategy == "iterative":
        cols = gen_colors(img)
    else:  # subtractive (default)
        cols = gen_colors_brightness(img)
    
    return adjust(cols, light)
