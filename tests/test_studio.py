"""Palette Studio keeps previews out of the live cache and writes it only through Apply."""

import colorsys
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

FILES = os.path.abspath("tests/test_files")


def colourful(path):
    """A saturated hue sweep; the bundled test photos are too grey for the palette engine."""
    img = Image.new("RGB", (240, 120))
    img.putdata([tuple(int(255 * v) for v in colorsys.hsv_to_rgb(x / 240, 0.4 + 0.6 * (y / 120), 0.35 + 0.6 * ((x * y) % 97) / 97)) for y in range(120) for x in range(240)])
    img.save(path)


class StudioServer:
    def __init__(self, *extra):
        self.root = tempfile.mkdtemp(prefix="studio-test-")
        self.live = os.path.join(self.root, "live")
        self.walls = os.path.join(self.root, "walls")
        os.makedirs(self.live)
        shutil.copytree(FILES, self.walls)
        colourful(os.path.join(self.walls, "sweep.png"))
        live_colors = {"wallpaper": os.path.join(self.walls, "test.jpg"), "special": {"background": "#010203", "foreground": "#eeeeee"}, "colors": {}}
        with open(os.path.join(self.live, "colors.json"), "w") as f:
            json.dump(live_colors, f)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        # A private config dir keeps saved themes out of the real ~/.config/wal.
        env = {**{k: v for k, v in os.environ.items() if k != "PYWAL_CACHE_DIR"}, "XDG_CONFIG_HOME": os.path.join(self.root, "config")}
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "pywal.studio", "--port", str(self.port), "--live-dir", self.live, "--wallpapers", self.walls, "--scratch", os.path.join(self.root, "scratch"), "--backups", os.path.join(self.root, "backups"), *extra],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for delay in [0.1, 0.2, 0.4, 0.8, 1.6, 3.2]:
            try:
                self.get("/api/state")
                return
            except OSError:
                time.sleep(delay)
        raise RuntimeError("studio did not start")

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=30) as r:
            return json.load(r)

    def post(self, path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)

    def live_snapshot(self):
        return {n: Path(self.live, n).read_bytes() for n in os.listdir(self.live)}

    def close(self):
        self.proc.terminate()
        self.proc.wait(10)
        shutil.rmtree(self.root, ignore_errors=True)


class TestStudio(unittest.TestCase):
    def test_preview_renders_outputs_without_touching_live_cache(self):
        studio = StudioServer()
        self.addCleanup(studio.close)
        before = studio.live_snapshot()
        res = studio.post("/api/preview", {"image": os.path.join(studio.walls, "sweep.png"), "settings": {"contrast": 1.5}})
        self.assertIn("colors-kitty.conf", res["outputs"])
        self.assertEqual(studio.live_snapshot(), before)

    def test_apply_is_refused_without_allow_apply(self):
        studio = StudioServer()
        self.addCleanup(studio.close)
        studio.post("/api/preview", {"image": os.path.join(studio.walls, "sweep.png")})
        with self.assertRaises(urllib.error.HTTPError) as err:
            studio.post("/api/apply", {"targets": ["files"]})
        self.assertEqual(err.exception.code, 403)

    def test_images_outside_wallpapers_are_not_served(self):
        studio = StudioServer()
        self.addCleanup(studio.close)
        with self.assertRaises(urllib.error.HTTPError) as err:
            studio.get("/api/image?path=/etc/hosts")
        self.assertEqual(err.exception.code, 403)

    def test_unusable_image_reports_an_error(self):
        studio = StudioServer()
        self.addCleanup(studio.close)
        with self.assertRaises(urllib.error.HTTPError) as err:
            studio.post("/api/preview", {"image": os.path.join(studio.walls, "test.png")})
        self.assertEqual(err.exception.code, 400)

    def test_apply_files_writes_draft_and_keeps_a_backup(self):
        studio = StudioServer("--allow-apply")
        self.addCleanup(studio.close)
        draft = studio.post("/api/preview", {"image": os.path.join(studio.walls, "sweep.png"), "look": {"blur": 8, "tint": 0.8}})["colors"]
        res = studio.post("/api/apply", {"targets": ["files"], "look": {"blur": 8, "tint": 0.7}})
        self.assertEqual(res["results"][0]["status"], "verified")
        live = json.loads(Path(studio.live, "colors.json").read_text())
        self.assertEqual(live["special"]["background"], draft["special"]["background"])
        self.assertEqual(live["studio"], {"blur": 8.0, "tint": 0.7})
        self.assertTrue(os.path.isfile(os.path.join(studio.live, "colors-kitty.conf")))
        backups = os.listdir(os.path.join(studio.root, "backups"))
        backup_colors = json.loads(Path(studio.root, "backups", backups[0], "colors.json").read_text())
        self.assertEqual(backup_colors["special"]["background"], "#010203")


    def test_builtin_theme_renders_every_template(self):
        studio = StudioServer()
        self.addCleanup(studio.close)
        res = studio.post("/api/preview", {"image": os.path.join(studio.walls, "sweep.png"), "theme": {"source": "builtin", "name": "ashes"}})
        self.assertEqual(res["colors"]["special"]["background"], "#1c2023")
        self.assertIn("delta.gitconfig", res["outputs"])
        self.assertIn("diff_plus_bg", res["colors"]["colors"])

    def test_saved_theme_loads_back_as_the_same_palette(self):
        studio = StudioServer("--allow-apply")
        self.addCleanup(studio.close)
        draft = studio.post("/api/preview", {"image": os.path.join(studio.walls, "sweep.png")})["colors"]
        studio.post("/api/themes/save", {"name": "sweep-test"})
        self.assertEqual(studio.get("/api/themes")["user"]["dark"], ["sweep-test"])
        loaded = studio.post("/api/preview", {"image": os.path.join(studio.walls, "sweep.png"), "theme": {"source": "user", "name": "sweep-test"}})["colors"]
        self.assertEqual(loaded["colors"]["red"], draft["colors"]["red"])
        self.assertEqual(loaded["special"]["background"], draft["special"]["background"])


    def test_undo_restores_the_theme_from_before_an_apply(self):
        studio = StudioServer("--allow-apply")
        self.addCleanup(studio.close)
        first = studio.post("/api/preview", {"image": os.path.join(studio.walls, "sweep.png")})["colors"]
        studio.post("/api/apply", {"targets": ["files"]})
        studio.post("/api/preview", {"image": os.path.join(studio.walls, "sweep.png"), "theme": {"source": "builtin", "name": "ashes"}})
        studio.post("/api/apply", {"targets": ["files"]})
        before_second = studio.get("/api/backups")[0]
        self.assertEqual(before_second["background"], first["special"]["background"])
        studio.post("/api/preview", {"restore": before_second["name"]})
        res = studio.post("/api/apply", {"targets": ["files"]})
        self.assertEqual(res["results"][0]["status"], "verified")
        self.assertEqual(json.loads(Path(studio.live, "colors.json").read_text())["colors"]["red"], first["colors"]["red"])

    def test_cross_site_form_posts_cannot_reach_apply(self):
        studio = StudioServer("--allow-apply")
        self.addCleanup(studio.close)
        req = urllib.request.Request(f"http://127.0.0.1:{studio.port}/api/apply", data=b'{"targets":["files"]}', headers={"Content-Type": "text/plain"})
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(err.exception.code, 403)
        req = urllib.request.Request(f"http://127.0.0.1:{studio.port}/api/apply", data=b"{}", headers={"Content-Type": "application/json", "Origin": "http://evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(err.exception.code, 403)

    def test_palette_service_serves_live_css_with_cors(self):
        studio = StudioServer()
        self.addCleanup(studio.close)
        with urllib.request.urlopen(f"http://127.0.0.1:{studio.port}/palette.css", timeout=10) as r:
            self.assertEqual(r.headers["Access-Control-Allow-Origin"], "*")
            self.assertIn("--wal-surface:", r.read().decode())


if __name__ == "__main__":
    unittest.main()
