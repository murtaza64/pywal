"""Palette Studio's browser-tab backend (pywal.studio.web), run under CPython."""

import io
import json
import os
import tempfile
import unittest
from unittest import mock
import zipfile
from pathlib import Path
from urllib.parse import quote

from PIL import Image

from pywal.studio.web import WebStudio
from pywal.util import image_average_color


def png(w=160, h=90):
    img = Image.new("RGB", (w, h))
    img.putdata([((x * 7) % 256, (y * 11) % 256, (x * y) % 256) for y in range(h) for x in range(w)])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class TestWebStudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # In the tab the worker points XDG_CONFIG_HOME at IndexedDB; here saved themes go to a temp dir,
        # never the developer's ~/.config/wal.
        cls.conf = tempfile.mkdtemp(prefix="web-studio-conf-")
        cls.patch = mock.patch("pywal.studio.server.CONF_DIR", cls.conf)
        cls.patch.start()
        cls.studio = WebStudio(tempfile.mkdtemp(prefix="web-studio-test-"), kept=True)
        cls.image = cls.studio.add_image("my wall.png", png())

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()

    def get(self, url):
        return self.studio.handle("GET", url)

    def test_state_marks_the_tab_export_only_and_lists_added_images(self):
        state = json.loads(self.get("/api/state")[2])
        self.assertTrue(state["web"])
        self.assertFalse(state["allowApply"])
        self.assertIn("my wall.png", [w["name"] for w in state["wallpapers"]])

    def test_preview_then_export_zip_holds_the_scheme_contract_and_templates(self):
        status, _, body = self.studio.handle("POST", "/api/preview", json.dumps({"image": self.image, "settings": {"seed": "7"}, "look": {"blur": 8}}))
        self.assertEqual(status, 200, body)
        status, mime, raw = self.get("/api/export.zip")
        names = zipfile.ZipFile(io.BytesIO(raw)).namelist()
        self.assertEqual((status, mime), (200, "application/zip"))
        self.assertTrue({"wal/colors.json", "wal/palette.json", "wal/colors-kitty.conf", "wal/wallpaper.blurred", "wal/kitty-glass.conf"} <= set(names))
        z = zipfile.ZipFile(io.BytesIO(raw))
        self.assertEqual(Image.open(io.BytesIO(z.read("wal/wallpaper.blurred"))).size, Image.open(self.image).size)
        glass = z.read("wal/kitty-glass.conf").decode()
        self.assertIn("background_image ~/.cache/wal/wallpaper.blurred", glass)
        self.assertIn("background_tint 0.95", glass)

    def test_a_browser_decode_is_used_for_the_palette_only_when_it_is_the_same_picture(self):
        from pywal import decoded, mmcq

        jpg = io.BytesIO()
        Image.open(io.BytesIO(png())).save(jpg, "JPEG", quality=80)
        path = self.studio.add_image("wall.jpg", jpg.getvalue())
        pillow = Image.open(path).convert("RGB")
        # A decoder that rounds one level differently: kept, and the palette reads its pixels.
        shifted = Image.eval(pillow, lambda v: min(v + 1, 255)).convert("RGBA")
        self.studio.add_image("wall.jpg", jpg.getvalue(), (shifted.width, shifted.height, shifted.tobytes()))
        self.assertTrue(self.studio.decoded[path])
        self.assertEqual(mmcq.get_palette(path, 8), mmcq.quantize(shifted.convert("RGB").tobytes(), 3, 10, 8))
        # A rotated decode (EXIF applied) is refused; Pillow's pixels are used.
        turned = pillow.transpose(Image.Transpose.ROTATE_180).convert("RGBA")
        self.studio.add_image("wall.jpg", jpg.getvalue(), (turned.width, turned.height, turned.tobytes()))
        self.assertFalse(self.studio.decoded[path])
        self.assertNotIn(path, decoded.PIXELS)

    def test_thumbnails_and_blur_come_from_pillow(self):
        for url in (f"/api/image?path={quote(self.image)}&w=80", f"/api/blur?path={quote(self.image)}&sigma=6&dim=0.3&w=120"):
            status, mime, raw = self.get(url)
            self.assertEqual((status, mime), (200, "image/jpeg"), url)
            self.assertLessEqual(Image.open(io.BytesIO(raw)).width, 120)

    def test_apply_sync_and_saving_are_refused_and_write_nothing_outside_the_tab(self):
        refused = {
            path: self.studio.handle("POST", path, json.dumps({"targets": ["files", "kitty"], "name": "x", "look": {"blur": 4}}))[0]
            for path in ("/api/apply", "/api/plan", "/api/sync", "/api/history")
        }
        self.assertTrue(all(status >= 400 for status in refused.values()), refused)
        self.assertEqual(json.loads(self.get("/api/sync")[2]), {"targets": []})
        self.assertEqual(os.listdir(self.studio.live_dir), [])
        self.assertEqual(os.listdir(self.studio.backups), [])

    def test_history_backup_and_cached_scheme_drafts_cannot_load(self):
        for key, value in (("history", "20260101-000000"), ("restore", "20260101-000000"), ("scheme", "x.json")):
            status, _, body = self.studio.handle("POST", "/api/preview", json.dumps({"image": self.image, key: value}))
            self.assertEqual(status, 400, (key, body))

    def test_seeds_reach_the_page_exactly(self):
        from pywal.settings import SEED_MAX

        status, _, body = self.studio.handle("POST", "/api/preview", json.dumps({"image": self.image, "settings": {"seed": ""}}))
        res = json.loads(body)
        self.assertLessEqual(int(res["seed"]), SEED_MAX)  # new seeds survive JavaScript numbers
        big = str(2**62 + 12345)
        res = json.loads(self.studio.handle("POST", "/api/preview", json.dumps({"image": self.image, "settings": {"seed": big}}))[2])
        self.assertEqual(res["seed"], big)  # and older large seeds come back as exact strings

    def test_a_saved_theme_is_listed_and_loads_back_as_the_draft(self):
        post = lambda path, body: self.studio.handle("POST", path, json.dumps(body))
        status, _, body = post("/api/preview", {"image": self.image, "settings": {"seed": "11"}})
        self.assertEqual(status, 200, body)
        drafted = json.loads(body)["colors"]["colors"]
        status, _, body = post("/api/themes/save", {"name": "tab-theme"})
        self.assertEqual(status, 200, body)
        self.assertIn("kept in this browser", json.loads(body)["saved"])
        self.assertTrue(os.path.isfile(os.path.join(self.conf, "colorschemes", "dark", "tab-theme.json")))
        themes = json.loads(self.get("/api/themes")[2])
        self.assertTrue(themes["canSave"])
        self.assertIn("tab-theme", themes["user"]["dark"])
        self.assertEqual(post("/api/themes/save", {"name": "tab-theme"})[0], 400)  # exists; the page asks first
        status, _, body = post("/api/preview", {"image": self.image, "theme": {"source": "user", "name": "tab-theme"}})
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["colors"]["colors"]["color4"], drafted["color4"])

    def test_images_outside_the_tab_are_refused(self):
        self.assertEqual(self.get(f"/api/image?path={quote(os.path.abspath(__file__))}")[0], 403)
        self.assertEqual(self.get("/api/blur?path=/etc/hosts")[0], 403)

    def test_non_image_uploads_are_refused(self):
        with self.assertRaises(ValueError):
            self.studio.add_image("notes.txt", b"hello")

    def test_image_average_is_the_mean_colour(self):
        path = os.path.join(tempfile.mkdtemp(), "half.png")
        img = Image.new("RGB", (2, 1))
        img.putdata([(0, 0, 0), (200, 100, 50)])
        img.save(path)
        self.assertEqual(image_average_color(path), "#643219")


class TestPrefixSafe(unittest.TestCase):
    """The page and site scripts use relative URLs, so the studio can be hosted under a path prefix."""

    def test_no_root_absolute_urls_in_the_page_or_site_scripts(self):
        import re

        root = Path(__file__).resolve().parent.parent
        files = [root / "pywal/studio/static" / n for n in ("studio.js", "index.html")] + [root / "site" / n for n in ("boot.js", "sw.js")]
        pattern = re.compile(r"""(?:["'`(]|href=|src=)/(?:api|static|web|samples|sw\.js|icon\.png)""")
        hits = [f"{f.name}:{i}" for f in files for i, line in enumerate(f.read_text().splitlines(), 1) if pattern.search(line)]
        # The worker also names Pyodide filesystem paths (/web, /engine) and the engine's own /api routes;
        # only its network fetches must be relative.
        worker = (root / "site/worker.js").read_text().splitlines()
        hits += [f"worker.js:{i}" for i, line in enumerate(worker, 1) if re.search(r"""fetch\(\s*["'`]/""", line)]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
