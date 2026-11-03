"""Palette Studio's browser-tab backend (pywal.studio.web), run under CPython."""

import io
import json
import os
import tempfile
import unittest
import zipfile
from urllib.parse import quote

from PIL import Image

from pywal.studio.web import WebStudio, average_color


def png(w=160, h=90):
    img = Image.new("RGB", (w, h))
    img.putdata([((x * 7) % 256, (y * 11) % 256, (x * y) % 256) for y in range(h) for x in range(w)])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class TestWebStudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.studio = WebStudio(tempfile.mkdtemp(prefix="web-studio-test-"))
        cls.image = cls.studio.add_image("my wall.png", png())

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
        self.assertTrue({"wal/colors.json", "wal/palette.json", "wal/colors-kitty.conf"} <= set(names))

    def test_thumbnails_and_blur_come_from_pillow(self):
        for url in (f"/api/image?path={quote(self.image)}&w=80", f"/api/blur?path={quote(self.image)}&sigma=6&dim=0.3&w=120"):
            status, mime, raw = self.get(url)
            self.assertEqual((status, mime), (200, "image/jpeg"), url)
            self.assertLessEqual(Image.open(io.BytesIO(raw)).width, 120)

    def test_apply_sync_and_saving_are_refused_and_write_nothing_outside_the_tab(self):
        refused = {
            path: self.studio.handle("POST", path, json.dumps({"targets": ["files", "kitty"], "name": "x", "look": {"blur": 4}}))[0]
            for path in ("/api/apply", "/api/plan", "/api/themes/save", "/api/sync", "/api/history")
        }
        self.assertTrue(all(status >= 400 for status in refused.values()), refused)
        self.assertEqual(json.loads(self.get("/api/sync")[2]), {"targets": []})
        self.assertEqual(os.listdir(self.studio.live_dir), [])
        self.assertEqual(os.listdir(self.studio.backups), [])

    def test_history_backup_and_cached_scheme_drafts_cannot_load(self):
        for key, value in (("history", "20260101-000000"), ("restore", "20260101-000000"), ("scheme", "x.json")):
            status, _, body = self.studio.handle("POST", "/api/preview", json.dumps({"image": self.image, key: value}))
            self.assertEqual(status, 400, (key, body))

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
        self.assertEqual(average_color(path), "#643219")


if __name__ == "__main__":
    unittest.main()
