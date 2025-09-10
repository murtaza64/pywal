"""
Print functions for displaying color palettes and colors.
"""

import logging

from . import util


def print_color(color, label=""):
    """Print a color with its visual representation in the terminal."""
    r, g, b = util.hex_to_rgb(color)
    if label:
        print(f"{label}: \033[48;2;{r};{g};{b}m  \033[0m {color}")
    else:
        print(f"\033[48;2;{r};{g};{b}m  \033[0m {color}")


def print_terminal_palette():
    """Generate a palette using terminal ANSI codes."""
    for i in range(0, 16):
        if i % 8 == 0:
            print()

        if i > 7:
            i = "8;5;%s" % i

        print("\033[4%sm%s\033[0m" % (i, " " * (80 // 20)), end="")

    print("\n")


def palette(color_dict: dict):
    """Generate a palette from the color dictionary."""
    colors = color_dict["colors"]
    # Print 2 rows of 8 numbered colors (color0-color15) using true color
    for row in range(2):
        for col in range(8):
            i = row * 8 + col
            color = colors[f"color{i}"]
            r, g, b = util.hex_to_rgb(color)
            print("\033[48;2;%d;%d;%dm    \033[0m" % (r, g, b), end="")
        print()
    
    print()
    # Print surface colors
    for key in [f"surface{i}" for i in range(6)]:
        if key in colors:
            color = colors[key]
            r, g, b = util.hex_to_rgb(color)
            print("\033[48;2;%d;%d;%dm    \033[0m" % (r, g, b), end="")
    print()
    print()
    # Print ANSI colors in two columns with titles
    ansi_names = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
    bright_names = ["bright_black", "bright_red", "bright_green", "bright_yellow", 
                   "bright_blue", "bright_magenta", "bright_cyan", "bright_white"]
        
    for i in range(8):
        # Normal color
        color = colors[ansi_names[i]]
        r, g, b = util.hex_to_rgb(color)
        print("\033[48;2;%d;%d;%dm    \033[0m \033[38;2;%d;%d;%dm%-8s\033[0m  " % (r, g, b, r, g, b, ansi_names[i]), end="")
        
        # Bright color
        bright_color = colors[bright_names[i]]
        br, bg, bb = util.hex_to_rgb(bright_color)
        print("\033[48;2;%d;%d;%dm    \033[0m \033[38;2;%d;%d;%dm%s\033[0m" % (br, bg, bb, br, bg, bb, bright_names[i]))
    print()


def palette_absolute(colors, level=logging.DEBUG):
    """Log a palette from absolute color values.
    
    Args:
        colors: List of hex color strings (e.g., ['#000000', '#ff0000', ...])
    """
    if isinstance(colors, dict):
        colors = list(colors.values())
    row = ""
    for i, color in enumerate(colors):
        if i % 8 == 0 and i > 0:
            logging.log(level, row)
            row = ""

        # Convert hex to RGB
        r, g, b = util.hex_to_rgb(color)
        
        # Use RGB escape codes for true color display
        row += "\033[48;2;%d;%d;%dm%s\033[0m" % (r, g, b, " " * 4)

    if row:
        logging.log(level, row)
