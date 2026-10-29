"""Palette Studio keeps previews out of the live cache and writes it only through Apply."""

import colorsys
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
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
    def __init__(self, *extra, env=None):
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
        env = {**{k: v for k, v in os.environ.items() if k != "PYWAL_CACHE_DIR"}, "XDG_CONFIG_HOME": os.path.join(self.root, "config"), **(env or {})}
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
        return {str(p.relative_to(self.live)): p.read_bytes() for p in Path(self.live).rglob("*") if p.is_file()}

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

    def test_missing_imagemagick_is_reported_instead_of_dropping_the_preview(self):
        # A launchd service gets a bare PATH without Homebrew; the engine then exits mid-request.
        studio = StudioServer(env={"PATH": "/usr/bin:/bin"})
        self.addCleanup(studio.close)
        with self.assertRaises(urllib.error.HTTPError) as err:
            studio.post("/api/preview", {"image": os.path.join(studio.walls, "sweep.png")})
        self.assertEqual(err.exception.code, 500)
        self.assertIn("ImageMagick", json.load(err.exception)["error"])
        self.assertIn("magick", studio.get("/api/state")["engine"]["missing"])

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
        self.assertEqual(live["studio"], {"blur": 8.0, "tint": 0.7, "dim": 0.0})
        self.assertTrue(os.path.isfile(os.path.join(studio.live, "colors-kitty.conf")))
        # Backup folders are named by time; history/ and history.jsonl sit beside them.
        backups = [n for n in os.listdir(os.path.join(studio.root, "backups")) if n[:8].isdigit()]
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


    def test_theme_list_carries_an_eight_cell_band_per_theme(self):
        studio = StudioServer()
        self.addCleanup(studio.close)
        bands = studio.get("/api/themes")["bands"]
        self.assertEqual(bands["builtin/dark/ashes"], ["#1c2023", "#c7ae95", "#95c7ae", "#aec795", "#ae95c7", "#c795ae", "#95aec7", "#c7ccd1"])

    def test_cached_scheme_loads_as_the_draft_with_its_settings(self):
        studio = StudioServer()
        self.addCleanup(studio.close)
        sweep = os.path.join(studio.walls, "sweep.png")
        # Any rendered draft has the cached-scheme shape; a theme draft avoids needing ImageMagick.
        generated = studio.post("/api/preview", {"image": sweep, "settings": {"contrast": 2.5}, "theme": {"source": "builtin", "name": "ashes"}})["colors"]
        os.makedirs(os.path.join(studio.live, "schemes"))
        Path(studio.live, "schemes", "sweep_dark_colorthief.json").write_text(json.dumps(generated))
        before = studio.live_snapshot()
        listed = studio.get("/api/schemes")
        self.assertEqual([(s["id"], s["available"], s["band"][1]) for s in listed], [("sweep_dark_colorthief.json", True, generated["colors"]["color1"])])
        draft = studio.post("/api/preview", {"image": sweep, "scheme": "sweep_dark_colorthief.json"})["colors"]
        self.assertEqual(draft["colors"]["red"], generated["colors"]["red"])
        self.assertEqual(draft["settings"]["contrast"], 2.5)
        self.assertEqual(studio.live_snapshot(), before)

    def test_cached_scheme_names_cannot_leave_the_schemes_folder(self):
        studio = StudioServer()
        self.addCleanup(studio.close)
        with self.assertRaises(urllib.error.HTTPError) as err:
            studio.post("/api/preview", {"image": os.path.join(studio.walls, "sweep.png"), "scheme": "../colors.json"})
        self.assertEqual(err.exception.code, 400)

    def test_es_desktop_apply_is_proven_by_the_app_receipt_and_undone_by_a_backup(self):
        receipt = os.path.join(tempfile.mkdtemp(prefix="es-receipt-"), "appearance-receipt.json")
        self.addCleanup(shutil.rmtree, os.path.dirname(receipt), True)
        studio = StudioServer("--allow-apply", env={"PYWAL_STUDIO_ES_RECEIPT": receipt})
        self.addCleanup(studio.close)
        # Stand-in for es-desktop (the external app): it re-reads colors.json and records what it shows.
        Path(receipt).write_text(json.dumps({"schema": "es-appearance-receipt/1", "background": "#010203"}))
        stop = threading.Event()
        def follow():
            # es-desktop records the served palette; an open page acknowledges the revision it renders.
            while not stop.wait(0.1):
                live = json.loads(Path(studio.live, "colors.json").read_text())
                revision = json.loads(Path(studio.live, "palette.json").read_text())["revision"] if Path(studio.live, "palette.json").is_file() else None
                Path(receipt).write_text(json.dumps({"schema": "es-appearance-receipt/1", "background": live["special"]["background"], "walRevision": revision,
                                                     "applied": [{"host": "local", "walRevision": revision, "theme": "wallpaper"}]}))
        threading.Thread(target=follow, daemon=True).start()
        self.addCleanup(stop.set)
        sweep = os.path.join(studio.walls, "sweep.png")
        studio.post("/api/preview", {"image": sweep, "theme": {"source": "builtin", "name": "ashes"}})
        studio.post("/api/apply", {"targets": ["files"]})
        studio.post("/api/preview", {"image": sweep, "theme": {"source": "builtin", "name": "gruvbox"}})
        applied = {r["target"]: r["status"] for r in studio.post("/api/apply", {"targets": ["files", "es-desktop"]})["results"]}
        self.assertEqual(applied, {"files": "verified", "es-desktop": "verified"})
        self.assertEqual(json.loads(Path(receipt).read_text())["background"], "#282828")
        studio.post("/api/preview", {"restore": studio.get("/api/backups")[0]["name"]})
        undone = {r["target"]: r["status"] for r in studio.post("/api/apply", {"targets": ["files", "es-desktop"]})["results"]}
        self.assertEqual(undone, {"files": "verified", "es-desktop": "verified"})
        self.assertEqual(json.loads(Path(receipt).read_text())["background"], "#1c2023")

    def test_es_desktop_without_a_page_acknowledgement_is_only_loaded(self):
        receipt = os.path.join(tempfile.mkdtemp(prefix="es-receipt-"), "appearance-receipt.json")
        self.addCleanup(shutil.rmtree, os.path.dirname(receipt), True)
        # The app process holds the draft background already, but no page has acknowledged rendering it.
        Path(receipt).write_text(json.dumps({"schema": "es-appearance-receipt/1", "background": "#1c2023", "applied": []}))
        studio = StudioServer("--allow-apply", env={"PYWAL_STUDIO_ES_RECEIPT": receipt, "PYWAL_STUDIO_ES_WAIT": "0.5"})
        self.addCleanup(studio.close)
        studio.post("/api/preview", {"image": os.path.join(studio.walls, "sweep.png"), "theme": {"source": "builtin", "name": "ashes"}})
        result = studio.post("/api/apply", {"targets": ["files", "es-desktop"]})["results"][1]
        self.assertEqual(result["status"], "loaded")

    def test_es_desktop_that_never_shows_the_draft_is_a_mismatch(self):
        receipt = os.path.join(tempfile.mkdtemp(prefix="es-receipt-"), "appearance-receipt.json")
        self.addCleanup(shutil.rmtree, os.path.dirname(receipt), True)
        Path(receipt).write_text(json.dumps({"schema": "es-appearance-receipt/1", "background": "#010203"}))
        studio = StudioServer("--allow-apply", env={"PYWAL_STUDIO_ES_RECEIPT": receipt, "PYWAL_STUDIO_ES_WAIT": "0.5"})
        self.addCleanup(studio.close)
        studio.post("/api/preview", {"image": os.path.join(studio.walls, "sweep.png"), "theme": {"source": "builtin", "name": "ashes"}})
        result = studio.post("/api/apply", {"targets": ["files", "es-desktop"]})["results"][1]
        self.assertEqual(result["status"], "mismatch")

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

    def test_targets_flag_refuses_other_apps_on_the_server(self):
        studio = StudioServer("--allow-apply", "--targets", "files,es-desktop")
        self.addCleanup(studio.close)
        self.assertEqual([t["id"] for t in studio.get("/api/sync")["targets"]], ["files", "es-desktop"])
        studio.post("/api/preview", {"image": os.path.join(studio.walls, "sweep.png"), "theme": {"source": "builtin", "name": "ashes"}})
        before = studio.live_snapshot()
        for targets in (["kitty"], ["files", "system-wallpaper"], ["pywalfox"], ["tmux"]):
            with self.assertRaises(urllib.error.HTTPError) as err:
                studio.post("/api/apply", {"targets": targets})
            self.assertEqual(err.exception.code, 400)
        self.assertEqual(studio.live_snapshot(), before)
        self.assertEqual(studio.post("/api/apply", {"targets": ["files"]})["results"][0]["status"], "verified")

    def test_dim_darkens_the_blurred_wallpaper_kitty_loads(self):
        studio = StudioServer()
        self.addCleanup(studio.close)
        sweep = os.path.join(studio.walls, "sweep.png")
        mean = lambda dim: sum(Image.open(__import__("io").BytesIO(urllib.request.urlopen(
            f"http://127.0.0.1:{studio.port}/api/blur?path={urllib.parse.quote(sweep)}&sigma=4&dim={dim}", timeout=30).read())).convert("L").getdata())
        self.assertLess(mean(0.5), mean(0) * 0.6)

    def test_state_says_whether_apply_writes_the_live_wal_cache(self):
        studio = StudioServer()
        self.addCleanup(studio.close)
        self.assertFalse(studio.get("/api/state")["liveIsSystem"])

    def test_each_apply_is_recorded_with_its_palette_targets_and_results(self):
        studio = StudioServer("--allow-apply")
        self.addCleanup(studio.close)
        sweep = os.path.join(studio.walls, "sweep.png")
        studio.post("/api/preview", {"image": sweep, "theme": {"source": "builtin", "name": "ashes"}})
        studio.post("/api/apply", {"targets": ["files"]})
        studio.post("/api/preview", {"image": sweep, "theme": {"source": "builtin", "name": "gruvbox"}})
        # tmux has no server in the test environment: the attempt is recorded as partial, not as success.
        res = studio.post("/api/apply", {"targets": ["files", "tmux"]})
        self.assertIsNone(res["historyError"])
        history = studio.get("/api/history")
        self.assertEqual([(e["background"], e["outcome"], [r["status"] for r in e["results"]]) for e in history["entries"]],
                         [("#282828", "partial", ["verified", "skipped"]), ("#1c2023", "verified", ["verified"])])
        self.assertEqual([e["current"] for e in history["entries"]], [True, False])

    def test_history_finds_a_renamed_wallpaper_by_content_and_marks_missing_ones(self):
        studio = StudioServer("--allow-apply")
        self.addCleanup(studio.close)
        sweep = os.path.join(studio.walls, "sweep.png")
        studio.post("/api/preview", {"image": sweep, "theme": {"source": "builtin", "name": "ashes"}})
        studio.post("/api/apply", {"targets": ["files"]})
        os.rename(sweep, os.path.join(studio.walls, "renamed.png"))
        self.assertEqual(studio.get("/api/history")["entries"][0]["image"], os.path.join(studio.walls, "renamed.png"))
        os.remove(os.path.join(studio.walls, "renamed.png"))
        self.assertIsNone(studio.get("/api/history")["entries"][0]["image"])

    def test_an_interrupted_attempt_stays_unknown(self):
        studio = StudioServer("--allow-apply")
        self.addCleanup(studio.close)
        sweep = os.path.join(studio.walls, "sweep.png")
        studio.post("/api/preview", {"image": sweep, "theme": {"source": "builtin", "name": "ashes"}})
        studio.post("/api/apply", {"targets": ["files"]})
        log = Path(studio.root, "backups", "history.jsonl")
        attempt = json.loads(log.read_text().splitlines()[0])
        log.write_text(log.read_text() + json.dumps({**attempt, "id": "20990101-000000", "at": attempt["at"] + 1}) + "\n")
        self.assertEqual([e["outcome"] for e in studio.get("/api/history")["entries"]], ["unknown", "verified"])

    def test_history_pages_and_filters_by_wallpaper_without_losing_older_matches(self):
        studio = StudioServer("--allow-apply")
        self.addCleanup(studio.close)
        sweep, other = os.path.join(studio.walls, "sweep.png"), os.path.join(studio.walls, "other.png")
        shutil.copy(os.path.join(studio.walls, "test.jpg"), other)
        for image in (sweep, other, other):
            studio.post("/api/preview", {"image": image, "theme": {"source": "builtin", "name": "ashes"}})
            studio.post("/api/apply", {"targets": ["files"]})
        first = studio.get("/api/history?limit=2")
        self.assertEqual((len(first["entries"]), first["total"], first["hasMore"]), (2, 3, True))
        print_ = studio.get("/api/history?limit=1&offset=2")["entries"][0]["fingerprint"]
        only = studio.get(f"/api/history?fingerprint={urllib.parse.quote(print_)}")
        self.assertEqual([e["wallpaper"] for e in only["entries"]], [sweep])

    def test_only_the_newest_apply_of_the_live_palette_is_current(self):
        studio = StudioServer("--allow-apply")
        self.addCleanup(studio.close)
        sweep = os.path.join(studio.walls, "sweep.png")
        for name in ("ashes", "gruvbox", "ashes"):
            studio.post("/api/preview", {"image": sweep, "theme": {"source": "builtin", "name": name}})
            studio.post("/api/apply", {"targets": ["files"]})
        self.assertEqual([e["current"] for e in studio.get("/api/history")["entries"]], [True, False, False])

    def test_apply_reports_only_the_targets_this_instance_permits(self):
        studio = StudioServer("--allow-apply", "--targets", "files")
        self.addCleanup(studio.close)
        studio.post("/api/preview", {"image": os.path.join(studio.walls, "sweep.png"), "theme": {"source": "builtin", "name": "ashes"}})
        self.assertEqual([t["id"] for t in studio.post("/api/apply", {"targets": ["files"]})["probe"]["targets"]], ["files"])

    def test_a_refused_apply_leaves_no_history(self):
        studio = StudioServer("--allow-apply", "--targets", "files")
        self.addCleanup(studio.close)
        studio.post("/api/preview", {"image": os.path.join(studio.walls, "sweep.png"), "theme": {"source": "builtin", "name": "ashes"}})
        with self.assertRaises(urllib.error.HTTPError):
            studio.post("/api/apply", {"targets": ["kitty"]})
        self.assertEqual(studio.get("/api/history")["total"], 0)

    def test_an_applied_palette_loads_back_as_the_draft(self):
        studio = StudioServer("--allow-apply")
        self.addCleanup(studio.close)
        sweep = os.path.join(studio.walls, "sweep.png")
        studio.post("/api/preview", {"image": sweep, "theme": {"source": "builtin", "name": "gruvbox"}})
        studio.post("/api/apply", {"targets": ["files"]})
        entry = studio.get("/api/history")["entries"][0]
        draft = studio.post("/api/preview", {"image": sweep, "history": entry["id"]})["colors"]
        self.assertEqual(draft["special"]["background"], "#282828")

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
