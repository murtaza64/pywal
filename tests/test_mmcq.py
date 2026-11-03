"""The browser's quantizer (pywal.mmcq) gives the desktop's palettes."""

import os
import random
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image, ImageDraw, ImageFilter

from pywal import colorthief, mmcq

try:
    import modern_colorthief
except ImportError:
    modern_colorthief = None


def wallpaper(path, seed, mode="RGB", size=(640, 360), **save):
    """Blurred random fields: many colours, uneven populations, a few near-white pixels."""
    rnd = random.Random(seed)
    img = Image.new("RGB", size, tuple(rnd.randrange(60) for _ in range(3)))
    d = ImageDraw.Draw(img)
    for _ in range(9):
        x, y, r = rnd.uniform(0, size[0]), rnd.uniform(0, size[1]), rnd.uniform(20, 160)
        d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(rnd.randrange(256) for _ in range(3)))
    d.rectangle([0, 0, 30, 30], fill=(255, 255, 255))
    img = img.filter(ImageFilter.GaussianBlur(rnd.uniform(0, 12)))
    if mode == "RGBA":
        img.putalpha(Image.linear_gradient("L").resize(size))
    img.convert(mode).save(path, **save)
    return path


@unittest.skipIf(modern_colorthief is None, "needs the Rust wheel to compare against")
class TestSameAsDesktop(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="mmcq-test-")

    def check(self, path):
        for n in (2, 8, 12, 16, 20):
            with self.subTest(path=os.path.basename(path), colors=n):
                self.assertEqual(mmcq.get_palette(path, n), colorthief.get_palette(path, n))

    def test_png_rgb_rgba_and_palette(self):
        for seed in range(6):
            self.check(wallpaper(os.path.join(self.dir, f"{seed}.png"), seed))
        self.check(wallpaper(os.path.join(self.dir, "a.png"), 7, mode="RGBA"))
        self.check(wallpaper(os.path.join(self.dir, "p.png"), 8, mode="P"))

    def test_lossy_formats_read_through_the_same_decoder(self):
        for seed in range(6):
            self.check(wallpaper(os.path.join(self.dir, f"{seed}.jpg"), seed, quality=80))
        self.check(wallpaper(os.path.join(self.dir, "w.webp"), 9, quality=70))

    def test_flat_image(self):
        path = os.path.join(self.dir, "flat.png")
        Image.new("RGB", (64, 64), (40, 90, 200)).save(path)
        self.check(path)


class TestBrowserPath(unittest.TestCase):
    def test_without_the_wheel_get_palette_uses_the_port(self):
        path = wallpaper(os.path.join(tempfile.mkdtemp(prefix="mmcq-test-"), "x.jpg"), 3)
        # A None entry makes `import modern_colorthief` raise ImportError, as in Pyodide.
        with mock.patch.dict(sys.modules, {"modern_colorthief": None}):
            colors = colorthief.get_palette(path, color_count=8)
        self.assertEqual(colors, mmcq.get_palette(path, 8))


if __name__ == "__main__":
    unittest.main()
