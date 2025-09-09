from colorsys import rgb_to_hsv, hsv_to_rgb
from typing import List, Tuple
from . import util
import logging

def print_colored_square(r, g, b):
    r, g, b = round(r*255), round(g*255), round(b*255)
    print(f"\033[48;2;{r};{g};{b}m  \033[0m", end="")

def print_palette(colors):
    for color in colors:
        print_colored_square(*color)
        print_colored_square(*color)
        print_color(color)

def print_color(color):
        greyish = 'greyish' if is_greyish(*color) else ''
        h, s, v = rgb_to_hsv(*color)
        h = round(h * 360)
        s = f"{round(s * 100)}%"
        v = f"{round(v / 255 * 100)}%"
        print(' ', h, s, v, greyish)

# FILENAME = "/Users/murtaza/wallpapers/outrun.jpg"
#
# palette = ColorThief(FILENAME).get_palette(color_count=8)
# print_palette(palette)

TARGET_HUES = {k: v / 360 for k, v in {
    "red": 0,
    "green": 120,
    "yellow": 60,
    "blue": 240,
    "magenta": 300,
    "cyan": 180,
}.items()}

TARGET_COLORS = {
    "red": (0, 1, 1),
    "green": (120/360, 1, 1),
    "yellow": (60/360, 1, 1),
    "blue": (240/360, 1, 1),
    "magenta": (300/360, 1, 1),
    "cyan": (180/360, 1, 1),
}

HUE_TOLERANCES = {
    "red": 0.15,
    "green": 0.15,
    "yellow": 0.1,
    "blue": 0.15,
    "magenta": 0.15,
    "cyan": 0.15,
}

def color_distance(hsv_a, hsv_b):
    h1, s1, v1 = hsv_a
    h2, s2, v2 = hsv_b
    return ((4 * circle_distance(h1, h2)) ** 2 + (s1 - s2) ** 2 + (v1 - v2) ** 2) ** 0.5

def get_closest_target(color):
    # hue, _, _ = rgb_to_hsv(*color)
    # return min(TARGET_HUES, key=lambda k: circle_distance(hue, TARGET_HUES[k]))
    return min(
        TARGET_COLORS,
        key=lambda k: color_distance(rgb_to_hsv(*color), TARGET_COLORS[k])
    )
#
# clostest_match = {color: get_closest_match(color) for color in palette}
#
# sorted_by_hue = sorted(clostest_match.items(), key=lambda x: TARGET_HUES[x[1]])
#
# for color, match in sorted_by_hue:
#     print_colored_square(*color)
#     print_colored_square(*color)
#     print(' ', color, match)

def get_closest_palette_color(target, palette):
    closest = None
    closest_distance = float('inf')
    logging.debug('finding closest palette color to', target)
    for color in palette:
        # h, _, _ = rgb_to_hsv(*color)
        # distance = circle_distance(h, hue)
        # print_colored_square(*color)
        # print_colored_square(*color)
        hsv = rgb_to_hsv(*color)
        distance = color_distance(hsv, TARGET_COLORS[target])
        # print(distance)
        if distance < closest_distance:
            closest_distance = distance
            closest = color
    return closest

def is_greyish(r, g, b):
    h, s, v = rgb_to_hsv(r, g, b)
    return s < 0.1

# repeat until all colors are chosen: find closest color-target pair, remove both
def choose_colors_for_each_target(generated_palette):
    generated_palette = generated_palette[:]
    # remove greyish colors
    palette = {}
    remaining_targets = TARGET_HUES.copy()
    shortest = float('inf')
    candidate_target = 'red'
    candidate_color = generated_palette[0]
    # out of all target-pallete pairs, find the one with the shortest distance
    while remaining_targets:
        shortest = float('inf')
        for target, hue in remaining_targets.items():
            for color in generated_palette:
                h, _, _ = rgb_to_hsv(*color)
                distance = circle_distance(h, hue)
                if distance < shortest:
                    shortest = distance
                    candidate_target = target
                    candidate_color = color
        palette[candidate_target] = candidate_color
        del remaining_targets[candidate_target]
        generated_palette.remove(candidate_color)
    return palette

# proceed in order of target hues (red -> green -> yellow -> ...)
# the earlier colors have more semantic meaning so more important 
# to get right
def choose_colors_for_each_target2(generated_palette):
    generated_palette = generated_palette[:]
    palette = {}
    for target, hue in TARGET_HUES.items():
        # palette[target] = get_closest_palette_color_for_hue(hue, generated_palette)
        palette[target] = get_closest_palette_color(target, generated_palette)
        generated_palette.remove(palette[target])
    return palette


def circle_distance(a, b):
    return min(abs(a-b), abs(b-a+1), abs(a-b+1))

def circle_midpoint(a, b):
    m1 = (a + b) / 2
    m2 = (a + b + 1) / 2
    d_m1 = circle_distance(a, m1) + circle_distance(b, m1)
    d_m2 = circle_distance(a, m2) + circle_distance(b, m2)
    if d_m1 < d_m2:
        return m1
    return m2

def interpolate_hue(color_map, target: str):
    reversed_target_hues = {v: k for k, v in TARGET_HUES.items()}
    target_hue = TARGET_HUES[target] * 360
    next = (target_hue + 60) % 360 / 360
    prev = (target_hue - 60) % 360 / 360
    next_name = reversed_target_hues[next]
    prev_name = reversed_target_hues[prev]
    next_color = color_map[next_name]
    prev_color = color_map[prev_name]

    h, s, v = rgb_to_hsv(*next_color)
    h2, s2, v2 = rgb_to_hsv(*prev_color)
    new_h = circle_midpoint(h, h2)
    new_s = (s + s2) / 2
    new_v = (v + v2) / 2
    new_color = tuple(int(p) for p in hsv_to_rgb(new_h, new_s, new_v))
    logging.debug("interpolated between", next_name, "and", prev_name, "to get", target, "color:")
    # print_colored_square(*new_color)
    # print_colored_square(*new_color)
    # print(' ', new_color)
    return new_color

def offset_target_hue(h, target_h, push_amount=0.15):
    increased = (target_h + push_amount) % 1
    decreased = (target_h - push_amount) % 1
    if circle_distance(increased, h) < circle_distance(decreased, h):
        return increased
    return decreased

def interpolate_by_avg_sv(color_map, target: str, tolerance):
    original = color_map[target]
    # push the target hue towards the actual hue
    h, _, _ = rgb_to_hsv(*original)
    target_hue = TARGET_HUES[target]
    new_h = offset_target_hue(h, target_hue, tolerance)
    avg_s = sum(rgb_to_hsv(*color_map[t])[1] for t in color_map) / len(color_map)
    avg_v = sum(rgb_to_hsv(*color_map[t])[2] for t in color_map) / len(color_map)
    # # dull color since it wasnt part of the palette
    avg_s = avg_s/2
    avg_v = avg_v * 0.8
    new_color = tuple(p for p in hsv_to_rgb(new_h, avg_s, avg_v))
    logging.debug("interpolated by avg s and v to get", target, "color:", end='')
    # print_colored_square(*new_color)
    # print_colored_square(*new_color)
    # print()
    return new_color

def fix_bad_colors(color_map):
    targets_to_fix = ["red", "yellow", "green"]
    for target, color in color_map.items():
        if target not in targets_to_fix:
            continue
        target_hue = TARGET_HUES[target]
        h, s, v = rgb_to_hsv(*color)
        tol = HUE_TOLERANCES[target]
        if circle_distance(h, target_hue) > tol:
            logging.warning(f"bad match for {target} {color} interpolated")
            color_map[target] = interpolate_by_avg_sv(color_map, target, tol)


def categorize_palette(colors):
    for color in colors:
        print_colored_square(*color)
        print_colored_square(*color)
        # print_color(color)
        target = get_closest_target(color)
        hue = int(rgb_to_hsv(*color)[0] * 360)
        hsv = rgb_to_hsv(*color)
        target_hsv = TARGET_COLORS[target]
        d = color_distance(hsv, target_hsv)
        print(' ', target, hue, f'{d:.2f}')

def get_ansi_color_mapping(raw_palette: List[str]) -> dict:
    """Get a mapping of ANSI color names to hex colors from a palette.
    
    Args:
        raw_palette: List of hex color strings
        
    Returns:
        dict: Mapping of color names (red, green, etc.) to hex colors
    """
    colors = [util.hex_to_rgb(color) for color in raw_palette]
    black = colors[0]
    white = colors[-1]
    colors = [(r/255, g/255, b/255) for (r, g, b) in colors]
    logging.debug(colors)
    colors = colors[1:-1]
    palette = [color for color in colors if not is_greyish(*color)]
    assert len(palette) >= 6, "too many greyish colors"
    categorize_palette(palette)
    palette = choose_colors_for_each_target2(palette)
    fix_bad_colors(palette)
    
    # Convert back to hex and create mapping
    ansi_mapping = {}
    for color_name, (r, g, b) in palette.items():
        ansi_mapping[color_name] = util.rgb_to_hex((round(r*255), round(g*255), round(b*255)))
    
    # Add black and white
    ansi_mapping["black"] = util.rgb_to_hex(black)
    ansi_mapping["white"] = util.rgb_to_hex(white)
    
    return ansi_mapping

def rearrange_palette(raw_palette: List[Tuple[int, int, int]]):
    colors = [util.hex_to_rgb(color) for color in raw_palette]
    black = colors[0]
    white = colors[-1]
    colors = [(r/255, g/255, b/255) for (r, g, b) in colors]
    logging.debug(colors)
    colors = colors[1:-1]
    palette = [color for color in colors if not is_greyish(*color)]
    assert len(palette) >= 6, "too many greyish colors"
    categorize_palette(palette)
    palette = choose_colors_for_each_target2(palette)
    fix_bad_colors(palette)
    palette = {k: (round(r*255), round(g*255), round(b*255)) for k, (r, g, b) in palette.items()}
    # for target, color in palette.items():
    #     print_colored_square(*color)
    #     print_colored_square(*color)
        # print(' ', target, util.rgb_to_hex(color))
    out = [util.rgb_to_hex(c) for c in (
        black,
        palette['red'],
        palette['green'],
        palette['yellow'],
        palette['blue'],
        palette['magenta'],
        palette['cyan'],
        white
    )]
    # print(out)
    return out
