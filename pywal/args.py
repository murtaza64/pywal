"""
Global arguments storage and argument parsing.
"""

import argparse
import json
import logging
import sys
import os
import shutil
import random

from .settings import __version__
from .print import palette, print_terminal_palette
from .util import get_cache_file
from pywal import util

# Global argparse.Namespace to store parsed arguments
ARGS = argparse.Namespace()

OPTIONS_TO_SAVE = [
    "alpha",
    "backend",
    "bg",
    "brightness",
    "choose",
    "contrast",
    "fg",
    "generation_strategy",
    "light",
    "saturate",
    "seed",
    "shading",
    "subtractive_initial",
]

def get_save_dict():
    return { option: getattr(ARGS, option) for option in OPTIONS_TO_SAVE }


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
        nargs="?",
        const=f"{os.path.expanduser('~')}/wallpapers",
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
        default="colorthief",
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
        "--saturate", metavar="(-100 .. 100)", help="Adjust palette saturation.", type=int
    )
    color_group.add_argument(
        "--brightness", metavar="(-100 .. 100)", help="Adjust minimum palette brightness. Try 40", type=int
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
        "--shading",
        default="lighten",
        choices=["darken", "lighten"],
        help="""Shading strategy to get 16 colors. 
'darken' uses the generated colors as bright colors and darkens them to get normal colors.
'lighten' uses the generated colors as normal colors and lightens them to get bright colors. Default: lighten""",
    )
    color_group.add_argument(
        "--choose",
        metavar="strategy",
        default="backend",
        choices=["random", "ansi", "brightness", "saturation", "ansi-brightness", "ansi-saturation", "ansi-shuffle", "backend"],
        help="How to choose 8 colors from the generated palette"
    )
    color_group.add_argument(
        "--seed",
        metavar="N",
        type=int,
        help="Set random seed for reproducible results.",
    )
    color_group.add_argument(
        "--subtractive-initial",
        "--si",
        metavar="N",
        type=int,
        default=16,
        help="When using the 'subtractive' strategy, start with a palette of N colors. Default: 16",
    )
    color_group.add_argument(
        "--generation-strategy",
        "--gen",
        metavar="strategy",
        required=False,
        default="subtractive",
        choices=["iterative", "subtractive"],
        help="Color generation strategy. 'iterative' filters greyish colors "
             "and retries with larger palettes. 'subtractive' gets brightest "
             "colors from a 16-color palette. Default: subtractive",
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
        "--modify",
        action="store_true",
        help="Modify the current colorscheme."
    )
    behavior_group.add_argument(
        "--shuffle",
        nargs="?",
        const="post",
        choices=["post", "all"],
        help="Randomize palette generation settings. By default (--shuffle post) only shuffles post-processing. --shuffle all to randomize palette too.",
    )
        
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

        settings = colors_plain.get("settings", {})

        print("Color settings:")
        for key, value in settings.items():
            print(f"{key}: {value}")

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

def get_cli_provided_args():
    """Get a set of argument names that were explicitly provided on the command line."""
    # Create a sentinel value to detect when defaults are used
    class _SENTINEL:
        pass
    
    sentinel = _SENTINEL()
    
    # Create a parser with all defaults set to sentinel
    temp_parser = get_parser()
    
    # Override all defaults with sentinel
    for action in temp_parser._actions:
        if hasattr(action, 'dest') and action.dest != 'help':
            action.default = sentinel
    
    # Parse with sentinel defaults
    temp_args = temp_parser.parse_args()
    
    # Find which arguments are NOT the sentinel (i.e., were provided)
    provided_args = set()
    for arg_name in vars(temp_args):
        if getattr(temp_args, arg_name) is not sentinel:
            provided_args.add(arg_name)
    logging.debug(f"CLI provided args: {provided_args}")
    
    return provided_args

def shuffle_settings():
    """Randomize palette generation settings."""
    # Choose strategy
    # use a Random instance to bypass global
    r = random.Random()
    
    ARGS.brightness = r.randint(-10, 60)
    ARGS.saturate = r.randint(-20, 40)

    shading_options = ["darken", "lighten"]
    ARGS.shading = r.choice(shading_options)
    
    shuffled_settings = {
        "brightness": ARGS.brightness, 
        "saturate": ARGS.saturate,
        "shading": ARGS.shading,
    }
    if ARGS.shuffle == "all":
        choose_options = ["random", "ansi", "brightness", "saturation", "ansi-brightness", "ansi-saturation", "ansi-shuffle", "backend"]
        ARGS.choose = r.choice(choose_options)
        
        ARGS.generation_strategy = r.choices(
            ["subtractive", "iterative"], 
            weights=[70, 30]
        )[0]
        ARGS.subtractive_initial = r.randint(16, 24)
        shuffled_settings.update({
            "choose": ARGS.choose,
            "generation_strategy": ARGS.generation_strategy,
            "subtractive_initial": ARGS.subtractive_initial
        })

    logging.info("Randomized palette generation settings:")
    for key, value in shuffled_settings.items():
        logging.info(f"{key}: {value}")

def load_modify_settings(cli_provided_args):
    """Load settings from colors.json and override with CLI-provided arguments."""
    try:
        with open(get_cache_file("colors.json")) as f:
            colors_data = json.load(f)
            wallpaper = colors_data["wallpaper"]
        
        loaded_settings = {} 

        if "image" not in cli_provided_args:
            loaded_settings["image"] = wallpaper
            ARGS.image = wallpaper
            ARGS.no_set_wallpaper = True

        # modify implies no-cache
        ARGS.no_cache = True

        saved_settings = colors_data.get("settings", {})
        previous_settings = {k: v for k, v in saved_settings.items() if v is not None}

        logging.info(f"Previous settings: {', '.join({f'{k}={v}' for k, v in previous_settings.items()})}")
        
        # Load saved settings, but only for args not provided on CLI
        for arg_name in OPTIONS_TO_SAVE:
            if arg_name in saved_settings:
                saved_value = saved_settings[arg_name]
                if saved_value is not None and arg_name not in cli_provided_args:
                    setattr(ARGS, arg_name, saved_value)

        new_settings = {k: getattr(ARGS, k) for k in OPTIONS_TO_SAVE if getattr(ARGS, k) is not None}
        changed_settings = {k: v for k, v in new_settings.items() if previous_settings.get(k) != v}

        if "seed" not in cli_provided_args and "choose" in cli_provided_args:
            if "random" in ARGS.choose:
                logging.info("Reseeding due to 'random' in choose strategy.")
                ARGS.seed = random.randint(0, sys.maxsize)
                changed_settings["seed"] = ARGS.seed

        if changed_settings:
            logging.debug(f"Settings overridden by CLI: {', '.join(changed_settings)}")
        else:
            logging.warning("No palette generation settings overridden by CLI.")

        
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logging.error(f"Could not load settings for modify mode: {e}")

def parse_args():
    
    parser.parse_args(namespace=ARGS)
    util.setup_logging(level=logging.DEBUG if ARGS.debug else logging.INFO)

    if len(sys.argv) <= 1:
        parser.print_help()
        sys.exit(1)


    if ARGS.version:
        parser.exit(0, "wal %s\n" % __version__)

    if ARGS.modify:
        cli_provided_args = get_cli_provided_args()
        # Load settings from colors.json and override with CLI-provided args
        load_modify_settings(cli_provided_args)

    if not ARGS.seed:
        ARGS.seed = random.randint(0, sys.maxsize)

    random.seed(ARGS.seed)
    logging.debug(f"Random seed set to: {ARGS.seed}")
    
    # Apply shuffling if requested (can be used with any mode)
    if ARGS.shuffle:
        shuffle_settings()

    if (
        not ARGS.image
        and not ARGS.theme
        and not ARGS.restore
        and not ARGS.wallpaper
        and not ARGS.modify
        and not ARGS.backend
    ):
        parser.error(
            "No input specified.\n" "--backend, --theme, -i, -R, or --modify are required."
        )
