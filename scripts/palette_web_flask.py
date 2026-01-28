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
import os
import secrets
import tempfile
import time
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

from pywal import palette
from pywal.args import ARGS


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


def _apply_params(params: dict) -> None:
    mapping = {
        "light": "light",
        "shading": "shading",
        "generation_strategy": "generation_strategy",
        "subtractive_initial": "subtractive_initial",
        "choose": "choose",
        "shuffle": "shuffle",
        "seed": "seed",
        "contrast": "contrast",
        "brightness": "brightness",
        "saturate": "saturate",
        "bg_chroma_floor": "bg_chroma_floor",
        "greyish_chroma_threshold": "greyish_chroma_threshold",
    }

    for k, attr in mapping.items():
        if k in params:
            setattr(ARGS, attr, params[k])

    # Interactive behavior.
    ARGS.no_cache = True
    ARGS.debug = False

    if ARGS.seed is None:
        ARGS.seed = int.from_bytes(os.urandom(8), "big")


@app.get("/")
def index():
    return send_from_directory(WEBUI, "index.html")


@app.get("/assets/<path:name>")
def assets(name: str):
    return send_from_directory(ASSETS, name)


@app.get("/api/wallpaper")
def api_wallpaper():
    return jsonify({"path": _current_wallpaper_path()})


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
    return jsonify({"path": str(out), "name": f.filename})


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
            "params": params,
            "colors": colors,
            "debug": [],
        }
    )


def main() -> None:
    host = os.environ.get("PYWAL_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("PYWAL_WEB_PORT", "4740"))
    url = f"http://{host}:{port}/"
    print(url)
    webbrowser.open(url)

    # Flask reloader gives live reload on backend changes.
    app.run(host=host, port=port, debug=True)


if __name__ == "__main__":
    main()
