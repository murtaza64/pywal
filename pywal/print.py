"""
Print functions for displaying color palettes and colors.
"""

import logging
import re

from . import util


def get_display_width(text):
    """Calculate the display width of text by removing ANSI escape sequences."""
    # Remove all ANSI escape sequences
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_text = ansi_escape.sub('', text)
    return len(clean_text)


def make_color_code(hex_color, bold=False):
    """Generate ANSI color code from hex color."""
    if not hex_color:
        return ""
    r, g, b = util.hex_to_rgb(hex_color)
    code = f"\033[38;2;{r};{g};{b}m"
    if bold:
        code += "\033[1m"
    return code


def print_wallpaper_name(wallpaper_path, color_dict=None):
    """Print the wallpaper name in bold color1."""
    import os
    
    # Extract filename from path
    wallpaper_name = os.path.basename(wallpaper_path) if wallpaper_path else "Unknown"
    
    # Get color1 for styling
    colors = color_dict.get("colors", {}) if color_dict else {}
    wallpaper_color = make_color_code(colors.get("color1"), bold=True)
    reset_color = "\033[0m"
    
    print(f"{wallpaper_color}{wallpaper_name}{reset_color}")
    print()


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
    lines = get_palette_lines(color_dict)
    for line in lines:
        print(line)

def get_palette_lines(color_dict: dict):
    """Return a list of strings representing the color palette."""
    lines = []
    colors = color_dict["colors"]
    
    # Add 2 rows of 8 numbered colors (color0-color15) using true color
    for row in range(2):
        line = ""
        for col in range(8):
            i = row * 8 + col
            color = colors[f"color{i}"]
            r, g, b = util.hex_to_rgb(color)
            line += "\033[48;2;%d;%d;%dm    \033[0m" % (r, g, b)
        lines.append(line)
    
    lines.append("")  # Empty line
    
    # Add surface colors
    surface_line = ""
    for key in [f"surface{i}" for i in range(6)]:
        if key in colors:
            color = colors[key]
            r, g, b = util.hex_to_rgb(color)
            surface_line += "\033[48;2;%d;%d;%dm    \033[0m" % (r, g, b)
    lines.append(surface_line)
    lines.append("")  # Empty line
    
    # Add ANSI colors in two columns with titles
    ansi_names = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
    bright_names = ["bright_black", "bright_red", "bright_green", "bright_yellow", 
                   "bright_blue", "bright_magenta", "bright_cyan", "bright_white"]
        
    for i in range(8):
        # Normal color
        color = colors[ansi_names[i]]
        r, g, b = util.hex_to_rgb(color)
        line = "\033[48;2;%d;%d;%dm    \033[0m \033[38;2;%d;%d;%dm%-8s\033[0m  " % (r, g, b, r, g, b, ansi_names[i])
        
        # Bright color
        bright_color = colors[bright_names[i]]
        br, bg, bb = util.hex_to_rgb(bright_color)
        line += "\033[48;2;%d;%d;%dm    \033[0m \033[38;2;%d;%d;%dm%s\033[0m" % (br, bg, bb, br, bg, bb, bright_names[i])
        lines.append(line)
    
    return lines


def display_palette_and_settings(color_dict: dict, args):
    """Display color palette and settings side by side."""
    palette_lines = get_palette_lines(color_dict)
    settings_lines = get_palette_settings_lines(args, color_dict)
    
    # Calculate the maximum display width of palette lines
    max_palette_width = max(get_display_width(line) for line in palette_lines if line)
    
    # Add padding between columns
    gap = "  "  # 2 spaces
    
    # Ensure both lists have the same length by padding with empty strings
    max_lines = max(len(palette_lines), len(settings_lines))
    
    while len(palette_lines) < max_lines:
        palette_lines.append("")
    while len(settings_lines) < max_lines:
        settings_lines.append("")
    
    # Print lines side by side
    for palette_line, settings_line in zip(palette_lines, settings_lines):
        # Calculate actual display width of this palette line
        palette_display_width = get_display_width(palette_line)
        
        # Pad palette line to consistent width
        padding = max(0, max_palette_width - palette_display_width)
        print(f"{palette_line}{' ' * padding}{gap}{settings_line}")


def palette_absolute(colors, level=logging.DEBUG):
    """Log a palette (list of hex colors) with absolute (rgb) color escape sequences
    
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


def print_palette_settings(args, color_dict=None):
    """Print a nicely formatted table of palette generation settings."""
    lines = get_palette_settings_lines(args, color_dict)
    for line in lines:
        print(line)

def get_palette_settings_lines(args, color_dict=None):
    """Return a list of strings representing the palette settings table."""
    from .args import OPTIONS_TO_SAVE
    
    lines = []
    
    # Get colors for styling
    reset_color = "\033[0m"
    
    # Extract colors from palette if available
    colors = color_dict.get("colors", {}) if color_dict else {}
    
    border_color = make_color_code(colors.get("color1"))
    header_color = make_color_code(colors.get("color2"), bold=True)
    row_color3 = make_color_code(colors.get("color3"))  # For seed
    row_color4 = make_color_code(colors.get("color4"))  # For backend - choose
    row_color5 = make_color_code(colors.get("color5"))  # For light - shading
    
    # Define display names for better formatting
    display_names = {
        "backend": "Backend",
        "generation_strategy": "Strategy", 
        "choose": "Choose",
        "subtractive_initial": "Subtractive Initial",
        "shading": "Shading",
        "brightness": "Brightness",
        "saturate": "Saturation",
        "contrast": "Contrast",
        "light": "Light Mode",
        "seed": "Seed",
        "bg": "Background",
        "fg": "Foreground",
        "alpha": "Alpha"
    }
    
    # Define the order of rows and their color groups
    row_order = [
        "seed",
        "backend", 
        "generation_strategy",
        # subtractive_initial handled specially in strategy row
        "choose",
        "light",
        "contrast",
        "saturate",
        "brightness",
        "shading"
    ]
    
    # Define color groups
    def get_row_color(option):
        if option == "seed":
            return row_color3
        elif option in ["backend", "generation_strategy", "subtractive_initial", "choose"]:
            return row_color4
        elif option in ["light", "saturate", "brightness", "shading", "contrast"]:
            return row_color5
        else:
            return ""  # Default color for other options
    
    # Get current settings in specified order
    settings = []
    for option in row_order:
        if option in OPTIONS_TO_SAVE:
            value = getattr(args, option, None)
            if value is not None:
                display_name = display_names.get(option, option.replace('_', ' ').title())
                
                # Special handling for generation_strategy
                if option == "generation_strategy":
                    if value == "subtractive":
                        # Include subtractive_initial if it exists
                        subtractive_initial = getattr(args, "subtractive_initial", None)
                        if subtractive_initial is not None:
                            value = f"subtractive ({subtractive_initial})"
                
                settings.append((display_name, str(value), option))
    
    # Add any remaining options not in the specified order
    displayed_options = set(row_order)
    displayed_options.add("subtractive_initial")  # Already handled in strategy row
    for option in OPTIONS_TO_SAVE:
        if option not in displayed_options:
            value = getattr(args, option, None)
            if value is not None:
                display_name = display_names.get(option, option.replace('_', ' ').title())
                settings.append((display_name, str(value), option))
    
    if not settings:
        lines.append("No palette settings configured.")
        return lines
    
    # Calculate column widths
    max_name_len = max(len(name) for name, _, _ in settings)
    max_value_len = max(len(value) for _, value, _ in settings)
    
    # Ensure minimum widths for readability
    name_width = max(max_name_len + 2, 20)
    value_width = max(max_value_len + 2, 15)
    
    # Add table header
    header_line = f"{border_color}┌{'─' * name_width}┬{'─' * value_width}┐{reset_color}"
    lines.append(header_line)
    
    lines.append(f"{border_color}│{reset_color} {header_color}{'Setting':<{name_width-2}}{reset_color} {border_color}│{reset_color} {header_color}{'Value':<{value_width-2}}{reset_color} {border_color}│{reset_color}")
    
    separator_line = f"{border_color}├{'─' * name_width}┼{'─' * value_width}┤{reset_color}"
    lines.append(separator_line)
    
    # Add settings rows
    for name, value, option in settings:
        original_value = value  # Keep original for length calculation
        row_color = get_row_color(option)
        
        # Highlight certain values with colors
        if name == "Strategy":
            if value.startswith("subtractive"):
                value = f"\033[32m{value}\033[0m"  # Green for subtractive
            elif value == "iterative":
                value = f"\033[33m{value}\033[0m"  # Yellow for iterative
        elif name in ["Brightness", "Saturation"] and value != "None":
            try:
                num_val = int(value)
                if num_val > 0:
                    original_value = f"+{value}"  # Update original_value to include the +
                    value = f"\033[32m+{value}\033[0m"  # Green for positive
                elif num_val < 0:
                    value = f"\033[31m{value}\033[0m"   # Red for negative
            except ValueError:
                pass
        elif name == "Light Mode":
            if value.lower() == "true":
                value = f"\033[32m{value}\033[0m"  # Green for true
            elif value.lower() == "false":
                value = f"\033[31m{value}\033[0m"  # Red for false
        
        # Apply row color to the setting name
        colored_name = f"{row_color}{name}{reset_color}" if row_color else name
        
        # Calculate padding for name and value columns
        name_padding = name_width - 2 - len(name)  # Use original name length for padding calculation
        value_padding = value_width - 2 - len(original_value)
        
        lines.append(f"{border_color}│{reset_color} {colored_name}{' ' * name_padding} {border_color}│{reset_color} {value}{' ' * value_padding} {border_color}│{reset_color}")
    
    # Add table footer
    footer_line = f"{border_color}└{'─' * name_width}┴{'─' * value_width}┘{reset_color}"
    lines.append(footer_line)
    
    return lines
