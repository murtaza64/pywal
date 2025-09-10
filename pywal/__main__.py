"""
                                      '||
... ...  .... ... ... ... ...  ....    ||
 ||'  ||  '|.  |   ||  ||  |  '' .||   ||
 ||    |   '|.|     ||| |||   .|' ||   ||
 ||...'     '|       |   |    '|..'|' .||.
 ||      .. |
''''      ''
Created by Dylan Araps.
"""

import json
import logging
import os
import sys

from .settings import __version__, CONF_DIR
from .args import ARGS, parse_args, process_args_exit
from .util import get_cache_dir, get_cache_file
from . import colors
from . import export
from . import image
from . import reload
from . import sequences
from . import theme
from . import util
from . import wallpaper
from .print import palette, print_palette_settings, display_palette_and_settings, print_wallpaper_name


show_colorama_warning = False
if sys.platform.startswith("win"):
    try:
        import colorama
        colorama.just_fix_windows_console()
    except ImportError:
        no_colorama_terms = [
                "wezterm",
                "alacritty",
                "hyper",
                "putty",
                "ghostty",
                "mintty",
                ]
        if os.environ.get("TERMINAL") not in no_colorama_terms and \
           os.environ.get("TERM_PROGRAM") not in no_colorama_terms:
            show_colorama_warning = True




def run():
    colors_plain = {}

    if ARGS.quiet:
        logging.getLogger().disabled = True
        sys.stdout = sys.stderr = open(os.devnull, "w")

    if ARGS.alpha:
        util.alpha_integrify(ARGS.alpha)
        util.Color.passed_alpha_num = ARGS.alpha
        util.Color.alpha_num = ARGS.alpha or util.Color.alpha_num

    if ARGS.image and not ARGS.theme:
        image_file = image.get(
            ARGS.image, iterative=ARGS.iterative, recursive=ARGS.recursive
        )
        colors_plain = colors.get(image_file)

    if ARGS.theme:
        colors_plain = theme.file(ARGS.theme, ARGS.light)
        if ARGS.image:
            colors_plain["wallpaper"] = ARGS.image

    if ARGS.restore:
        colors_plain = theme.file(get_cache_file("colors.json"))

    if ARGS.wallpaper:
        cached_wallpaper = util.read_file(get_cache_file("wal"))
        colors_plain = colors.get(cached_wallpaper[0])

    if not colors_plain:
        logging.error("No colors generated")
        sys.exit(1)

    if ARGS.bg:
        ARGS.bg = "#%s" % (ARGS.bg.strip("#"))
        colors_plain["special"]["background"] = ARGS.bg
        colors_plain["colors"]["color0"] = ARGS.bg

    if ARGS.fg:
        ARGS.fg = "#%s" % (ARGS.fg.strip("#"))
        colors_plain["special"]["foreground"] = ARGS.fg
        colors_plain["colors"]["color15"] = ARGS.fg

    if not ARGS.no_set_wallpaper:
        wallpaper.change(colors_plain["wallpaper"])

    if ARGS.save_theme:
        theme.save(colors_plain, ARGS.save_theme, ARGS.light)

    sequences.send(colors_plain, to_send=not ARGS.skip_sequences, vte_fix=ARGS.vte)

    json_file = get_cache_file("colors.json")
    with open(json_file, "w") as file:
        json.dump(colors_plain, file, indent=4)
    export.every(colors_plain)

    if not ARGS.skip_reload:
        reload.env(tty_reload=not ARGS.skip_tty)

    if sys.stdout.isatty():
        print()
        print_wallpaper_name(colors_plain.get("wallpaper"), colors_plain)
        display_palette_and_settings(colors_plain, ARGS)

    if ARGS.then:
        for cmd in ARGS.then:
            util.disown([cmd])

def main():
    """Main script function."""
    util.create_dir(os.path.join(CONF_DIR, "templates"))
    util.create_dir(os.path.join(CONF_DIR, "colorschemes/light/"))
    util.create_dir(os.path.join(CONF_DIR, "colorschemes/dark/"))

    parse_args()

    if show_colorama_warning:
        logging.warning("colorama is not present")
    
    process_args_exit()

    run()


if __name__ == "__main__":
    main()
