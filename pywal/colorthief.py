"""Generate candidate colors using ColorThief."""

import logging
import sys
import colorsys

from pywal.types import RGB

from .print import palette_absolute
from .color import Color
from .match import circle_distance, circle_midpoint
from .args import ARGS

def get_colored_square(r, g, b):
    """Return a colored square for terminal output."""
    return f"\033[48;2;{r};{g};{b}m  \033[0m"

def sorted_by_yiq(colors: list[Color]) -> list[Color]:
    """Sort colors by YIQ value."""
    return list(sorted(colors, key=lambda c: colorsys.rgb_to_yiq(*c.srgb)[0]))

def format_hsv(h, s, v):
    """ example: (180*, 50%, 75%) """
    return f"({h * 360:.0f}°, {s*100:.0f}%, {v*100:.0f}%)"

def sorted_by_saturation(colors: list[Color]) -> list[Color]:
    for c in sorted(colors, key=lambda c: c.hsv[1]):
        sq = get_colored_square(*c.rgb8)
        hsv = format_hsv(*c.hsv)
        logging.debug(f"{sq*2} RGB: {c.rgb8} -> HSV: {hsv}")
    return list(sorted(colors, key=lambda c: c.hsv[1]))

def sorted_by_value(colors: list[Color]) -> list[Color]:
    return list(sorted(colors, key=lambda c: c.hsv[2]))

def gen_colors(img: str) -> list[Color]:
    """Loop until >=8 non-greyish colors are generated (iterative strategy)."""
    from modern_colorthief import get_palette as color_cmd

    for i in range(0, 10, 1):
        palette_size = 8 + i
        logging.debug(f"ColorThief iteration {i + 1} (requesting {palette_size} colors):")
        
        raw_colors_rgb: list[RGB] = color_cmd(img, color_count=palette_size)
        raw_colors = [Color.from_rgb8(*rgb) for rgb in raw_colors_rgb]
        logging.debug(f"Raw colors from ColorThief ({len(raw_colors_rgb)} colors):")
        palette_absolute(raw_colors)
        
        # Filter out greyish colors
        filtered = [c for c in raw_colors if not c.is_greyish()]
        logging.debug(f"After filtering greyish colors ({len(raw_colors)} colors remaining):")
        palette_absolute(filtered)

        if len(filtered) >= 8:
            return filtered
        else:
            logging.debug(f"Need at least 8 colors, only got {len(filtered)}. Trying larger palette...")

    logging.error("ColorThief couldn't generate a suitable palette.")
    sys.exit(1)


def gen_colors_brightness(img: str, initial: int | None = None) -> list[Color]:
    """Generate a candidate list in one pass (subtractive strategy).

    Returns a full list of candidate colors; background/foreground selection is
    handled by the palette pipeline.
    """
    from modern_colorthief import get_palette as color_cmd
    
    logging.debug("Using brightness strategy - requesting 16 colors immediately:")
    
    # Get 16 colors directly
    color_count = initial or ARGS.subtractive_initial or 16
    raw_colors_rgb: list[RGB] = color_cmd(img, color_count=color_count)
    raw_colors = [Color.from_rgb8(*rgb) for rgb in raw_colors_rgb]
    raw_colors_hex = [c.hex_color for c in raw_colors]
    
    logging.debug(f"Raw 16 colors from ColorThief:")
    palette_absolute(raw_colors)

    non_grey = [c for c in raw_colors if not c.is_greyish()]
    candidates = non_grey if len(non_grey) >= 8 else raw_colors[:]

    if len(candidates) < 8:
        if not candidates:
            logging.error("ColorThief returned no colors")
            sys.exit(1)
        logging.debug(f"Not enough colors ({len(candidates)}), filling with interpolated colors...")
        candidates = fill_palette_with_interpolated_colors(candidates, 8)
    
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

    logging.debug(f"Final candidate list ({len(candidates)} colors):")
    palette_absolute(candidates)
    return candidates


def fill_palette_with_interpolated_colors(existing: list[Color], target_count: int = 8) -> list[Color]:
    """Fill palette by interpolating between existing hues using circle math."""

    if len(existing) >= target_count:
        return existing
    
    logging.debug(f"Filling palette from {len(existing)} to {target_count} colors")
    
    existing_hsv = [c.hsv for c in existing]
    existing_hues = [h for (h, _s, _v) in existing_hsv]
    
    # Calculate average saturation and value for consistency
    if not existing_hsv:
        return existing

    avg_s = sum(hsv[1] for hsv in existing_hsv) / len(existing_hsv)
    avg_v = sum(hsv[2] for hsv in existing_hsv) / len(existing_hsv)
    
    logging.debug(f"Average S: {avg_s:.2f}, Average V: {avg_v:.2f}")
    
    # Sort hues for gap analysis
    sorted_hues = sorted(existing_hues)
    
    interpolated_colors = []
    needed = target_count - len(existing)
    
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
        r, g, b = colorsys.hsv_to_rgb(best_midpoint, avg_s, avg_v)
        interpolated_colors.append(Color.from_srgb01((r, g, b)))
        working_hues.append(best_midpoint)
        working_hues.sort()
    
    result = [*existing, *interpolated_colors]
    logging.debug(f"Added {len(interpolated_colors)} interpolated colors")
    palette_absolute(result)
    
    return result


def seed(img: str, generation_strategy: str = "subtractive", subtractive_initial: int | None = None) -> list[Color]:
    """Return a list of candidate colors for the image."""
    if generation_strategy == "iterative":
        return gen_colors(img)
    return gen_colors_brightness(img, initial=subtractive_initial)


def get(img, light=False):
    # Backwards compat for callers; `light` unused here.
    _ = light
    return seed(img, generation_strategy=ARGS.generation_strategy, subtractive_initial=ARGS.subtractive_initial)
