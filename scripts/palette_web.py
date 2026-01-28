#!/usr/bin/env -S uv run --script

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from pywal import palette
from pywal.args import ARGS


ROOT = Path(__file__).resolve().parents[1]
WEBUI = ROOT / "webui"
ASSETS = WEBUI / "assets"
UPLOAD_DIR = Path(tempfile.gettempdir()) / "pywal-web" / "uploads"


def _json(handler: BaseHTTPRequestHandler, status: int, payload: object) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler: BaseHTTPRequestHandler) -> bytes:
    n = int(handler.headers.get("content-length", "0"))
    return handler.rfile.read(n)


def _serve_file(handler: BaseHTTPRequestHandler, path: Path) -> None:
    if not path.exists() or not path.is_file():
        handler.send_error(404)
        return

    if path.suffix == ".html":
        ctype = "text/html; charset=utf-8"
    elif path.suffix == ".css":
        ctype = "text/css; charset=utf-8"
    elif path.suffix == ".js":
        ctype = "application/javascript; charset=utf-8"
    else:
        ctype = "application/octet-stream"

    data = path.read_bytes()
    handler.send_response(200)
    handler.send_header("content-type", ctype)
    handler.send_header("content-length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _parse_multipart(body: bytes, boundary: bytes) -> dict[str, tuple[str | None, bytes]]:
    # Returns {field_name: (filename|None, content_bytes)}
    out: dict[str, tuple[str | None, bytes]] = {}
    marker = b"--" + boundary
    parts = body.split(marker)
    for part in parts:
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2]

        header_blob, _, content = part.partition(b"\r\n\r\n")
        headers = header_blob.decode("utf-8", errors="replace").split("\r\n")
        disp = ""
        for h in headers:
            if h.lower().startswith("content-disposition:"):
                disp = h
                break
        if not disp:
            continue

        # content-disposition: form-data; name="file"; filename="x.png"
        name = None
        filename = None
        for chunk in disp.split(";"):
            chunk = chunk.strip()
            if chunk.startswith("name="):
                name = chunk.split("=", 1)[1].strip().strip('"')
            if chunk.startswith("filename="):
                filename = chunk.split("=", 1)[1].strip().strip('"')
        if not name:
            continue
        out[name] = (filename, content.rstrip(b"\r\n"))
    return out


def _current_wallpaper_path() -> str:
    from pywal import util

    wal = util.get_cache_file("wal")
    try:
        return util.read_file(wal)[0].strip()
    except Exception:
        return ""


def _apply_params(params: dict) -> None:
    # Keep it simple: set ARGS fields directly.
    mapping = {
        "light": "light",
        "shading": "shading",
        "generation_strategy": "generation_strategy",
        "subtractive_initial": "subtractive_initial",
        "bg_strategy": "bg_strategy",
        "choose": "choose",
        "shuffle": "shuffle",
        "seed": "seed",
        "contrast": "contrast",
        "brightness": "brightness",
        "saturate": "saturate",
    }

    for k, attr in mapping.items():
        if k not in params:
            continue
        v = params[k]
        setattr(ARGS, attr, v)

    # Ensure interactive behavior.
    ARGS.no_cache = True
    ARGS.debug = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        # Keep CLI clean.
        return

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            return _serve_file(self, WEBUI / "index.html")

        if self.path.startswith("/assets/"):
            rel = self.path.removeprefix("/assets/")
            return _serve_file(self, ASSETS / rel)

        if self.path == "/api/wallpaper":
            path = _current_wallpaper_path()
            return _json(self, 200, {"path": path})

        if self.path.startswith("/api/image"):
            from urllib.parse import parse_qs, urlparse

            q = parse_qs(urlparse(self.path).query)
            path = (q.get("path") or [""])[0]
            if not path:
                self.send_error(400)
                return
            p = Path(path)
            if not p.exists() or not p.is_file():
                self.send_error(404)
                return

            # Basic content type by extension.
            ext = p.suffix.lower()
            if ext in (".jpg", ".jpeg"):
                ctype = "image/jpeg"
            elif ext == ".png":
                ctype = "image/png"
            elif ext == ".gif":
                ctype = "image/gif"
            else:
                ctype = "application/octet-stream"

            data = p.read_bytes()
            self.send_response(200)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_error(404)

    def do_POST(self):
        if self.path == "/api/upload":
            ctype = self.headers.get("content-type", "")
            if "multipart/form-data" not in ctype or "boundary=" not in ctype:
                return _json(self, 400, {"error": "expected multipart/form-data"})
            boundary = ctype.split("boundary=", 1)[1].encode("utf-8")
            body = _read_body(self)
            parts = _parse_multipart(body, boundary)
            if "file" not in parts:
                return _json(self, 400, {"error": "missing file field"})
            filename, content = parts["file"]
            if not filename:
                filename = "upload"

            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            ext = Path(filename).suffix or ".img"
            out = UPLOAD_DIR / f"{int(time.time())}-{secrets.token_hex(8)}{ext}"
            out.write_bytes(content)
            return _json(self, 200, {"path": str(out), "name": filename})

        if self.path == "/api/generate":
            try:
                payload = json.loads(_read_body(self).decode("utf-8"))
            except Exception as e:
                return _json(self, 400, {"error": f"bad json: {e}"})

            image_path = payload.get("imagePath")
            params = payload.get("params") or {}
            if not image_path:
                return _json(self, 400, {"error": "missing imagePath"})

            # Only allow reading uploaded files or existing paths.
            p = Path(image_path)
            if not p.exists():
                return _json(self, 400, {"error": f"imagePath does not exist: {image_path}"})

            _apply_params(params)

            # Ensure deterministic shuffle/seed behavior if provided.
            if ARGS.seed is None:
                ARGS.seed = int.from_bytes(os.urandom(8), "big")

            # Run pipeline (no cache writes due to ARGS.no_cache)
            try:
                result = palette.get(str(p))
            except Exception as e:
                return _json(self, 500, {"error": str(e)})

            # For UI: flatten to {background, foreground, color0.., bright_*, surface*}
            colors = dict(result.get("colors", {}))
            colors.update(result.get("special", {}))
            resp = {
                "imagePath": str(p),
                "params": params,
                "colors": colors,
                "debug": [],
            }
            return _json(self, 200, resp)

        return _json(self, 404, {"error": "unknown endpoint"})


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4737)
    ap.add_argument("--open", action="store_true")
    ns = ap.parse_args(argv)

    if not (WEBUI / "index.html").exists():
        print(f"webui not found at {WEBUI}", file=sys.stderr)
        return 2

    server = HTTPServer((ns.host, ns.port), Handler)
    url = f"http://{ns.host}:{ns.port}/"
    print(url)

    if ns.open:
        threading.Timer(0.2, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
