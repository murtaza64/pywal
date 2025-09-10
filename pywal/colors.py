"""
Generate a palette using various backends.
"""

import colorsys
import logging
import os
import random
import re
import sys
import colorsys

from pywal.types import HexColor

from .args import ARGS, get_save_dict
from .util import get_cache_dir
from . import theme
from . import util
from . import match
from .print import palette_absolute
from .settings import MODULE_DIR, __cache_version__

# Foreground color thresholds for white-ish appearance
COLOR_7_MAX_SATURATION = 0.2
COLOR_7_MIN_BRIGHTNESS = 0.7
FG_MAX_SATURATION = 0.12
FG_MIN_BRIGHTNESS = 0.8


def list_backends():
    """List color backends."""
    return [
        b.name.replace(".py", "")
        for b in os.scandir(os.path.join(MODULE_DIR, "backends"))
        if "__" not in b.name
    ]


def normalize_img_path(img: str):
    """Normalizes the image path for output."""
    if os.name == "nt":
        # On Windows, the JSON.dump ends up outputting un-escaped backslash
        # breaking the ability to read colors.json. Windows supports forward
        # slash, so we can use that for now
        return img.replace("\\", "/")
    return img


def colors_to_dict(colors: dict, img):
    """Convert list of colors to pywal format."""
    logging.debug("Converting colors to dictionary")

    light = ARGS.light
    shading = ARGS.shading 
    color_dict = {
        "settings": get_save_dict(),
        "checksum": util.get_img_checksum(img),
        "wallpaper": normalize_img_path(img),
        "alpha": util.Color.alpha_num,
        "special": {
            "background": colors[0],
            "foreground": colors[15],
            "cursor": colors[15],
        },
    }
    # Convert integer colors to color0, color1, ...
    colors = {k if isinstance(k, str) else f"color{k}": v for k, v in colors.items()}
    color_dict["colors"] = colors

    # Generate gradually lightened background shades
    surface_colors = {}
    for i in range(6):
        shade_amount = (i + 1) * (0.75 / 7)  # Evenly spaced from 0 to 0.75 exclusive: ~0.107, 0.214, 0.321, 0.429, 0.536, 0.643
        surface_colors[f"surface{i}"] = util.lighten_color(colors["color0"], shade_amount)
    
    colors.update(surface_colors)

    # Print surface colors
    logging.debug("Surface colors:")
    surface_values = [colors[f"surface{i}"] for i in range(6)]
    palette_absolute(surface_values)
    
    
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
    

    return color_dict


def colors_to_base_dict(colors_list) -> dict[str | int, str]:
    """Convert 8-color list to integer-indexed dict format for shade_16."""
    return {i: colors_list[i] for i in range(min(8, len(colors_list)))}


def adjust_to_fg_thresholds(color, sat_threshold, brightness_threshold):
    """Adjust a color to meet foreground thresholds (low saturation, high brightness)."""
    r, g, b = util.hex_to_rgb(color)
    h, s, v = match.rgb_to_hsv(r/255.0, g/255.0, b/255.0)
    
    logging.debug(f"Adjusting fg color {color} (s={s:.2f}, v={v:.2f}) to meet thresholds")
    
    adjusted_color = color
    
    # Reduce saturation if too high (desaturate to make more white-ish)
    if s > sat_threshold:
        # Calculate how much to desaturate: current saturation - target
        desaturate_amount = -(s - sat_threshold)  # negative value for desaturation
        adjusted_color = util.add_saturation(adjusted_color, desaturate_amount, debug=True)
    
    # # Increase brightness if too low
    # if v < brightness_threshold:
    #     # Calculate target brightness increase
    #     target_brightness = brightness_threshold
    #     adjusted_color = util.brighten_color(adjusted_color, target_brightness, debug=True)
    adjusted_color = util.brighten_color(adjusted_color, brightness_threshold, debug=True)
    
    return adjusted_color


def shade_16(colors, light, shading):
    """Generate 16-color palette from 8 base colors
    this function expects an 8-color dict input and expands it to 16 colors

    colors: dict (expected to have integer keys 0 through 7)
    light:  boolean - whether the colorscheme is light
    shading: str [lighten|darken] - method to generate the shades"""

    dark_to_light_map = {k: v for k, v in {
        # omit 0 and 7 (bg and fg) for custom handling
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
        # "white": "bright_white",
    }.items() if k in colors}

    # middle colors
    for orig, bright in dark_to_light_map.items():
        if light and shading == "lighten":
            colors[bright] = util.lighten_color(colors[orig], 0.25)
        elif light and shading == "darken":
            colors[bright] = util.darken_color(colors[orig], 0.25)
        elif not light and shading == "lighten":
            new = util.lighten_color(colors[orig], 0.25)
            new = util.saturate_color(new, 0.40)
            colors[bright] = new
        elif not light and shading == "darken":
            colors[bright] = colors[orig]
            colors[orig] = util.darken_color(colors[orig], 0.25)
        else:
            raise ValueError("Invalid shading strategy")

    # bg and fg
    if light:
        # Light theme: Generate colors 8-15 based on colors 0-7
        logging.debug("    Light theme - Generating bright colors 8-15:")
        colors[8] = util.darken_color(colors[0], 0.25, debug=True)
        # colors[15] = util.darken_color(colors[0], 0.75)
    else:
        # Dark theme: Generate colors 8-15 based on colors 0-7
        logging.debug("    Dark theme - Generating bright colors 8-15:")
        # colors[15] = util.lighten_color(colors[0], 0.75, debug=True)

        # bright bg
        color8 = util.lighten_color(colors[0], 0.35)
        color8 = util.saturate_color(color8, 0.10)
        colors[8] = color8

    colors["white"] = colors[7]
    colors["bright_white"] = colors[15]
    colors["bright_black"] = colors[8]

def adjust_background(color, light):
    if light:
        logging.debug("Lightening background color:")
        color = util.lighten_color(color, 0.95, debug=True)

    else:
        if color[1] != "0":  # the color may already be dark enough
            logging.debug("Darkening background color:")
            color = util.darken_color(color, 0.40, debug=True)  # just a bit darker

        saturate_more = False
        if color[1] == "0":  # the color may not be saturated enough
            saturate_more = True
        if color[3] == "0":  # the color may not be saturated enough
            saturate_more = True
        if color[5] == "0":  # the color may not be saturated enough
            saturate_more = True

        if saturate_more:
            logging.debug("Background needs more saturation:")
            color = util.lighten_color(color, 0.03, debug=True)
            color = util.saturate_color(color, 0.40, debug=True)
    return color

def generic_adjust(colors, light):
    """Generic color adjustment for themers."""
    if light:
        logging.debug("Light theme: Saturating and darkening all colors except 0:")
        for i in range(1, len(colors)):
            colors[i] = util.saturate_color(colors[i], 0.60, debug=True)
            colors[i] = util.darken_color(colors[i], 0.5, debug=True)

    # Adjust foreground color to meet white-ish thresholds
    # colors[7] = adjust_to_fg_thresholds(colors[7], COLOR_7_MAX_SATURATION, COLOR_7_MIN_BRIGHTNESS)

    logging.debug("After generic_adjust:")
    palette_absolute(colors)
    return colors

def saturate_colors(colors, amount):
    """Saturate all colors."""
    if amount and (float(amount) <= 1.0 and float(amount) >= -1.0):
        logging.debug(f"Saturating colors (amount: {amount}):")
        for i, _ in enumerate(colors):
            if i not in [7, 15]:
                colors[i] = util.add_saturation(colors[i], float(amount), debug=True)

    return colors

def brighten_colors(colors, min_brightness):
    """Brighten all colors."""
    logging.debug(f"Brightening colors (min_brightness: {min_brightness}):")
    for i, _ in enumerate(colors):
        if i not in [0, 7, 8, 15]:
            colors[i] = util.brighten_color(colors[i], min_brightness, debug=True)

    return colors


def ensure_contrast(colors, contrast, light, image):
    """Ensure user-specified W3 contrast of colors
    depending on dark or light theme."""
    # If no contrast checking was specified, do nothing
    if not contrast or contrast == "":
        return colors

    # Contrast must be within a predefined range
    if float(contrast) < 1 or float(contrast) > 21:
        logging.error("Specified contrast ratio is too extreme")
        return colors

    # Get the image background color
    background_color = util.Color(util.image_average_color(image))
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
        return colors

    if luminance_desired >= 0.99:
        logging.debug("Can't contrast this palette without changing colors to white")
        return colors
    if luminance_desired <= 0.01:
        logging.debug("Can't contrast this palette without changing colors to black")
        return colors

    # Determine which colors should be modified / checked
    # ! For the time being this is just going to modify all the colors except
    # 0 and 15
    colors_to_contrast = range(1, len(colors) - 1)

    # Modify colors
    for index in colors_to_contrast:
        color = util.Color(colors[index])

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
            and util.Color(
                util.rgb_to_hex(
                    [
                        int(channel * 255)
                        for channel in colorsys.hsv_to_rgb(h, s, 1)
                    ]  # type: ignore
                )
            ).w3_luminance
            >= luminance_desired
        ):
            colors[index] = binary_luminance_adjust(
                luminance_desired, h, s, s, v, 1
            )
        # If the color is to be lighter than background and increasing value
        # to 1 doesn't produce the desired luminance, additionally decrease
        # saturation
        elif not light:
            colors[index] = binary_luminance_adjust(
                luminance_desired, h, 0, s, 1, 1
            )
        # If the color is to be darker than background, produce desired
        # luminance by decreasing value, and raising saturation
        else:
            colors[index] = binary_luminance_adjust(
                luminance_desired, h, s, 1, 0, v
            )

    return colors


def binary_luminance_adjust(
    luminance_desired, hue, s_min, s_max, v_min, v_max, iterations=10
):
    """Use a binary method to adjust a color's value and/or
    saturation to produce the desired luminance"""
    for i in range(iterations):
        # Obtain a new color by averaging saturation and value
        s = (s_min + s_max) / 2
        v = (v_min + v_max) / 2

        # Compare the luminance of this color to the target luminance
        # If the color is too light, clamp the minimum saturation
        # and maximum value
        if (
            util.Color(
                util.rgb_to_hex(
                    [
                        int(channel * 255)
                        for channel in colorsys.hsv_to_rgb(hue, s, v)
                    ]  # type: ignore
                )
            ).w3_luminance
            >= luminance_desired
        ):
            s_min = s
            v_max = v
        # If the color is too dark, clamp the maximum saturation
        # and minimum value
        else:
            s_max = s
            v_min = v

    return util.rgb_to_hex(
        [int(channel * 255) for channel in colorsys.hsv_to_rgb(hue, s, v)]  # type: ignore
    )

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

def get_backend(backend):
    """Figure out which backend to use."""
    if backend == "random":
        backends = list_backends()
        random.shuffle(backends)
        return backends[0]

    return backend

def get_brightness(color: HexColor) -> float:
    """Calculate brightness of a hex color (0.0 to 1.0)."""
    r, g, b = util.hex_to_rgb(color)
    h, s, v = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)
    return v

def get_saturation(color: HexColor) -> float:
    r, g, b = util.hex_to_rgb(color)
    h, s, v = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)
    return s

def choose_8(colors, ansi_mapping):
    # first (darkest), last (brightest) and 6 middle colors
    # choose either the same colors as the ansi colors
    # or the 6 most saturated colors
    # or the 6 most bright colors
    # or 6 random colors
    # for now, return 6 random colors
    bg = colors[0]
    fg = colors[-1]
    middle_colors = colors[1:-1]

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


    selected = [bg] + middle_colors[:6] + [fg]
    logging.debug("Selected 8 colors:")
    palette_absolute(selected)
    return selected

def get(img, cache_dir=None):
    """Generate a palette."""
    if cache_dir is None:
        cache_dir = get_cache_dir()
    # Get values from global args
    light = ARGS.light
    backend = ARGS.backend or "wal"
    saturation_to_add = ARGS.saturate / 100 if ARGS.saturate else 0
    min_brightness = ARGS.brightness / 100 if ARGS.brightness else 0
    no_cache = ARGS.no_cache
    contrast = ARGS.contrast

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
    backend = get_backend(backend)

    __import__("pywal.backends.%s" % backend)

    logging.info("Using %s backend.", backend)
    backend = sys.modules["pywal.backends.%s" % backend]
    colors = getattr(backend, "get")(img, light)
    
    logging.debug("Backend generated colors:")
    palette_absolute(colors)

    if saturation_to_add:
        # Post-processing steps from command-line arguments
        colors = saturate_colors(colors, saturation_to_add)
        logging.debug("After saturation adjustment:")
        palette_absolute(colors)

    if min_brightness:
        colors = brighten_colors(colors, min_brightness)
        logging.debug("After brightness adjustment:")
        palette_absolute(colors)

    if contrast:
        colors = ensure_contrast(colors, contrast, light, img)
        logging.debug("After contrast adjustment:")
        palette_absolute(colors)


    # Generate ANSI color mapping (now default behavior)
    ansi_mapping = match.get_ansi_color_mapping(colors)
    logging.debug(f"ANSI color mapping:")
    # Print in standard ANSI color order: black, red, green, yellow, blue, magenta, cyan, white
    ansi_order = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
    ansi_values = [ansi_mapping[key] for key in ansi_order]
    palette_absolute(ansi_values)

    colors = choose_8(colors, ansi_mapping)
    colors_dict = colors_to_base_dict(colors)
    colors_dict.update(ansi_mapping)

    colors_dict[7] = adjust_to_fg_thresholds(colors_dict[7], COLOR_7_MAX_SATURATION, COLOR_7_MIN_BRIGHTNESS)

    # 16 color shading
    shading = ARGS.shading
    logging.debug(f"Applying final 16-color shading with strategy {shading}:")
    shade_16(colors_dict, light, shading)
    logging.debug("After 16-color shading:")
    palette_absolute(colors_dict[i] for i in range(16))

    colors_dict[15] = adjust_to_fg_thresholds(colors_dict[15], FG_MAX_SATURATION, FG_MIN_BRIGHTNESS)

    logging.debug(f"ANSI bright colors:")
    # Print in same order as base ANSI colors: black, red, green, yellow, blue, magenta, cyan, white
    bright_order = ["bright_black", "bright_red", "bright_green", "bright_yellow", 
                   "bright_blue", "bright_magenta", "bright_cyan", "bright_white"]
    bright_values = [colors_dict[key] for key in bright_order]
    palette_absolute(bright_values)


    colors = colors_to_dict(colors_dict, img)
    util.save_file_json(colors, cache_file)
    logging.info("Generation complete.")

    return colors


def file(input_file):
    """Deprecated: symbolic link to --> theme.file"""
    return theme.file(input_file)
