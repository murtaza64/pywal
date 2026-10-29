"""Browser export engine (site/walexport.py), run under CPython."""

import importlib.util
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent.parent


def load_engine(out):
    os.environ["PYWAL_CACHE_DIR"] = out
    spec = importlib.util.spec_from_file_location("walexport", ROOT / "site" / "walexport.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestWalexport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="walexport-test-")
        cls.engine = load_engine(os.path.join(cls.dir, "out"))
        img = Image.new("RGB", (160, 90))
        img.putdata([((x * 7) % 256, (y * 11) % 256, (x * y) % 256) for y in range(90) for x in range(160)])
        cls.image = os.path.join(cls.dir, "in.png")
        img.save(cls.image)

    def test_generate_exports_scheme_contract_and_templates_naming_the_wallpaper_by_file_name(self):
        result = self.engine.generate(self.image, "my wall.png", json.dumps({"seed": "7", "contrast": 2}))
        self.assertTrue({"colors.json", "palette.json", "colors-kitty.conf", "colors.css"} <= set(result["files"]))
        self.assertEqual(json.loads(result["files"]["colors.json"])["wallpaper"], "my wall.png")
        self.assertEqual(result["colors"]["wallpaper"], "my wall.png")
        self.assertEqual(result["seed"], "7")
        names = zipfile.ZipFile(io.BytesIO(result["zip"])).namelist()
        self.assertEqual(sorted(names), sorted(f"wal/{n}" for n in result["files"]))

    def test_same_seed_and_settings_give_the_same_palette(self):
        settings = json.dumps({"seed": "11", "light": True, "saturate": 20})
        first = self.engine.generate(self.image, "a.png", settings)["colors"]["colors"]
        second = self.engine.generate(self.image, "a.png", settings)["colors"]["colors"]
        self.assertEqual(first, second)

    def test_image_average_comes_from_pillow(self):
        path = os.path.join(self.dir, "half.png")
        img = Image.new("RGB", (2, 1))
        img.putdata([(0, 0, 0), (200, 100, 50)])
        img.save(path)
        self.assertEqual(self.engine.average_color(path), "#643219")


if __name__ == "__main__":
    unittest.main()
