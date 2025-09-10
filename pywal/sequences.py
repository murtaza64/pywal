"""
Send sequences to all open terminals.
"""

import glob
import logging
import os
import subprocess

from .settings import OS
from .util import get_cache_dir, get_cache_file
from . import util


def set_special(index, color, iterm_name="h", alpha=100):
    """Convert a hex color to a special sequence."""
    if OS == "Darwin" and iterm_name:
        return "\033]P%s%s\033\\" % (iterm_name, color.strip("#"))

    if index in [11, 708] and alpha != "100":
        return "\033]%s;[%s]%s\033\\" % (index, alpha, color)

    return "\033]%s;%s\033\\" % (index, color)


def set_color(index, color):
    """Convert a hex color to a text color sequence."""
    # if OS == "Darwin" and index < 20:
    #     return "\033]P%1x%s\033\\" % (index, color.strip("#"))

    return "\033]4;%s;%s\033\\" % (index, color)


def set_iterm_tab_color(color):
    """Set iTerm2 tab/window color"""
    return (
        "\033]6;1;bg;red;brightness;%s\a"
        "\033]6;1;bg;green;brightness;%s\a"
        "\033]6;1;bg;blue;brightness;%s\a"
    ) % (*util.hex_to_rgb(color),)


def create_sequences(colors, vte_fix=False):
    """Create the escape sequences."""
    alpha = colors["alpha"]

    # Colors 0-15.
    # Use ANSI semantic colors if available, otherwise fall back to indexed colors
    if "ansi" in colors:
        print("Using ANSI semantic colors for terminal sequences:")
        # Map semantic colors to their ANSI positions
        ansi_colors = colors["ansi"]
        sequences = [
            set_color(0, ansi_colors["black"]),      # color0 - black
            set_color(1, ansi_colors["red"]),        # color1 - red  
            set_color(2, ansi_colors["green"]),      # color2 - green
            set_color(3, ansi_colors["yellow"]),     # color3 - yellow
            set_color(4, ansi_colors["blue"]),       # color4 - blue
            set_color(5, ansi_colors["magenta"]),    # color5 - magenta
            set_color(6, ansi_colors["cyan"]),       # color6 - cyan
            set_color(7, ansi_colors["white"]),      # color7 - white
        ]
        # For colors 8-15 (bright colors), use ANSI bright colors if available
        bright_names = ["bright_black", "bright_red", "bright_green", "bright_yellow", 
                       "bright_blue", "bright_magenta", "bright_cyan", "bright_white"]
        
        for index in range(8, 16):
            bright_name = bright_names[index - 8]
            if bright_name in ansi_colors:
                sequences.append(set_color(index, ansi_colors[bright_name]))
            else:
                sequences.append(set_color(index, colors["colors"]["color%s" % index]))
    else:
        print("Using indexed colors for terminal sequences:")
        sequences = [
            set_color(index, colors["colors"]["color%s" % index])
            for index in range(16)
        ]

    # Special colors.
    # Source: https://goo.gl/KcoQgP
    # 10 = foreground, 11 = background, 12 = cursor foreground
    # 13 = mouse foreground, 708 = background border color.
    sequences.extend(
        [
            set_special(10, colors["special"]["foreground"], "g"),
            set_special(11, colors["special"]["background"], "h", alpha),
            set_special(12, colors["special"]["cursor"], "l"),
            set_special(13, colors["special"]["foreground"], "j"),
            set_special(17, colors["special"]["foreground"], "k"),
            set_special(19, colors["special"]["background"], "m"),
            set_color(232, colors["special"]["background"]),
            set_color(256, colors["special"]["foreground"]),
            set_color(257, colors["special"]["background"]),
        ]
    )

    if not vte_fix:
        sequences.extend(
            set_special(708, colors["special"]["background"], "", alpha)
        )

    if OS == "Darwin":
        sequences += set_iterm_tab_color(colors["special"]["background"])

    return "".join(sequences)


def send(colors, cache_dir=None, to_send=True, vte_fix=False):
    """Send colors to all open terminals."""
    if cache_dir is None:
        cache_dir = get_cache_dir()
    if OS == "Darwin":
        devices = glob.glob("/dev/ttys00[0-9]*")
    elif OS == "OpenBSD":
        devices = subprocess.check_output(
            "ps -o tty | sed -e 1d -e s#^#/dev/# | sort | uniq",
            shell=True,
            universal_newlines=True,
        ).split()
    else:
        devices = glob.glob("/dev/pts/[0-9]*")

    sequences = create_sequences(colors, vte_fix)

    if not util.has_fcntl:
        logging.warning(util.fcntl_warning)

    # Send data to open terminal devices.
    if to_send:
        for dev in devices:
            if dev == "/dev/pts/0":
                if os.environ.get("DESKTOP_SESSION") == "plasma":
                    continue
            util.save_file(sequences, dev)

    util.save_file(sequences, get_cache_file("sequences"))
    logging.info("Set terminal colors.")
