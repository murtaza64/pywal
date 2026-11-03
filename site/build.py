"""Build the browser studio (static site) into site/dist.

The page is Palette Studio's own (pywal/studio/static) with boot.js in place of the server: a service
worker routes /api to pywal.studio.web running in Pyodide. engine.zip carries the pywal package
(without the studio's static files) and the pure-Python colorthief port (BSD, Shipeng Feng; header
kept) that Pyodide uses in place of the modern_colorthief Rust wheel. Sample wallpapers are generated
here, so the site ships no third-party images.
Run: uv run python site/build.py
"""

import colorsys
import random
import shutil
import zipfile
from pathlib import Path

import colorthief
from PIL import Image, ImageDraw, ImageFilter

SITE = Path(__file__).parent
ROOT = SITE.parent
STATIC = ROOT / "pywal" / "studio" / "static"
DIST = SITE / "dist"
SKIP = {"static", "__pycache__"}
# name, base hue
SAMPLES = [("dusk.jpg", 0.72), ("ember.jpg", 0.03), ("moss.jpg", 0.33), ("tide.jpg", 0.55)]


def main():
    shutil.rmtree(DIST, ignore_errors=True)
    (DIST / "web").mkdir(parents=True)
    shutil.copytree(STATIC, DIST / "static")
    page = (STATIC / "index.html").read_text()
    script = '<script src="/static/studio.js" type="module"></script>'
    assert script in page, "studio index.html no longer loads studio.js the expected way"
    page = page.replace(script, '<script src="/web/boot.js" type="module"></script>')
    page = page.replace("<title>Palette Studio</title>", "<title>WalStudio · palette studio in your browser</title>")
    page = page.replace('<link rel="icon" href="data:,">', '<link rel="icon" href="/icon.png">')
    (DIST / "index.html").write_text(page)
    shutil.copy(SITE / "boot.js", DIST / "web" / "boot.js")
    shutil.copy(SITE / "worker.js", DIST / "web" / "worker.js")
    shutil.copy(SITE / "sw.js", DIST / "sw.js")
    shutil.copy(ROOT / "desktop/walstudio/icon/walstudio-1024.png", DIST / "icon.png")
    (DIST / "samples").mkdir()
    for name, hue in SAMPLES:
        sample(hue).save(DIST / "samples" / name, quality=88)
    with zipfile.ZipFile(DIST / "web" / "engine.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted((ROOT / "pywal").rglob("*")):
            rel = path.relative_to(ROOT)
            if path.is_file() and not SKIP & set(rel.parts) and path.suffix != ".pyc":
                z.write(path, rel)
        z.write(colorthief.__file__, "colorthief.py")
    print(DIST, sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) // 1024, "KiB")


def sample(hue):
    """A soft colour-field wallpaper (1920x1080): a dark ground, a few blurred fields around `hue`."""
    rnd = random.Random(int(hue * 1000))
    w, h = 1920, 1080
    rgb = lambda hh, s, v: tuple(int(255 * c) for c in colorsys.hsv_to_rgb(hh % 1, s, v))
    img = Image.new("RGB", (w, h), rgb(hue, 0.6, 0.12))
    d = ImageDraw.Draw(img)
    for i in range(7):
        x, y, r = rnd.uniform(0, w), rnd.uniform(0, h), rnd.uniform(160, 520)
        d.ellipse([x - r, y - r, x + r, y + r], fill=rgb(hue + rnd.uniform(-0.12, 0.12) + (0.5 if i == 6 else 0), rnd.uniform(0.45, 0.9), rnd.uniform(0.35, 0.95)))
    return img.filter(ImageFilter.GaussianBlur(90))


main()
