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

from .args import ARGS
from .util import get_cache_dir
from . import theme
from . import util
from . import match
from .print import palette_absolute
from .settings import MODULE_DIR, __cache_version__


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
    cols16 = ARGS.cols16 
    color_dict = {
        "settings": {
            "light": light,
            "cols16": cols16,
            "backend": ARGS.backend,
            "saturate": ARGS.saturate,
            "contrast": ARGS.contrast,
        },
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
    #         if cols16 == "lighten":
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


def shade_16(colors, light, cols16):
    """Generate 16-color palette from 8 base colors
    this function expects an 8-color dict input and expands it to 16 colors

    colors: dict (expected to have integer keys 0 through 7)
    light:  boolean - whether the colorscheme is light
    cols16: str [lighten|darken] - method to generate the shades"""

    dark_to_light_map = {k: v for k, v in {
        # omit 0 and 7 (bg and fg) for custom handling
        1: 9,
        2: 10,
        3: 11,
        4: 12,
        5: 13,
        6: 14,
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
        if light and cols16 == "lighten":
            colors[bright] = util.lighten_color(colors[orig], 0.25)
        elif light and cols16 == "darken":
            colors[bright] = util.darken_color(colors[orig], 0.25)
        elif not light and cols16 == "lighten":
            new = util.lighten_color(colors[orig], 0.25)
            new = util.saturate_color(new, 0.40)
            colors[bright] = new
        elif not light and cols16 == "darken":
            colors[bright] = colors[orig]
            colors[orig] = util.darken_color(colors[orig], 0.25)
        else:
            raise ValueError("Invalid cols16 strategy")

    # bg and fg
    if light:
        # Light theme: Generate colors 8-15 based on colors 0-7
        logging.debug("    Light theme - Generating bright colors 8-15:")
        colors[7] = util.darken_color(colors[0], 0.50, debug=True)
        colors[8] = util.darken_color(colors[0], 0.25, debug=True)
        colors[15] = util.darken_color(colors[0], 0.75)
    else:
        # Dark theme: Generate colors 8-15 based on colors 0-7
        logging.debug("    Dark theme - Generating bright colors 8-15:")
        colors[7] = util.lighten_color(colors[0], 0.55, debug=True)
        colors[7] = util.saturate_color(colors[7], 0.05, debug=True)
        color8 = util.lighten_color(colors[0], 0.35)
        color8 = util.saturate_color(color8, 0.10)
        colors[8] = color8
        colors[15] = util.lighten_color(colors[0], 0.75, debug=True)

    colors["white"] = colors[7]
    colors["bright_white"] = colors[15]
    colors["bright_black"] = colors[8]

def generic_adjust(colors, light):
    """Generic color adjustment for themers."""
    logging.debug("Before generic_adjust:")
    palette_absolute(colors)
    
    # Get c16 from global args
    cols16 = ARGS.cols16

    if light:
        logging.debug("Light theme adjustments:")
        
        logging.debug("  Saturating and darkening colors 1-7:")
        for i in range(1, min(8, len(colors))):
            colors[i] = util.saturate_color(colors[i], 0.60, debug=True)
            colors[i] = util.darken_color(colors[i], 0.5, debug=True)

        logging.debug("  Lightening background (color0):")
        colors[0] = util.lighten_color(colors[0], 0.95, debug=True)
        
        # 16-color shading will be applied later after all adjustments

    else:
        logging.debug("Dark theme adjustments:")
        
        if colors[0][1] != "0":  # the color may already be dark enough
            logging.debug("  Darkening background (color0):")
            colors[0] = util.darken_color(colors[0], 0.40, debug=True)  # just a bit darker

        saturate_more = False
        if colors[0][1] == "0":  # the color may not be saturated enough
            saturate_more = True
        if colors[0][3] == "0":  # the color may not be saturated enough
            saturate_more = True
        if colors[0][5] == "0":  # the color may not be saturated enough
            saturate_more = True

        if saturate_more:
            logging.debug("  Background needs more saturation:")
            colors[0] = util.lighten_color(colors[0], 0.03, debug=True)
            colors[0] = util.saturate_color(colors[0], 0.40, debug=True)

        # 16-color shading will be applied later after all adjustments

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
    colors_to_contrast = range(1, 7)

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
                    ]
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
                    ]
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
        [int(channel * 255) for channel in colorsys.hsv_to_rgb(hue, s, v)]
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

def get(img, cache_dir=None):
    """Generate a palette."""
    if cache_dir is None:
        cache_dir = get_cache_dir()
    # Get values from global args
    light = ARGS.light
    backend = ARGS.backend or "wal"
    sat = ARGS.saturate
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

    # Post-processing steps from command-line arguments
    colors = saturate_colors(colors, sat)

    if sat:
        logging.debug("After saturation adjustment:")
        palette_absolute(colors)
    colors = brighten_colors(colors, 0.4)
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

    colors_dict = colors_to_base_dict(colors)
    colors_dict.update(ansi_mapping)

    # 16 color shading
    cols16 = ARGS.cols16
    logging.debug(f"Applying final 16-color shading with strategy {cols16}:")
    shade_16(colors_dict, light, cols16)
    logging.debug("After 16-color shading:")
    palette_absolute(colors_dict[i] for i in range(16))

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
