"""
Global arguments storage and argument parsing.
"""

import argparse
import json
import sys
import os
import shutil

from .settings import __version__
from .print import palette, print_terminal_palette
from .util import get_cache_file

# Global argparse.Namespace to store parsed arguments
ARGS = argparse.Namespace()




def get_parser():
    """Get the script arguments."""
    description = "wal - Generate colorschemes on the fly"
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # === INPUT SOURCES ===
    input_group = parser.add_argument_group('Input Sources')
    input_group.add_argument(
        "--image",
        "-i",
        metavar='"/path/to/img.jpg" | "/path/to/dir"',
        help="Which image or directory to use.",
    )
    input_group.add_argument(
        "--theme",
        "-f",
        metavar="/path/to/file or theme_name",
        help="Which colorscheme file to use. \
                           Use 'wal --theme' to list builtin and user themes.",
        const="list_themes",
        nargs="?",
    )
    input_group.add_argument(
        "--restore",
        "-R",
        action="store_true",
        help="Restore previous colorscheme.",
    )
    input_group.add_argument(
        "--wallpaper",
        "-w",
        action="store_true",
        help="Use last used wallpaper for color generation.",
    )
    input_group.add_argument(
        "--iterative",
        action="store_true",
        help="When pywal is given a directory as input and this "
        "flag is used: Go through the images in order "
        "instead of shuffled.",
    )
    input_group.add_argument(
        "--recursive",
        action="store_true",
        help="When pywal is given a directory as input and this "
        "flag is used: Search for images recursively in "
        "subdirectories instead of the root only.",
    )
    
    # === COLOR GENERATION ===
    color_group = parser.add_argument_group('Color Generation')
    color_group.add_argument(
        "--backend",
        metavar="backend",
        help="Which color backend to use. \
                           Use 'wal --list-backends' to list backends.",
        type=str,
        default="wal",
    )
    color_group.add_argument(
        "--list-backends",
        action="store_true",
        help="List available color backends.",
    )
    color_group.add_argument(
        "--light", "-l", action="store_true", help="Generate a light colorscheme."
    )
    color_group.add_argument(
        "--saturate", metavar="(-1.0 .. 1.0)", help="Set the color saturation."
    )
    color_group.add_argument(
        "--contrast",
        metavar="(1.0 .. 21.0)",
        required=False,
        type=float,
        help="Specify a minimum contrast ratio between palette "
        "colors and the source image according to W3 "
        "contrast specifications. Values between 1.5-4.5 "
        "typically work best.",
    )
    color_group.add_argument(
        "--cols16",
        metavar="method",
        required=False,
        nargs="?",
        default="lighten",
        const="darken",
        choices=["darken", "lighten"],
        help="Use 16 color output " '"darken" or "lighten" default: lighten',
    )
    
    # === COLOR CUSTOMIZATION ===
    custom_group = parser.add_argument_group('Color Customization')
    custom_group.add_argument(
        "--bg",
        "--background",
        "-b",
        metavar="background",
        help="Custom background color to use.",
    )
    custom_group.add_argument(
        "--fg", "--foreground", metavar="foreground", help="Custom foreground color to use."
    )
    custom_group.add_argument(
        "--alpha",
        "-a",
        metavar='"alpha"',
        help="Set terminal background transparency. \
              Must be a number between 0 and 100. \
              *Only works in terminals that implement OSC-11 (URxvt)*",
    )
    
    # === DISPLAY & OUTPUT ===
    display_group = parser.add_argument_group('Display & Output')
    display_group.add_argument(
        "--show",
        "-S",
        action="store_true",
        help="Show the current colorscheme.",
    )
    display_group.add_argument(
        "--print-term-colors",
        action="store_true",
        help="Print the current 16 terminal colors.",
    )
    display_group.add_argument(
        "--out-dir",
        metavar="out_dir",
        help="Cache dir to export themes. \
              Default is 'XDG_CACHE_HOME/wal'. \
              This can also be set with the env var: 'PYWAL_CACHE_DIR'",
        type=str,
        nargs="?",
    )
    display_group.add_argument(
        "--save-theme",
        "-p",
        metavar='"theme_name"',
        help="permanently save theme to "
        "$XDG_CONFIG_HOME/wal/colorschemes with "
        "the specified name",
    )
    
    # === BEHAVIOR CONTROL ===
    behavior_group = parser.add_argument_group('Behavior Control')
    behavior_group.add_argument(
        "--no-set-wallpaper",
        "-n",
        action="store_true",
        help="Skip setting the wallpaper.",
    )
    behavior_group.add_argument(
        "--skip-sequences",
        "-s",
        action="store_true",
        help="Skip changing colors in terminals.",
    )
    behavior_group.add_argument(
        "--skip-reload",
        "-e",
        action="store_true",
        help="Skip reloading gtk/xrdb/i3/sway/polybar",
    )
    behavior_group.add_argument(
        "--skip-tty",
        "-t",
        action="store_true",
        help="Skip changing colors in tty.",
    )
    behavior_group.add_argument(
        "--then",
        "-o",
        metavar='"script_name"',
        action="append",
        help='External script to run after "wal".',
    )
    behavior_group.add_argument(
        "--vte",
        action="store_true",
        help="Fix text-artifacts printed in VTE terminals.",
    )
    
    # === UTILITIES ===
    util_group = parser.add_argument_group('Utilities')
    util_group.add_argument(
        "--clear-cache",
        "-c",
        action="store_true",
        help="Delete all cached colorschemes.",
    )
    util_group.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip looking for cached colorschemes and always regenerate.",
    )
    util_group.add_argument(
        "--reload", "-r",
        action="store_true",
        help="Reload colors in open applications and exit",
    )
    util_group.add_argument(
        "--debug", action="store_true", help="Show debug information."
    )
    util_group.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Quiet mode, don't print anything.",
    )
    util_group.add_argument(
        "--version",
        "-v",
        action="store_true",
        help='Print "wal" version.',
    )

    return parser

parser = get_parser()

def process_args_exit():
    """Process args that exit."""
    if ARGS.print_term_colors:
        print_terminal_palette()
        sys.exit(0)

    if ARGS.show:
        from .util import get_cache_dir
        wallpaper = open(os.path.join(get_cache_dir(), "wal")).read().strip()
        print("Wallpaper:", wallpaper)
        print()

        with open(get_cache_file("colors.json")) as f:
            colors_plain = json.load(f)
        palette(colors_plain)

        sys.exit(0)

    if ARGS.reload:
        from . import reload
        reload.colors()
        sys.exit(0)

    if ARGS.clear_cache:
        from .util import get_cache_dir
        scheme_dir = get_cache_file("schemes")
        shutil.rmtree(scheme_dir, ignore_errors=True)
        sys.exit(0)


    if ARGS.theme == "list_themes":
        from . import theme
        theme.list_out()
        sys.exit(0)

    if ARGS.list_backends:
        from . import colors
        print(
            "\n - ".join(
                ["\033[1;32mBackends\033[0m:", *colors.list_backends()]
            )
        )
        sys.exit(0)

def parse_args():
    parser.parse_args(namespace=ARGS)

    if len(sys.argv) <= 1:
        parser.print_help()
        sys.exit(1)

    if ARGS.version:
        parser.exit(0, "wal %s\n" % __version__)

    if (
        not ARGS.image
        and not ARGS.theme
        and not ARGS.restore
        and not ARGS.wallpaper
        and not ARGS.backend
    ):
        parser.error(
            "No input specified.\n" "--backend, --theme, -i or -R are required."
        )
