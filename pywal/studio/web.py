"""Palette Studio in a browser tab (Pyodide): the same Studio and page, export only.

The browser has no ImageMagick, no apps to sync and no wallpaper folder. Images the user adds are
written to the in-memory filesystem; thumbnails and blur come from Pillow. Saved themes go to the
config dir, which the worker keeps in this browser's IndexedDB. Apply, sync and backups do not exist here.
"""

import io
import json
import os
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageFilter

from .. import decoded as decoded_pixels
from .server import DEFAULT_LOOK, IMAGE_EXTS, Studio


GLASS = """# WalStudio glass: include this from kitty.conf after colors-kitty.conf.
# wallpaper.blurred is the wallpaper at blur {blur:g}, dim {dim:g}.
background_image ~/.cache/wal/wallpaper.blurred
background_tint {tint:g}
"""


class WebStudio(Studio):
    def __init__(self, root, kept=False):
        os.environ.setdefault("PYWAL_CACHE_DIR", os.path.join(root, "preview"))
        os.makedirs(os.environ["PYWAL_CACHE_DIR"], exist_ok=True)
        dirs = {k: os.path.join(root, k) for k in ("live", "walls", "scratch", "backups")}
        for d in dirs.values():
            os.makedirs(d, exist_ok=True)
        super().__init__(live_dir=dirs["live"], wallpapers=dirs["walls"], scratch=dirs["scratch"], backups=dirs["backups"], allow_apply=False, targets=[])
        self.decoded = {}  # path -> whether the browser's decode is used for its palette
        self.kept = bool(kept)  # saved themes outlive the tab

    def state(self):
        return {**super().state(), "host": "browser", "liveDir": "this tab", "liveIsSystem": False, "engine": {"missing": []}, "web": True, "keptThemes": self.kept}

    def themes(self):
        return {**super().themes(), "canSave": True}

    def save_theme(self, body):
        super().save_theme(body)
        return {"saved": f"{body['name'].strip()} · kept in this browser" if self.kept else f"{body['name'].strip()} · until this tab closes (this browser does not keep site data)"}

    def add_image(self, name, data, decoded=None):
        """Store an image the user picked; returns its path. Same-named files replace each other.

        `decoded` is the browser's own decode, (width, height, RGBA bytes): generation uses it in place
        of Pyodide's Pillow, whose JPEG decoder differs from the desktop's (see pywal.decoded).
        """
        name = os.path.basename(name).replace("/", "_") or "wallpaper"
        if Path(name).suffix.lower() not in IMAGE_EXTS:
            raise ValueError(f"{name}: not a supported image")
        path = os.path.join(self.wallpapers, name)
        with open(path, "wb") as f:
            # From the page these are JS Uint8Array proxies.
            f.write(data.to_bytes() if hasattr(data, "to_bytes") else data)
        decoded_pixels.PIXELS.pop(path, None)
        if decoded is not None:
            width, height, rgba = decoded
            self.decoded[path] = decoded_pixels.register(path, int(width), int(height), rgba.to_bytes() if hasattr(rgba, "to_bytes") else rgba)
        return path

    def thumb(self, path, width):
        out = self.scratch_file("thumbs", path, f"w{width}", ".jpg")
        if not os.path.isfile(out):
            with Image.open(path) as im:
                im = im.convert("RGB")
                im.thumbnail((width, width * 4))
                im.save(out, quality=86)
        return out

    def blurred(self, path, sigma, dim=0.0):
        out = self.scratch_file("blurred", path, f"s{sigma:g}" + (f"-d{dim:g}" if dim else ""), ".jpg")
        if not os.path.isfile(out):
            with Image.open(path) as im:
                im = im.convert("RGB").filter(ImageFilter.GaussianBlur(sigma))
                if dim:
                    im = Image.blend(im, Image.new("RGB", im.size), dim)
                im.save(out, quality=90)
        return out

    def export_zip(self):
        """The draft's colors.json, palette.json/css and every template, as wal/… in one zip.

        With the draft's glass: wallpaper.blurred (what desktop Apply hands kitty) and kitty-glass.conf,
        which points kitty at it with the draft's tint.
        """
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(Path(self.preview_dir).rglob("*")):
                if p.is_file():
                    z.write(p, f"wal/{p.relative_to(self.preview_dir)}")
            look, wall = (self.last or {}).get("studio"), (self.last or {}).get("wallpaper")
            if look and wall and self.allowed_image(wall):
                z.write(self.blurred(wall, look["blur"], look["dim"]), "wal/wallpaper.blurred", zipfile.ZIP_STORED)
                z.writestr("wal/kitty-glass.conf", GLASS.format(tint=look["tint"], blur=look["blur"], dim=look["dim"]))
        return buf.getvalue()

    def handle(self, method, url, body=None):
        """One request from the page: (status, content type, bytes). Mirrors server.Handler for the routes the tab has."""
        u = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if method == "POST":
                data = json.loads(body or "{}")
                if u.path == "/api/preview":
                    return ok(self.preview(data))
                if u.path == "/api/themes/save":
                    return ok(self.save_theme(data))
                if u.path == "/api/plan":
                    self.set_look(data.get("look"))
                    return 403, *as_json({"error": "export only: nothing is applied from the browser"})
                return 404, *as_json({"error": "not available in the browser"})
            if u.path == "/api/state":
                return ok(self.state())
            if u.path in ("/api/image", "/api/blur"):
                path = q.get("path", "")
                if not self.allowed_image(path):
                    return 403, *as_json({"error": "image not allowed"})
                if u.path == "/api/blur":
                    path = self.blurred(path, float(q.get("sigma", DEFAULT_LOOK["blur"])), max(0.0, min(float(q.get("dim", 0) or 0), 0.8)))
                width = int(q.get("w", "0") or 0)
                out = self.thumb(path, min(width, 3840)) if width else path
                return 200, mime(out), Path(out).read_bytes()
            if u.path == "/api/output":
                target = os.path.join(self.preview_dir, os.path.basename(q.get("name", "")))
                if not os.path.isfile(target):
                    return 404, *as_json({"error": "no such output"})
                return 200, "text/plain; charset=utf-8", Path(target).read_bytes()
            if u.path == "/api/export.zip":
                return 200, "application/zip", self.export_zip()
            if u.path == "/api/themes":
                return ok(self.themes())
            if u.path == "/api/schemes":
                return ok([])
            if u.path == "/api/sync":
                return ok({"targets": []})
            if u.path == "/api/history":
                return ok({"entries": [], "offset": 0, "total": 0, "hasMore": False, "liveRevision": None, "liveDir": "this tab"})
            if u.path == "/api/backups":
                return ok([])
            return 404, *as_json({"error": "not found"})
        except (ValueError, AssertionError) as e:
            return 400, *as_json({"error": str(e) or type(e).__name__})
        except SystemExit:
            return 400, *as_json({"error": "the palette engine could not use this image"})


def ok(data):
    return 200, *as_json(data)


def as_json(data):
    return "application/json", json.dumps(data).encode()


def mime(path):
    return {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp"}.get(Path(path).suffix.lower(), "image/jpeg")

