"""
Misc helper functions.
"""

import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import hashlib
import copy

from .settings import XDG_CACHE_DIR
from .color import (
    Color,
    add_saturation,
    alpha_integrify,
    blend_color,
    brighten_color,
    darken_color,
    hex_to_rgb,
    hex_to_xrgba,
    lighten_color,
    print_color_change,
    rgb_to_hex,
    rgb_to_yiq,
    saturate_color,
)

# Custom log level (below DEBUG which is 10)
VERBOSE = 5


def get_cache_dir():
    """Get the cache directory from global args or environment."""
    # Import here to avoid circular imports
    from .args import ARGS
    
    if hasattr(ARGS, 'out_dir') and ARGS.out_dir:
        return ARGS.out_dir
    return os.getenv("PYWAL_CACHE_DIR", os.path.join(XDG_CACHE_DIR, "wal"))


def get_cache_file(*path: str) -> str:
    """Get a filename from the cache directory."""
    return os.path.join(get_cache_dir(), *path)

has_fcntl = False
fcntl_warning = ""

try:
    import fcntl

    has_fcntl = True
except ImportError:
    fcntl_warning = "{}, {}".format(
        "can't skip blocking io in current platform",
        "program could hang indefinitely",
    )


def read_file(input_file):
    """Read data from a file and trim newlines."""
    with open(input_file, "r") as file:
        return file.read().splitlines()


def read_file_json(input_file):
    """Read data from a json file."""
    with open(input_file, "r") as json_file:
        return json.load(json_file)


def read_file_raw(input_file):
    """Read data from a file as is, don't strip
    newlines or other special characters."""
    with open(input_file, "r") as file:
        return file.readlines()


def save_file(data, export_file):
    """Write data to a file."""
    create_dir(os.path.dirname(export_file))

    if has_fcntl:
        try:
            with open(export_file, "w") as file:
                # Get the current flags and add non-blocking mode
                # to skip TTYs suspended by Flow Control
                # https://www.gnu.org/software/libc/manual/html_node/Getting-File-Status-Flags.html
                # https://www.gnu.org/software/libc/manual/html_node/Open_002dtime-Flags.html
                flags = fcntl.fcntl(file, fcntl.F_GETFL)
                fcntl.fcntl(file, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                file.write(data)
        except PermissionError:
            logging.warning("Couldn't write to %s.", export_file)
        except BlockingIOError:
            logging.warning(
                "Couldn't write to %s, not accepting data", export_file
            )
    else:
        try:
            with open(export_file, "w") as file:
                file.write(data)
        except PermissionError:
            logging.warning("Couldn't write to %s.", export_file)


def save_file_json(data, export_file):
    """Write data to a json file."""
    create_dir(os.path.dirname(export_file))

    with open(export_file, "w") as file:
        json.dump(data, file, indent=4)


def get_img_checksum(img):
    checksum = hashlib.new("md5", usedforsecurity=False)
    with open(img, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def create_dir(directory):
    """Alias to create the cache dir."""
    os.makedirs(directory, exist_ok=True)


def setup_logging(level=logging.INFO):
    """Logging config."""
    # Add VERBOSE log level between INFO and DEBUG
    logging.addLevelName(VERBOSE, "VERBOSE")
    
    def verbose(self, message, *args, **kwargs):
        if self.isEnabledFor(VERBOSE):
            self._log(VERBOSE, message, args, **kwargs)
    
    logging.Logger.verbose = verbose
    
    logging.basicConfig(
        format=(
            "[%(levelname)s\033[0m] "
            "\033[1;31m%(module)s\033[0m: "
            "%(message)s"
        ),
        level=level,
        stream=sys.stderr,
    )
    logging.addLevelName(logging.ERROR, "\033[1;31mE")
    logging.addLevelName(logging.INFO, "\033[1;32mI")
    logging.addLevelName(logging.WARNING, "\033[1;33mW")
    logging.addLevelName(logging.DEBUG, "\033[1;34mD")
    logging.addLevelName(VERBOSE, "\033[1;35mV")  # Magenta for verbose


def disown(cmd):
    """Call a system command in the background,
    disown it and hide it's output."""
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def get_pid(name):
    """Check if process is running by name."""
    if not shutil.which("pidof"):
        return False

    try:
        if platform.system() != "Darwin":
            subprocess.check_output(["pidof", "-s", name])
        else:
            subprocess.check_output(["pidof", name])

    except subprocess.CalledProcessError:
        return False

    return True


def has_im():
    """Check to see if the user has im installed."""
    if shutil.which("magick"):
        return "magick"

    if shutil.which("convert"):
        return "convert"

    logging.error("Problem running image averaging command.")
    logging.error("Imagemagick wasn't found on your system.")
    sys.exit(1)


def image_average_color(img):
    """Mean sRGB colour of the image, as #rrggbb.

    Pillow on every platform, so the desktop and the browser agree (ImageMagick's `-resize 1x1!`
    is a filtered sample, not the mean).
    """
    from PIL import Image

    from .decoded import open_image

    with open_image(img) as im:
        r, g, b = im.convert("RGB").resize((1, 1), Image.BOX).getpixel((0, 0))
    return f"#{r:02x}{g:02x}{b:02x}"
