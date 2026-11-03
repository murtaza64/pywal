"""Palette Studio in a browser tab (Pyodide): the same Studio and page, export only.

The browser has no ImageMagick, no apps to sync and no wallpaper folder. Images the user adds are
written to the in-memory filesystem; thumbnails, blur and the image average come from Pillow.
Apply, sync, saved themes, history and backups do not exist here.
"""

import io
import json
import os
import sys
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageFilter

from .. import util
from .server import DEFAULT_LOOK, IMAGE_EXTS, Studio


def average_color(img):
    """Mean colour of the image, standing in for ImageMagick's `-resize 1x1!`."""
    with Image.open(img) as im:
        r, g, b = im.convert("RGB").resize((1, 1), Image.BOX).getpixel((0, 0))
    return f"#{r:02x}{g:02x}{b:02x}"


class WebStudio(Studio):
    def __init__(self, root):
        os.environ.setdefault("PYWAL_CACHE_DIR", os.path.join(root, "preview"))
        os.makedirs(os.environ["PYWAL_CACHE_DIR"], exist_ok=True)
        dirs = {k: os.path.join(root, k) for k in ("live", "walls", "scratch", "backups")}
        for d in dirs.values():
            os.makedirs(d, exist_ok=True)
        super().__init__(live_dir=dirs["live"], wallpapers=dirs["walls"], scratch=dirs["scratch"], backups=dirs["backups"], allow_apply=False, targets=[])
        if sys.platform == "emscripten":
            # No ImageMagick in the browser; the desktop keeps its own average.
            util.image_average_color = average_color

    def state(self):
        return {**super().state(), "host": "browser", "liveDir": "this tab", "liveIsSystem": False, "engine": {"missing": []}, "web": True}

    def add_image(self, name, data):
        """Store an image the user picked; returns its path. Same-named files replace each other."""
        name = os.path.basename(name).replace("/", "_") or "wallpaper"
        if Path(name).suffix.lower() not in IMAGE_EXTS:
            raise ValueError(f"{name}: not a supported image")
        path = os.path.join(self.wallpapers, name)
        with open(path, "wb") as f:
            # From the page this is a JS Uint8Array proxy.
            f.write(data.to_bytes() if hasattr(data, "to_bytes") else data)
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
        """The draft's colors.json, palette.json/css and every template, as wal/… in one zip."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(Path(self.preview_dir).rglob("*")):
                if p.is_file():
                    z.write(p, f"wal/{p.relative_to(self.preview_dir)}")
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

