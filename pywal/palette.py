"""Palette generation pipeline.

This project uses the `pywal.colorthief` backend exclusively.
"""

import logging
import os
import random
import re
import sys
import colorsys

from .args import ARGS, get_save_dict
from .util import get_cache_dir
from . import theme
from . import util
from . import match
from .print import palette_absolute
from .settings import __cache_version__
from .color import Color, rgb_to_hex
from . import colorthief

# Foreground color thresholds for white-ish appearance
COLOR_7_MAX_SATURATION = 0.2
COLOR_7_MIN_BRIGHTNESS = 0.7
FG_MAX_SATURATION = 0.12
FG_MIN_BRIGHTNESS = 0.8


def _fmt_oklch(c: Color) -> str:
    lch = c.oklch
    # Hue is undefined for near-neutral, but still print for debugging.
    h_deg = (lch.h_rad * 180.0 / 3.141592653589793) % 360.0
    return f"L={lch.L:.3f} C={lch.C:.3f} h={h_deg:.1f}"


def _fmt_hsv(c: Color) -> str:
    h, s, v = c.hsv
    return f"h={h*360:.1f} s={s:.3f} v={v:.3f}"


def _log_color(tag: str, c: Color) -> None:
    logging.debug(
        "%s %s rgb=%s %s %s lum=%.3f",
        tag,
        c.hex_color,
        c.rgb8,
        _fmt_hsv(c),
        _fmt_oklch(c),
        c.w3_luminance,
    )


def list_backends():
    """List available backends (project uses colorthief only)."""
    return ["colorthief"]


def normalize_img_path(img: str):
    """Normalizes the image path for output."""
    if os.name == "nt":
        # On Windows, the JSON.dump ends up outputting un-escaped backslash
        # breaking the ability to read colors.json. Windows supports forward
        # slash, so we can use that for now
        return img.replace("\\", "/")
    return img


def colors_to_dict(colors: dict[int | str, Color], img):
    """Convert list of colors to pywal format."""
    logging.debug("Converting colors to dictionary")

    _log_color("export background", colors["background"])
    _log_color("export foreground", colors["foreground"])

    light = ARGS.light
    shading = ARGS.shading
    color_dict = {
        "settings": get_save_dict(),
        "checksum": util.get_img_checksum(img),
        "wallpaper": normalize_img_path(img),
        "alpha": Color.alpha_num,
        "special": {
            "background": colors["background"].hex_color,
            "foreground": colors["foreground"].hex_color,
            "cursor": colors["foreground"].hex_color,
        },
    }
    # Convert integer colors to color0, color1, ... and export as hex strings.
    colors_hex: dict[str, str] = {}
    for k, v in colors.items():
        key = k if isinstance(k, str) else f"color{k}"
        colors_hex[str(key)] = v.hex_color
    color_dict["colors"] = colors_hex

    # Surfaces
    surface_colors: dict[str, str] = {}
    if light:
        # Light theme: surfaces should be darker than background.
        for i in range(6):
            shade_amount = (i + 1) * (0.20 / 7)  # ~0.029 .. 0.171
            s = colors["background"].darken_amount(shade_amount)
            _log_color(f"surface{i}", s)
            surface_colors[f"surface{i}"] = s.hex_color
    else:
        # Dark theme: surfaces are lighter than background.
        for i in range(6):
            shade_amount = (i + 1) * (0.6 / 7)
            s = colors["background"].lighten_amount(shade_amount)
            _log_color(f"surface{i}", s)
            surface_colors[f"surface{i}"] = s.hex_color
    
    colors_hex.update(surface_colors)

    # Print surface colors
    logging.debug("Surface colors:")
    surface_values = [colors_hex[f"surface{i}"] for i in range(6)]
    palette_absolute(surface_values)

    # Subsurfaces
    subsurface_colors: dict[str, str] = {}
    if light:
        for i, shade_amount in enumerate((0.20, 0.32, 0.45)):
            s = colors["background"].darken_amount(shade_amount)
            _log_color(f"subsurface{i}", s)
            subsurface_colors[f"subsurface{i}"] = s.hex_color
    else:
        for i, shade_amount in enumerate((0.15, 0.30, 0.45)):
            s = colors["background"].darken_amount(shade_amount)
            _log_color(f"subsurface{i}", s)
            subsurface_colors[f"subsurface{i}"] = s.hex_color

    colors_hex.update(subsurface_colors)

    logging.debug("Subsurface colors:")
    subsurface_values = [colors_hex[f"subsurface{i}"] for i in range(3)]
    palette_absolute(subsurface_values)
    
    
    # Generate bright variants of ANSI colors
    # ansi_bright = {
    #     "bright_black": color_dict["surfaces"]["surface2"],
    #     "bright_white": colors[15],
    # }
    
    # # Apply 16-color shading logic to middle colors
    # middle_colors = ["red", "green", "yellow", "blue", "magenta", "cyan"]
    # for color_name in middle_colors:
    #     base_color = ansi_mapping[color_name]
    #     if light:
    #         if shading == "lighten":
    #             bright_color = util.lighten_color(base_color, 0.25)
    #             bright_color = util.saturate_color(bright_color, 0.40)
    #         else:  # darken mode
    #             bright_color = util.darken_color(base_color, 0.25) 
    #     else:  # dark theme
    #         bright_color = util.lighten_color(base_color, 0.25)
    #
    #     ansi_bright[f"bright_{color_name}"] = bright_color
    #
    # # Add bright colors to ANSI mapping
    # ansi_mapping.update(ansi_bright)
    
    
    # color_dict["ansi"] = ansi_mapping
    

    # Persist derived colors in exported color map.
    color_dict["colors"].update(surface_colors)
    color_dict["colors"].update(subsurface_colors)
    return color_dict


def colors_to_base_dict(colors_list) -> dict[str | int, Color]:
    """Convert 8-color list to integer-indexed dict format for shade_16."""
    return {i: colors_list[i] for i in range(min(8, len(colors_list)))}


def adjust_to_fg_thresholds(color: Color, sat_threshold: float, brightness_threshold: float) -> Color:
    """Adjust a color to meet foreground thresholds (low saturation, high brightness)."""
    h, s, v = color.hsv
    
    logging.debug(f"Adjusting fg color {color} (s={s:.2f}, v={v:.2f}) to meet thresholds")
    
    adjusted_color = color
    
    # Reduce saturation if too high (desaturate to make more white-ish)
    if s > sat_threshold:
        # Calculate how much to desaturate: current saturation - target
        desaturate_amount = -(s - sat_threshold)  # negative value for desaturation
        adjusted_color = adjusted_color.add_saturation_amount(desaturate_amount)
    
    # # Increase brightness if too low
    # if v < brightness_threshold:
    #     # Calculate target brightness increase
    #     target_brightness = brightness_threshold
    #     adjusted_color = util.brighten_color(adjusted_color, target_brightness, debug=True)
    adjusted_color = adjusted_color.brighten_min_lightness(brightness_threshold)
    
    return adjusted_color


def shade_16(colors: dict[int | str, Color], light: bool, shading: str):
    """Generate 16-color palette from 8 base colors
    this function expects an 8-color dict input and expands it to 16 colors

    colors: dict (expected to have integer keys 0 through 7)
    light:  boolean - whether the colorscheme is light
    shading: str [lighten|darken] - method to generate the shades"""

    dark_to_light_map = {k: v for k, v in {
        0: 8,
        1: 9,
        2: 10,
        3: 11,
        4: 12,
        5: 13,
        6: 14,
        7: 15,
        # "black": "bright_black",
        "red": "bright_red",
        "green": "bright_green",
        "yellow": "bright_yellow",
        "blue": "bright_blue",
        "magenta": "bright_magenta",
        "cyan": "bright_cyan",
        "white": "bright_white",
    }.items() if k in colors}

    # middle colors
    for orig, bright in dark_to_light_map.items():
        if light and shading == "lighten":
            colors[bright] = colors[orig].lighten_amount(0.25)
        elif light and shading == "darken":
            colors[bright] = colors[orig].darken_amount(0.25)
        elif not light and shading == "lighten":
            colors[bright] = colors[orig].lighten_amount(0.25).saturate_to(0.40)
        elif not light and shading == "darken":
            colors[bright] = colors[orig]
            colors[orig] = colors[orig].darken_amount(0.25)
        else:
            raise ValueError("Invalid shading strategy")

    # bg and fg
    if light:
        # Light theme: Generate colors 8-15 based on colors 0-7
        logging.debug("    Light theme - Generating bright colors 8-15:")
        colors["bright_black"] = colors["background"].darken_amount(0.25)
        # colors[15] = util.darken_color(colors[0], 0.75)
    else:
        # Dark theme: Generate colors 8-15 based on colors 0-7
        logging.debug("    Dark theme - Generating bright colors 8-15:")
        # colors[15] = util.lighten_color(colors[0], 0.75, debug=True)

        # bright bg
        colors["bright_black"] = colors["background"].lighten_amount(0.35).saturate_to(0.10)

    # colors["white"] = colors[7]
    # colors["bright_white"] = colors[15]
    # colors["bright_black"] = colors[8]
    # colors["foreground"] = colors["bright_white"]

def adjust_background(color: Color, light: bool, bg_strategy: str, reference: Color | None = None) -> Color:
    """Derive background color from a seed.

    If ARGS.bg_lightness / ARGS.bg_chroma are unset, compute targets from the
    seed + strategy and persist the chosen values back into ARGS for saving.
    """
    ref_h = reference.oklch.h_rad if reference is not None else color.oklch.h_rad
    user_L = getattr(ARGS, "bg_lightness", None)
    user_C = getattr(ARGS, "bg_chroma", None)

    def _clamp01(x: float) -> float:
        if x < 0.0:
            return 0.0
        if x > 1.0:
            return 1.0
        return x

    def _clamp(x: float, lo: float, hi: float) -> float:
        if x < lo:
            return lo
        if x > hi:
            return hi
        return x

    lch = color.oklch

    if light:
        if user_L is None:
            target_L = _clamp(lch.L, 0.84, 0.94) if bg_strategy == "average" else _clamp(lch.L, 0.82, 0.92)
        else:
            target_L = _clamp01(float(user_L))

        if user_C is None:
            target_C = _clamp(lch.C, 0.02, 0.16) if bg_strategy == "average" else _clamp(lch.C, 0.02, 0.12)
        else:
            target_C = max(0.0, float(user_C))

    else:
        if user_L is None:
            max_L = 0.18 if bg_strategy == "average" else 0.20
            target_L = _clamp(lch.L, 0.05, max_L)
        else:
            target_L = _clamp01(float(user_L))

        if user_C is None:
            target_C = _clamp(lch.C, 0.01, 0.10)
        else:
            target_C = max(0.0, float(user_C))

    # Persist chosen values for colors.json settings.
    ARGS.bg_lightness = target_L
    ARGS.bg_chroma = target_C

    return color.with_oklch(L=target_L, C=target_C, h_rad=ref_h)

def apply_light_theme_tuning(candidates: list[Color], light: bool) -> list[Color]:
    """Apply light-theme tuning to a seed palette."""
    if light:
        logging.debug("Light theme: Saturating and darkening seed candidates:")
        for i in range(len(candidates)):
            candidates[i] = candidates[i].saturate_to(0.60).darken_amount(0.5)

    # Adjust foreground color to meet white-ish thresholds
    # colors[7] = adjust_to_fg_thresholds(colors[7], COLOR_7_MAX_SATURATION, COLOR_7_MIN_BRIGHTNESS)

    logging.debug("After apply_light_theme_tuning:")
    palette_absolute(candidates)
    return candidates

def saturate_colors(candidates: list[Color], amount):
    """Saturate all colors."""
    if amount and (float(amount) <= 1.0 and float(amount) >= -1.0):
        logging.debug(f"Saturating colors (amount: {amount}):")
        for i, _ in enumerate(candidates):
            candidates[i] = candidates[i].add_saturation_amount(float(amount))

    return candidates

def brighten_colors(candidates: list[Color], min_brightness):
    """Brighten all colors."""
    logging.debug(f"Brightening colors (min_brightness: {min_brightness}):")
    for i, _ in enumerate(candidates):
        candidates[i] = candidates[i].brighten_min_lightness(min_brightness)

    return candidates


def ensure_contrast(candidates: list[Color], contrast, light: bool, image):
    """Ensure user-specified W3 contrast of colors
    depending on dark or light theme."""
    # If no contrast checking was specified, do nothing
    if contrast in (None, ""):
        return candidates

    # Allow explicit disable.
    try:
        if float(contrast) == 0:
            return candidates
    except ValueError:
        logging.error("ensure_contrast(): Contrast value could not be parsed")
        return candidates

    # Contrast must be within a predefined range
    if float(contrast) < 1 or float(contrast) > 21:
        logging.error("Specified contrast ratio is too extreme")
        return candidates

    # Use a slightly darkened wallpaper average as baseline.
    background_color = Color(util.image_average_color(image)).darken_amount(0.12)
    background_luminance = background_color.w3_luminance

    # Calculate the required W3 luminance for the desired contrast ratio
    # This will modify all of the colors to be brighter or darker than the
    # background image depending on whether the user has specified for a
    # dark or light theme
    try:
        if light:
            luminance_desired = (background_luminance + 0.05) / float(
                contrast
            ) - 0.05
        else:
            luminance_desired = (background_luminance + 0.05) * float(
                contrast
            ) - 0.05
    except ValueError:
        logging.error("ensure_contrast(): Contrast valued could not be parsed")
        return candidates

    if luminance_desired >= 0.99:
        logging.debug("Clamping desired luminance to 0.99")
        luminance_desired = 0.99
    if luminance_desired <= 0.01:
        logging.debug("Clamping desired luminance to 0.01")
        luminance_desired = 0.01

    # Determine which colors should be modified / checked
    # ! For the time being this is just going to modify all the colors except
    # 0 and 15
    colors_to_contrast = range(len(candidates))

    # Modify colors
    for index in colors_to_contrast:
        color = candidates[index]

        # If the color already has sufficient contrast, do nothing
        if light and color.w3_luminance <= luminance_desired:
            continue
        elif color.w3_luminance >= luminance_desired:
            continue

        h, s, v = colorsys.rgb_to_hsv(
            float(color.red), float(color.green), float(color.blue)
        )

        # Determine how to modify the color based on its HSV characteristics

        # If the color is to be lighter than background, and the HSV color
        # with value 1 has sufficient luminance, adjust by increasing value
        if (
            not light
            and Color.from_srgb01(colorsys.hsv_to_rgb(h, s, 1)).w3_luminance
            >= luminance_desired
        ):
            candidates[index] = binary_luminance_adjust(luminance_desired, h, s, s, v, 1)
        # If the color is to be lighter than background and increasing value
        # to 1 doesn't produce the desired luminance, additionally decrease
        # saturation
        elif not light:
            candidates[index] = binary_luminance_adjust(luminance_desired, h, 0, s, 1, 1)
        # If the color is to be darker than background, produce desired
        # luminance by decreasing value, and raising saturation
        else:
            candidates[index] = binary_luminance_adjust(luminance_desired, h, s, 1, 0, v)

    return candidates


def binary_luminance_adjust(
    luminance_desired, hue, s_min, s_max, v_min, v_max, iterations=10
) -> Color:
    """Use a binary method to adjust a color's value and/or
    saturation to produce the desired luminance"""
    s = (s_min + s_max) / 2
    v = (v_min + v_max) / 2
    for _ in range(iterations):
        # Obtain a new color by averaging saturation and value
        s = (s_min + s_max) / 2
        v = (v_min + v_max) / 2

        # Compare the luminance of this color to the target luminance
        # If the color is too light, clamp the minimum saturation
        # and maximum value
        if Color.from_srgb01(colorsys.hsv_to_rgb(hue, s, v)).w3_luminance >= luminance_desired:
            s_min = s
            v_max = v
        # If the color is too dark, clamp the maximum saturation
        # and minimum value
        else:
            s_max = s
            v_min = v

    return Color.from_srgb01(colorsys.hsv_to_rgb(hue, s, v))

def cache_fname(img, backend, light, cache_dir):
    """Create the cache file name."""
    color_type = "light" if light else "dark"
    file_name = re.sub("[/|\\|.]", "_", img)
    file_size = os.path.getsize(img)

    file_parts = [
        file_name,
        color_type,
        backend,
        file_size,
        __cache_version__,
    ]
    return os.path.join(
        cache_dir,
        "schemes",
        "%s_%s_%s_%s_%s.json" % (*file_parts,),
    )

def get_brightness(color: Color) -> float:
    return color.hsv[2]

def get_saturation(color: Color) -> float:
    return color.hsv[1]

def choose_8(bg: Color, fg: Color, candidates: list[Color], ansi_mapping: dict[str, Color]) -> dict[int | str, Color]:
    # first (darkest), last (brightest) and 6 middle colors
    # choose either the same colors as the ansi colors
    # or the 6 most saturated colors
    # or the 6 most bright colors
    # or 6 random colors
    # for now, return 6 random colors
    middle_colors = candidates[:]

    choose_method = ARGS.choose or "brightness"
    if choose_method == "random":
        logging.debug("Shuffling middle colors randomly")
        random.shuffle(middle_colors)
    elif choose_method == "brightness":
        logging.debug("Sorting middle colors by brightness")
        middle_colors = sorted(middle_colors, key=get_brightness, reverse=True)
    elif choose_method == "saturation":
        logging.debug("Sorting middle colors by saturation")
        middle_colors = sorted(middle_colors, key=get_saturation, reverse=True)
    elif choose_method == "ansi":
        logging.debug("Choosing middle colors based on ANSI mapping")
        middle_colors = [ansi_mapping[color] for color in ["red", "green", "yellow", "blue", "magenta", "cyan"]]
    elif choose_method == "ansi-shuffle":
        logging.debug("Choosing middle colors based on ANSI mapping and shuffling")
        middle_colors = [ansi_mapping[color] for color in ["red", "green", "yellow", "blue", "magenta", "cyan"]]
        random.shuffle(middle_colors)
    elif choose_method == "ansi-brightness":
        logging.debug("Choosing middle colors based on ANSI mapping and sorting by brightness")
        middle_colors = [ansi_mapping[color] for color in ["red", "green", "yellow", "blue", "magenta", "cyan"]]
        middle_colors = sorted(middle_colors, key=get_brightness, reverse=True)
    elif choose_method == "ansi-saturation":
        logging.debug("Choosing middle colors based on ANSI mapping and sorting by saturation")
        middle_colors = [ansi_mapping[color] for color in ["red", "green", "yellow", "blue", "magenta", "cyan"]]
        middle_colors = sorted(middle_colors, key=get_saturation, reverse=True)
    elif choose_method == "backend":
        logging.debug("Keeping original middle colors order from backend")
    else:
        logging.error(f"Unknown choose method: {choose_method}, defaulting to brightness")
        sys.exit(1)


    while len(middle_colors) < 8:
        logging.warning("Not enough middle colors, padding with foreground color")
        middle_colors.append(fg)  # TODO pad with fg color if not enough colors

    colors_dict: dict[int | str, Color] = {
        "background": bg,
        "white": fg,
    }
    for i, color in enumerate(middle_colors[:8]):
        colors_dict[i] = color
    selected = [bg] + middle_colors[:8] + [fg]
    logging.debug("Selected bg + 8 + fg colors:")
    palette_absolute(selected)
    return colors_dict

def get(img, cache_dir=None):
    """Generate a palette."""
    if cache_dir is None:
        cache_dir = get_cache_dir()
    # Get values from global args
    light = ARGS.light
    backend = "colorthief"
    saturation_to_add = ARGS.saturate / 100 if ARGS.saturate else 0
    min_brightness = ARGS.brightness / 100 if ARGS.brightness else 0
    no_cache = ARGS.no_cache
    contrast = ARGS.contrast

    # Ensure deterministic palette generation across repeated calls
    # (e.g. the web UI), matching the CLI behavior.
    if not getattr(ARGS, "seed", None):
        ARGS.seed = random.randint(0, sys.maxsize)
    random.seed(int(ARGS.seed))
    logging.info("RNG seed: %s", ARGS.seed)

    # cache only image
    cache_file = cache_fname(img, backend, light, cache_dir)

    # Check the wallpaper's checksum against the cache'
    if not no_cache and os.path.isfile(cache_file) and theme.parse(cache_file)[
        "checksum"
    ] == util.get_img_checksum(img):
        colors = theme.file(cache_file)
        logging.info("Found cached colorscheme.")
        return colors

    logging.info("Generating a colorscheme.")
    logging.info("Using %s backend.", backend)

    bg_strategy = getattr(ARGS, "bg_strategy", "backend")
    backend_colors = colorthief.seed(
        img,
        generation_strategy=ARGS.generation_strategy,
        subtractive_initial=ARGS.subtractive_initial,
    )
    if not backend_colors:
        raise AssertionError("backend returned no colors")

    def _yiq(c: Color) -> float:
        # colorsys.rgb_to_yiq returns (Y, I, Q); we want Y (luma-like).
        return float(colorsys.rgb_to_yiq(*c.srgb)[0])

    non_grey = [c for c in backend_colors if not c.is_greyish()]
    darkest_pool = non_grey if non_grey else backend_colors
    darkest_candidate = min(darkest_pool, key=_yiq)

    brightest_pool = [c for c in backend_colors if c != darkest_candidate]
    brightest_candidate = max(brightest_pool if brightest_pool else backend_colors, key=_yiq)

    # Background/foreground seeds.
    # - Dark themes: dark background + bright foreground.
    # - Light themes: bright background + dark foreground.
    if bg_strategy == "average":
        background_seed = Color(util.image_average_color(img))
        foreground_seed = darkest_candidate if light else brightest_candidate
        candidates = [c for c in backend_colors if c != foreground_seed]
    else:
        if light:
            background_seed = brightest_candidate
            foreground_seed = darkest_candidate
        else:
            background_seed = darkest_candidate
            foreground_seed = brightest_candidate
        candidates = [c for c in backend_colors if c != background_seed and c != foreground_seed]

    _log_color("seed bg", background_seed)
    _log_color("seed fg", foreground_seed)
    for i, c in enumerate(candidates[:6]):
        _log_color(f"seed cand[{i}]", c)

    logging.debug("Backend candidate colors:")
    palette_absolute([background_seed, *candidates[:12], brightest_candidate])

    candidates = apply_light_theme_tuning(candidates, light)
    for i, c in enumerate(candidates[:6]):
        _log_color(f"tuned cand[{i}]", c)

    ref_pool = [*candidates, background_seed, foreground_seed]
    ref = max(ref_pool, key=lambda c: c.oklch.C) if ref_pool else background_seed
    background = adjust_background(background_seed, light, bg_strategy=bg_strategy, reference=ref)
    _log_color("adjusted background", background)

    if saturation_to_add:
        # Post-processing steps from command-line arguments
        candidates = saturate_colors(candidates, saturation_to_add)
        logging.debug("After saturation adjustment:")
        palette_absolute(candidates)

    if min_brightness:
        candidates = brighten_colors(candidates, min_brightness)
        logging.debug("After brightness adjustment:")
        palette_absolute(candidates)

    if contrast:
        candidates = ensure_contrast(candidates, contrast, light, img)
        logging.debug("After contrast adjustment:")
        palette_absolute(candidates)


    # Generate ANSI color mapping (now default behavior).
    # Terminal slots: make ANSI black/white track the theme rather than literal colors.
    ansi_mapping = match.get_ansi_color_mapping(black=background, white=foreground_seed, candidates=candidates)

    # Contrast boost for mapped ANSI colors too (these are derived after candidate contrast).
    if contrast not in (None, "") and float(contrast) != 0:
        keys = [k for k in ("red", "green", "yellow", "blue", "magenta", "cyan") if k in ansi_mapping]
        mapped = [ansi_mapping[k] for k in keys]
        mapped = ensure_contrast(mapped, contrast, light, img)
        for k, c in zip(keys, mapped):
            ansi_mapping[k] = c
    logging.debug(f"ANSI color mapping:")
    # Print in standard ANSI color order: black, red, green, yellow, blue, magenta, cyan, white
    ansi_order = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
    ansi_values = [ansi_mapping[key] for key in ansi_order]
    palette_absolute(ansi_values)

    colors_dict = choose_8(background, foreground_seed, candidates, ansi_mapping)
    # colors_dict = colors_to_base_dict(colors)
    colors_dict.update(ansi_mapping)

    # ANSI "white" tuning: for dark themes, keep it white-ish; for light themes, we'll
    # override later with a dark foreground.
    if not light:
        colors_dict["white"] = adjust_to_fg_thresholds(colors_dict["white"], COLOR_7_MAX_SATURATION, COLOR_7_MIN_BRIGHTNESS)

    # 16 color shading
    shading = ARGS.shading
    logging.debug(f"Applying final 16-color shading with strategy {shading}:")
    shade_16(colors_dict, light, shading)
    logging.debug("After 16-color shading:")
    palette_absolute(colors_dict)

    if not light:
        colors_dict["bright_white"] = adjust_to_fg_thresholds(colors_dict["bright_white"], FG_MAX_SATURATION, FG_MIN_BRIGHTNESS)

    def _contrast_ratio(a: Color, b: Color) -> float:
        L1 = max(a.w3_luminance, b.w3_luminance)
        L2 = min(a.w3_luminance, b.w3_luminance)
        return (L1 + 0.05) / (L2 + 0.05)

    # Foreground: for dark themes, use a white-ish bright color.
    # For light themes, pick a dark text color; using bright_white makes text unreadable.
    if light:
        pool = [c for c in [foreground_seed, *candidates] if c is not None]
        pool = [c for c in pool if c.hex_color != background.hex_color] or pool
        fg = min(pool, key=lambda c: c.w3_luminance) if pool else foreground_seed
        for _ in range(12):
            if _contrast_ratio(background, fg) >= 4.5:
                break
            fg = fg.darken_amount(0.06)

        # In light schemes, terminal "white" and special.foreground should be the dark text.
        colors_dict["white"] = fg
        colors_dict["bright_white"] = fg.darken_amount(0.15)
        colors_dict["foreground"] = fg
    else:
        colors_dict["foreground"] = colors_dict["bright_white"]

    logging.debug(f"ANSI bright colors:")
    # Print in same order as base ANSI colors: black, red, green, yellow, blue, magenta, cyan, white
    bright_order = ["bright_black", "bright_red", "bright_green", "bright_yellow", 
                   "bright_blue", "bright_magenta", "bright_cyan", "bright_white"]
    bright_values = [colors_dict[key] for key in bright_order]
    palette_absolute(bright_values)


    colors = colors_to_dict(colors_dict, img)

    if not no_cache:
        util.save_file_json(colors, cache_file)
    logging.info("Generation complete.")

    return colors


def file(input_file):
    """Deprecated: symbolic link to --> theme.file"""
    return theme.file(input_file)
