#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "flask>=3.0",
#   "modern-colorthief",
# ]
# ///

from __future__ import annotations

import json
import logging
import os
import secrets
import tempfile
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

from pywal import palette
from pywal import util
from pywal.args import ARGS, shuffle_settings


# Configure root logging for pywal modules.
util.setup_logging(level=logging.INFO)
logging.getLogger("werkzeug").setLevel(logging.INFO)


ROOT = Path(__file__).resolve().parents[1]
WEBUI = ROOT / "webui"
ASSETS = WEBUI / "assets"
UPLOAD_DIR = Path(tempfile.gettempdir()) / "pywal-web" / "uploads"


app = Flask(
    __name__,
    static_folder=None,
)


def _current_wallpaper_path() -> str:
    from pywal import util

    wal = util.get_cache_file("wal")
    try:
        return util.read_file(wal)[0].strip()
    except Exception:
        return ""


def _display_path(path: str) -> str:
    try:
        home = str(Path.home())
        p = str(Path(path).expanduser())
        if p.startswith(home + os.sep):
            return "~" + p[len(home) :]
        if p == home:
            return "~"
        return p
    except Exception:
        return path


def _iter_images(d: Path) -> list[Path]:
    exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".tif"}
    out: list[Path] = []
    for p in d.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts:
            continue
        out.append(p)
    out.sort(key=lambda p: p.name.lower())
    return out


def _apply_params(params: dict) -> None:
    mapping = {
        "light": "light",
        "shading": "shading",
        "bg_strategy": "bg_strategy",
        "generation_strategy": "generation_strategy",
        "subtractive_initial": "subtractive_initial",
        "choose": "choose",
        "seed": "seed",
        "contrast": "contrast",
        "brightness": "brightness",
        "saturate": "saturate",

        # Background tuning
        "bg_lightness": "bg_lightness",
        "bg_chroma": "bg_chroma",
    }

    for k, attr in mapping.items():
        if k not in params:
            continue

        v = params[k]
        if k == "seed":
            # Seed is handled as a string in the web UI to avoid JS number precision issues.
            if v in (None, ""):
                continue
            try:
                v = int(str(v))
            except Exception:
                continue

        setattr(ARGS, attr, v)

    # Interactive behavior.
    ARGS.no_cache = True
    ARGS.debug = False

    if ARGS.seed is None:
        ARGS.seed = int.from_bytes(os.urandom(8), "big")


def _export_params() -> dict:
    return {
        "light": bool(getattr(ARGS, "light", False)),
        "shading": getattr(ARGS, "shading", None),
        "bg_strategy": getattr(ARGS, "bg_strategy", None),
        "generation_strategy": getattr(ARGS, "generation_strategy", None),
        "subtractive_initial": getattr(ARGS, "subtractive_initial", None),
        "choose": getattr(ARGS, "choose", None),
        "seed": (str(getattr(ARGS, "seed", None)) if getattr(ARGS, "seed", None) is not None else None),
        "contrast": getattr(ARGS, "contrast", None),
        "brightness": getattr(ARGS, "brightness", None),
        "saturate": getattr(ARGS, "saturate", None),

        "bg_lightness": getattr(ARGS, "bg_lightness", None),
        "bg_chroma": getattr(ARGS, "bg_chroma", None),
    }


@app.get("/")
def index():
    return send_from_directory(WEBUI, "index.html")


@app.get("/assets/<path:name>")
def assets(name: str):
    return send_from_directory(ASSETS, name)


@app.get("/api/wallpaper")
def api_wallpaper():
    p = _current_wallpaper_path()
    return jsonify({"path": p, "displayPath": _display_path(p)})


@app.get("/api/image")
def api_image():
    path = request.args.get("path", "")
    if not path:
        return ("missing path", 400)
    p = Path(path)
    if not p.exists() or not p.is_file():
        return ("not found", 404)

    # Local tool: allow arbitrary local paths.
    return send_file(p)


@app.post("/api/upload")
def api_upload():
    if "file" not in request.files:
        return ("missing file", 400)
    f = request.files["file"]
    if not f.filename:
        return ("missing filename", 400)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(f.filename).suffix or ".img"
    out = UPLOAD_DIR / f"{int(time.time())}-{secrets.token_hex(8)}{ext}"
    f.save(out)
    return jsonify({"path": str(out), "name": f.filename, "displayPath": _display_path(str(out))})


@app.post("/api/browse")
def api_browse():
    payload = request.get_json(force=True, silent=True) or {}
    path = payload.get("path") or _current_wallpaper_path()
    direction = payload.get("direction")
    if direction not in ("prev", "next"):
        return ("invalid direction", 400)
    if not path:
        return ("missing path", 400)

    p = Path(path).expanduser()
    if not p.exists() or not p.is_file():
        return ("not found", 404)

    siblings = _iter_images(p.parent)
    if not siblings:
        return ("no images in directory", 400)

    try:
        idx = siblings.index(p)
    except ValueError:
        idx = 0

    delta = -1 if direction == "prev" else 1
    nxt = siblings[(idx + delta) % len(siblings)]
    return jsonify({"path": str(nxt), "displayPath": _display_path(str(nxt))})


@app.post("/api/generate")
def api_generate():
    payload = request.get_json(force=True, silent=True) or {}
    image_path = payload.get("imagePath")
    params = payload.get("params") or {}
    if not image_path:
        return ("missing imagePath", 400)

    p = Path(image_path)
    if not p.exists() or not p.is_file():
        return (f"imagePath does not exist: {image_path}", 400)

    _apply_params(params)

    result = palette.get(str(p))
    colors = dict(result.get("colors", {}))
    colors.update(result.get("special", {}))

    return jsonify(
        {
            "imagePath": str(p),
            "displayPath": _display_path(str(p)),
            "params": _export_params(),
            "colors": colors,
            "debug": [],
        }
    )


@app.post("/api/shuffle")
def api_shuffle():
    payload = request.get_json(force=True, silent=True) or {}
    image_path = payload.get("imagePath")
    mode = payload.get("mode")
    params = payload.get("params") or {}
    if not image_path:
        return ("missing imagePath", 400)
    if mode not in ("post", "all"):
        return ("invalid mode", 400)

    p = Path(image_path)
    if not p.exists() or not p.is_file():
        return (f"imagePath does not exist: {image_path}", 400)

    _apply_params(params)
    ARGS.shuffle = mode
    shuffle_settings()

    # If choose=random, reseed so repeated shuffles actually change output.
    if "random" in str(getattr(ARGS, "choose", "")):
        ARGS.seed = int.from_bytes(os.urandom(8), "big")

    return jsonify({"params": _export_params()})


def main() -> None:
    host = os.environ.get("PYWAL_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("PYWAL_WEB_PORT", "4740"))
    url = f"http://{host}:{port}/"
    print(url)

    # Flask reloader gives live reload on backend changes.
    app.run(host=host, port=port, debug=True)


if __name__ == "__main__":
    main()
