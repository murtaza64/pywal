class Colors:
    """Easy access to all pywal colors."""
    
    # Special colors
    background = "{background}"
    foreground = "{foreground}"
    cursor = "{cursor}"
    
    # Indexed colors (color0-15)
    color0 = "{color0}"
    color1 = "{color1}"
    color2 = "{color2}"
    color3 = "{color3}"
    color4 = "{color4}"
    color5 = "{color5}"
    color6 = "{color6}"
    color7 = "{color7}"
    color8 = "{color8}"
    color9 = "{color9}"
    color10 = "{color10}"
    color11 = "{color11}"
    color12 = "{color12}"
    color13 = "{color13}"
    color14 = "{color14}"
    color15 = "{color15}"
    
    # ANSI semantic colors (when available)
    black = "{black}"
    red = "{red}"
    green = "{green}"
    yellow = "{yellow}"
    blue = "{blue}"
    magenta = "{magenta}"
    cyan = "{cyan}"
    white = "{white}"
    
    # ANSI bright colors (when available)
    bright_black = "{bright_black}"
    bright_red = "{bright_red}"
    bright_green = "{bright_green}"
    bright_yellow = "{bright_yellow}"
    bright_blue = "{bright_blue}"
    bright_magenta = "{bright_magenta}"
    bright_cyan = "{bright_cyan}"
    bright_white = "{bright_white}"
    
    # Surface colors 
    surface0 = "{surface0}"
    surface1 = "{surface1}"
    surface2 = "{surface2}"
    surface3 = "{surface3}"
    surface4 = "{surface4}"
    surface5 = "{surface5}"

    # Metadata
    checksum = "{checksum}"
    wallpaper = "{wallpaper}"
    alpha = "{alpha}"


# Create global instance for easy importing
colors = Colors()

# Example usage:
# from colors import colors
# print(f"Background: {{colors.background}}")
# print(f"Red color: {{colors.red}}")
# print(f"Error color: {{colors.color1}}")
