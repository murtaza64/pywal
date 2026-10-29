"""Colour quantization across image formats and runtimes."""

import os
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

from pywal import colorthief


def gradient(path, mode):
    img = Image.new("RGB", (64, 64))
    img.putdata([(x * 4, y * 4, 128) for y in range(64) for x in range(64)])
    img.convert(mode).save(path)
    return path


class TestGetPalette(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="colorthief-test-")

    def test_greyscale_wallpapers_with_and_without_alpha_yield_a_palette(self):
        for mode in ("L", "LA", "1"):
            with self.subTest(mode=mode):
                colors = colorthief.get_palette(gradient(os.path.join(self.dir, f"{mode}.png"), mode), color_count=8)
                self.assertGreater(len(colors), 1)

    def test_without_the_rust_quantizer_the_pure_python_port_returns_a_palette(self):
        path = gradient(os.path.join(self.dir, "rgb.png"), "RGB")
        # A None entry makes `import modern_colorthief` raise ImportError, as in Pyodide.
        with mock.patch.dict(sys.modules, {"modern_colorthief": None}):
            colors = colorthief.get_palette(path, color_count=8)
        self.assertGreater(len(colors), 1)
        self.assertTrue(all(len(c) == 3 and all(0 <= v <= 255 for v in c) for c in colors))


if __name__ == "__main__":
    unittest.main()
