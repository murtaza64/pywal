from colorsys import rgb_to_hsv, hsv_to_rgb
from typing import List, Tuple
import logging
import colorsys

from . import oklab
from .color import Color, VERBOSE

def get_colored_square_from_rgb01(r: float, g: float, b: float) -> str:
    r8, g8, b8 = round(r * 255), round(g * 255), round(b * 255)
    return f"\033[48;2;{r8};{g8};{b8}m  \033[0m"


def get_colored_square(c: Color) -> str:
    r, g, b = c.rgb8
    return f"\033[48;2;{r};{g};{b}m  \033[0m"

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
    "green": (120 / 360, 1, 1),
    # Yellow sRGB primary (#ffff00) skews yellow-green in OKLCH.
    # Use a warmer canonical yellow.
    "yellow": colorsys.rgb_to_hsv(0xDE / 255, 0xC8 / 255, 0x38 / 255),
    "blue": (240 / 360, 1, 1),
    "magenta": (300 / 360, 1, 1),
    "cyan": (180 / 360, 1, 1),
}


def _target_oklch_hue_rad() -> dict[str, float]:
    """Target hues in OKLCH hue space.

    Important: HSV hue degrees are not comparable to OKLCH hue radians.
    Tolerance checks should use the same hue space as the candidate colors.
    """
    out: dict[str, float] = {}
    for name, (h, s, v) in TARGET_COLORS.items():
        rgb = colorsys.hsv_to_rgb(h, s, v)
        out[name] = float(Color.from_srgb01(rgb).oklch.h_rad)
    return out


TARGET_OKLCH_HUE_RAD = _target_oklch_hue_rad()

# Manually tuned green target hue to 145° OKLCH (from default ~142.5°)
# to better center the acceptable range and avoid yellow-greens
TARGET_OKLCH_HUE_RAD["green"] = 2.530727  # 145° in radians

HUE_TOLERANCES = {
    "red": 0.15,
    "green": 30 / 360,  # 30° (0.0833) - Manually tuned to exclude yellow-greens while accepting cyan-greens
    "yellow": 0.1,
    "blue": 0.15,
    "magenta": 0.15,
    "cyan": 0.15,
}


def _normalize_rad(h: float) -> float:
    two_pi = 6.283185307179586
    return h % two_pi


def _circle_distance_rad(a: float, b: float) -> float:
    two_pi = 6.283185307179586
    d = abs(a - b) % two_pi
    return min(d, two_pi - d)


def _offset_target_hue_rad(candidate_h: float, target_h: float, push_amount: float) -> float:
    candidate_h = _normalize_rad(candidate_h)
    target_h = _normalize_rad(target_h)
    two_pi = 6.283185307179586
    increased = (target_h + push_amount) % two_pi
    decreased = (target_h - push_amount) % two_pi
    if _circle_distance_rad(increased, candidate_h) < _circle_distance_rad(decreased, candidate_h):
        return increased
    return decreased


def _oklab_distance(a: oklab.OKLab, b: oklab.OKLab) -> float:
    return ((a.L - b.L) ** 2 + (a.a - b.a) ** 2 + (a.b - b.b) ** 2) ** 0.5


def _target_oklab() -> dict[str, oklab.OKLab]:
    out: dict[str, oklab.OKLab] = {}
    for name, hsv in TARGET_COLORS.items():
        rgb = hsv_to_rgb(*hsv)
        out[name] = Color.from_srgb01(rgb).oklab
    return out


TARGET_OKLAB = _target_oklab()

def get_closest_target(color: Color) -> str:
    return min(TARGET_OKLAB, key=lambda k: _oklab_distance(color.oklab, TARGET_OKLAB[k]))
#
# clostest_match = {color: get_closest_match(color) for color in palette}
#
# sorted_by_hue = sorted(clostest_match.items(), key=lambda x: TARGET_HUES[x[1]])
#
# for color, match in sorted_by_hue:
#     print_colored_square(*color)
#     print_colored_square(*color)
#     print(' ', color, match)

def hsvformat(hsv):
    h, s, v = hsv
    h = round(h * 360)
    s = f"{round(s * 100)}%"
    v = f"{round(v * 100)}%"
    return f"{h}, {s}, {v}"

def get_closest_palette_color(target: str, palette: list[Color]) -> Color:
    closest = palette[0]
    closest_distance = float("inf")
    logging.debug(f"finding closest palette color to {target} ({hsvformat(TARGET_COLORS[target])})")
    for color in palette:
        sq = get_colored_square(color)
        hsv = color.hsv
        distance = _oklab_distance(color.oklab, TARGET_OKLAB[target])
        logging.log(VERBOSE, f"{sq}{sq} ({hsvformat(hsv)}) d={distance:.2f}")
        if distance < closest_distance:
            closest_distance = distance
            closest = color
    sq = get_colored_square(closest)
    logging.debug(f"closest: {sq*2} ({hsvformat(closest.hsv)}) d={closest_distance:.2f}")
    return closest

def is_greyish(r: float, g: float, b: float) -> bool:
    return Color.from_srgb01((r, g, b)).is_greyish()

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
def choose_colors_for_each_target2(generated_palette: list[Color]) -> dict[str, Color]:
    generated_palette = generated_palette[:]
    palette: dict[str, Color] = {}

    # Pre-calculate average chroma and lightness from original palette.
    avg_c = sum(c.oklch.C for c in generated_palette) / len(generated_palette)
    avg_l = sum(c.oklch.L for c in generated_palette) / len(generated_palette)

    targets_to_fix = ["red", "yellow", "green", "blue"]

    for target in TARGET_HUES:
        candidate_color = get_closest_palette_color(target, generated_palette)

        if target in targets_to_fix:
            target_hue_rad = TARGET_OKLCH_HUE_RAD[target]
            candidate_hue_rad = _normalize_rad(candidate_color.oklch.h_rad)
            tol = HUE_TOLERANCES[target]
            tol_rad = tol * 6.283185307179586
            dist_rad = _circle_distance_rad(candidate_hue_rad, target_hue_rad)

            logging.debug(
                f"{target}: target_hue_oklch={(target_hue_rad*180/3.141592653589793):.1f} candidate_hue_oklch={(candidate_hue_rad*180/3.141592653589793):.1f} distance={(dist_rad*180/3.141592653589793):.1f} tolerance={tol*360}"
            )
            logging.log(
                VERBOSE,
                f"{target}: target_hue_oklch={(target_hue_rad*180/3.141592653589793):.1f} candidate_hue_oklch={(candidate_hue_rad*180/3.141592653589793):.1f} distance={(dist_rad*180/3.141592653589793):.1f} tolerance={tol*360}",
            )

            if dist_rad > tol_rad:
                palette[target] = interpolate_by_avg_sv(candidate_color, target, tol_rad, avg_c, avg_l)
                sq_old = get_colored_square(candidate_color)
                sq = get_colored_square(palette[target])
                logging.warning(f"bad match for {target} interpolated from {sq_old*2} to {sq*2}")
            else:
                palette[target] = candidate_color
                generated_palette.remove(candidate_color)
        else:
            palette[target] = candidate_color
            generated_palette.remove(candidate_color)

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
    logging.log(VERBOSE, "interpolated between", next_name, "and", prev_name, "to get", target, "color:")
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

def interpolate_by_avg_sv(original_color: Color, target: str, tolerance_rad: float, avg_c: float, avg_l: float) -> Color:
    # Bad match: synthesize a centered target color.
    # Don't push to the tolerance boundary; don't dull/darken; use palette averages.
    _ = original_color
    _ = tolerance_rad
    new_h = TARGET_OKLCH_HUE_RAD[target]

    new_c = avg_c
    new_l = avg_l

    new_color = Color.from_oklch(oklab.OKLCH(L=new_l, C=new_c, h_rad=new_h))
    sq = get_colored_square(new_color)
    logging.log(VERBOSE, f"synthesized by avg L/C to get {target} color: {sq}{sq}")
    return new_color

# def fix_bad_colors(color_map):
#     targets_to_fix = ["red", "yellow", "green"]
#     for target, color in color_map.items():
#         if target not in targets_to_fix:
#             continue
#         target_hue = TARGET_HUES[target]
#         h, s, v = rgb_to_hsv(*color)
#         tol = HUE_TOLERANCES[target]
#         if circle_distance(h, target_hue) > tol:
#             logging.warning(f"bad match for {target} {color} interpolated")
#             color_map[target] = interpolate_by_avg_sv(color_map, target, tol)


def categorize_palette(colors: list[Color]):
    logging.debug("categorizing palette")
    for color in colors:
        sq = get_colored_square(color)
        target = get_closest_target(color)
        d = _oklab_distance(color.oklab, TARGET_OKLAB[target])
        logging.log(VERBOSE, f"{sq*2}{sq} ({hsvformat(color.hsv)}) ~ {target}  d={d:.2f}")

def get_ansi_color_mapping(black: Color, white: Color, candidates: List[Color]) -> dict[str, Color]:
    """Map palette colors to ANSI names.

    `black` and `white` are terminal slots (theme background-ish / foreground-ish),
    not literal colors.
    """
    palette = [c for c in candidates if not c.is_greyish()]
    if len(palette) < 6:
        palette = [c for c in candidates if not c.is_greyish(chroma_threshold=0.02)]
    if len(palette) < 6:
        palette = candidates[:]

    if len(palette) < 6:
        raise AssertionError("too many greyish colors")

    categorize_palette(palette)
    palette = choose_colors_for_each_target2(palette)
    
    # Convert back to hex and create mapping
    ansi_mapping = {}
    for color_name, c in palette.items():
        ansi_mapping[color_name] = c
    
    # Add black and white
    ansi_mapping["black"] = black
    ansi_mapping["white"] = white
    
    return ansi_mapping

def rearrange_palette(raw_palette: List[Color]) -> list[Color]:
    black = raw_palette[0]
    white = raw_palette[-1]
    palette = [c for c in raw_palette[1:-1] if not c.is_greyish()]
    if len(palette) < 6:
        palette = [c for c in raw_palette[1:-1] if not c.is_greyish(chroma_threshold=0.02)]
    if len(palette) < 6:
        palette = raw_palette[1:-1]
    if len(palette) < 6:
        raise AssertionError("too many greyish colors")

    categorize_palette(palette)
    chosen = choose_colors_for_each_target2(palette)
    return [
        black,
        chosen["red"],
        chosen["green"],
        chosen["yellow"],
        chosen["blue"],
        chosen["magenta"],
        chosen["cyan"],
        white,
    ]
