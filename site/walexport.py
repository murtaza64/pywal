"""Browser export engine: the fork's palette pipeline and exporters, run in Pyodide.

Writes only to the in-memory Emscripten filesystem. ImageMagick is unavailable in the browser, so the
image average (used by --contrast and --bg-strategy average) comes from Pillow instead.
"""

import io
import json
import os
import shutil
import zipfile

OUT = os.environ.setdefault("PYWAL_CACHE_DIR", "/tmp/walstudio/out")

from PIL import Image  # noqa: E402

from pywal import export, palette, util  # noqa: E402
from pywal.args import ARGS, OPTIONS_TO_SAVE, parser  # noqa: E402


def average_color(img):
    """Mean colour of the image, standing in for ImageMagick's `-resize 1x1!`."""
    with Image.open(img) as im:
        r, g, b = im.convert("RGB").resize((1, 1), Image.BOX).getpixel((0, 0))
    return f"#{r:02x}{g:02x}{b:02x}"


util.image_average_color = average_color


def generate(path, name, settings_json):
    """Palette + every export for the image at `path`; returns colors, {name: bytes}, a zip of them and the seed."""
    settings = json.loads(settings_json)
    for key, value in vars(parser.parse_args([])).items():
        setattr(ARGS, key, value)
    for key in OPTIONS_TO_SAVE:
        if key in settings:
            setattr(ARGS, key, None if settings[key] == "" else settings[key])
    if ARGS.seed not in (None, ""):
        # Seeds exceed JS number precision, so the page sends them as strings.
        ARGS.seed = int(str(ARGS.seed))
    ARGS.no_cache = True

    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    colors = palette.get(path, cache_dir=OUT)
    # The exported files name the wallpaper as the user knows it, not its in-memory path.
    colors["wallpaper"] = name
    with open(os.path.join(OUT, "colors.json"), "w") as f:
        json.dump(colors, f, indent=4)
    export.every(colors)

    files = {}
    for root, _, names in os.walk(OUT):
        for n in names:
            full = os.path.join(root, n)
            with open(full, "rb") as f:
                files[os.path.relpath(full, OUT)] = f.read()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in sorted(files):
            z.writestr(f"wal/{n}", files[n])
    return {"colors": colors, "files": files, "zip": buf.getvalue(), "seed": str(ARGS.seed)}
