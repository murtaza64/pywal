"""HTTP server for Palette Studio (stdlib only, loopback by default)."""

import hashlib
import json
import logging
import mimetypes
import os
import platform
import re
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import export, palette, util
from .. import theme as pywal_theme
from .. import contract
from ..color import Color
from ..args import ARGS, OPTIONS_TO_SAVE, parser as cli_parser
from ..settings import CONF_DIR, MODULE_DIR
from . import adapters

STATIC = Path(__file__).parent / "static"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
# Defaults mirror the dotfiles kitty setup: `magick -blur 0x16` and `background_tint 0.95`.
DEFAULT_LOOK = {"blur": 16, "tint": 0.95, "dim": 0.0}
# How often palette event streams check the live cache (one stat each).
PALETTE_POLL = 1.0
THEME_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
ANSI_NAMES = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]


def serve(host, port, live_dir, wallpapers, scratch, backups, allow_apply, targets=None):
    util.setup_logging(level=logging.INFO)
    studio = Studio(live_dir=live_dir, wallpapers=wallpapers, scratch=scratch, backups=backups, allow_apply=allow_apply, targets=targets)
    # One worker makes the strip's thumbnails ahead of the browser; dozens of concurrent ImageMagick
    # runs on first open would otherwise outlast a proxy's timeout.
    threading.Thread(target=studio.warm_thumbs, daemon=True).start()
    handler = type("Handler", (Handler,), {"studio": studio})
    # A page opens dozens of thumbnail requests at once; socketserver's default listen backlog (5)
    # drops the overflow, which a fronting proxy reports as 502s.
    server = type("Server", (ThreadingHTTPServer,), {"request_queue_size": 128})((host, port), handler)
    print(f"Palette Studio: http://{host}:{port}/  live={live_dir}  apply={'on' if allow_apply else 'off'}  targets={','.join(targets) if targets else 'all'}", flush=True)
    if not (shutil.which("magick") or shutil.which("convert")):
        print("WARNING: ImageMagick (magick) is not on PATH; generated previews will fail. Add its directory to PATH.", flush=True)
    server.serve_forever()


class Studio:
    def __init__(self, live_dir, wallpapers, scratch, backups, allow_apply, targets=None):
        # Sync targets this instance may plan or apply; None = every adapter.
        self.targets = targets
        self.live_dir = live_dir
        self.backups = backups
        self.wallpapers = wallpapers
        self.scratch = scratch
        self.preview_dir = os.environ["PYWAL_CACHE_DIR"]
        self.allow_apply = allow_apply
        # pywal keeps generation options in one global namespace; serialize all generation.
        self.lock = threading.Lock()
        self.last = None
        self.palette_memo = None

    def state(self):
        live = read_json(os.path.join(self.live_dir, "colors.json"))
        return {
            "host": socket.gethostname(),
            "platform": platform.system(),
            "allowApply": self.allow_apply,
            "targets": self.targets,
            "liveDir": display(self.live_dir),
            # The live wal cache is what kitty, Editspace, Firefox and tmux read; anything else is a private profile.
            "liveIsSystem": os.path.realpath(self.live_dir) == os.path.realpath(os.path.expanduser("~/.cache/wal")),
            "live": live,
            "look": {**DEFAULT_LOOK, **(live or {}).get("studio", {})},
            "defaults": generation_defaults(),
            "engine": {"missing": [] if shutil.which("magick") or shutil.which("convert") else ["magick"]},
            "wallpapers": self.wallpaper_index(),
        }

    def wallpaper_index(self):
        """Wallpapers with pixel size (blur scaling) and the live cache's scheme for each, if any."""
        schemes = {}
        for f in sorted(Path(self.live_dir, "schemes").glob("*.json")):
            data = read_json(str(f)) or {}
            if data.get("wallpaper"):
                schemes[os.path.realpath(data["wallpaper"])] = {"special": data.get("special"), "colors": data.get("colors")}
        return [{"name": p.name, "path": str(p), "size": image_size(p), "scheme": schemes.get(os.path.realpath(p))} for p in self.images()]

    def images(self):
        root = Path(self.wallpapers)
        if not root.is_dir():
            return []
        return sorted((p for p in root.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS), key=lambda p: p.name.lower())

    def allowed_image(self, path):
        """Serve only wallpapers, the live wallpaper and studio scratch output."""
        real = os.path.realpath(path)
        live = read_json(os.path.join(self.live_dir, "colors.json")) or {}
        roots = [os.path.realpath(self.wallpapers), os.path.realpath(self.scratch)]
        if any(real.startswith(r + os.sep) for r in roots):
            return os.path.isfile(real)
        return real == os.path.realpath(live.get("wallpaper", "")) and os.path.isfile(real)

    def preview(self, body):
        image = body.get("image")
        if not body.get("restore") and (not image or not self.allowed_image(image)):
            raise ValueError("image must be a wallpaper or the live wallpaper")
        with self.lock:
            apply_settings(body.get("settings") or {})
            theme, restore, scheme, applied = body.get("theme"), body.get("restore"), body.get("scheme"), body.get("history")
            try:
                colors = (
                    self.load_history(applied, image) if applied
                    else self.load_backup(restore) if restore
                    else self.load_scheme(scheme, image) if scheme
                    else load_theme(theme, image) if theme
                    else palette.get(image, cache_dir=self.preview_dir)
                )
            except SystemExit:
                # The CLI engine exits on a missing tool (ImageMagick); in a server that would kill the
                # request thread and drop the connection, so the draft would silently stop updating.
                missing = "" if shutil.which("magick") or shutil.which("convert") else " ImageMagick (magick) is not on this server's PATH."
                raise RuntimeError(f"palette engine exited.{missing}") from None
            colors = apply_overrides(colors, body.get("overrides") or {})
            colors["studio"] = clean_look(body.get("look") or {})
            # Templates render into the scratch cache (PYWAL_CACHE_DIR), never the live one.
            export.every(colors)
            with open(os.path.join(self.preview_dir, "colors.json"), "w") as f:
                json.dump(colors, f, indent=4)
            self.last = colors
        return {"colors": colors, "outputs": sorted(os.listdir(self.preview_dir))}

    def palette(self):
        """The live wal-palette contract (colours only), memoised on the cache files' mtimes; never writes."""
        stamp = tuple(os.path.getmtime(p) if os.path.isfile(p) else 0 for p in (os.path.join(self.live_dir, n) for n in ("colors.json", "palette.json")))
        if self.palette_memo is None or self.palette_memo[0] != stamp:
            try:
                built = contract.current(self.live_dir, persist=False)
            except (KeyError, TypeError, ValueError, OSError):
                # A partial or hand-edited colors.json must not take documents' colours down.
                logging.exception("palette contract build failed; serving the default palette")
                built = contract.build(contract.DEFAULT_COLORS)
            self.palette_memo = (stamp, built)
        return self.palette_memo[1]

    def begin_apply(self, targets):
        """Record an Apply attempt and its palette before any target is touched.

        Returns (entry, error): an attempt with no later result line stays "unknown" (interrupted);
        it is never replayed or assumed successful."""
        draft = self.last
        stamp = time.strftime("%Y%m%d-%H%M%S")
        folder = os.path.join(self.backups, "history")
        try:
            os.makedirs(folder, exist_ok=True)
            entry_id = next(i for i in (stamp + (f"-{n}" if n else "") for n in range(1000)) if not os.path.exists(os.path.join(folder, i + ".json")))
            with open(os.path.join(folder, entry_id + ".json"), "w") as f:
                json.dump(draft, f)
            try:
                revision = contract.build(draft)["revision"]
            except (KeyError, TypeError, ValueError):
                revision = None
            wallpaper = draft.get("wallpaper") or ""
            entry = {
                "id": entry_id, "phase": "attempt", "at": time.time(), "wallpaper": wallpaper, "fingerprint": fingerprint(wallpaper),
                "revision": revision, "background": draft["special"]["background"], "band": band(draft), "look": draft.get("studio"),
                "theme": draft.get("theme"), "liveDir": display(self.live_dir), "targets": targets,
            }
            self.append_history(entry)
            return entry, None
        except OSError as e:
            return None, f"history not recorded: {e}"

    def finish_apply(self, entry, results):
        """Record what each target reported for an attempt."""
        if not entry:
            return None, None
        statuses = [r.get("status") for r in results]
        result = {
            "id": entry["id"], "phase": "result", "at": time.time(),
            "results": [{k: r.get(k) for k in ("target", "status", "detail")} for r in results],
            # verified = every requested target proved it; partial = some did; none = no target proved it.
            "outcome": "verified" if statuses and all(s == "verified" for s in statuses) else "partial" if "verified" in statuses else "none",
            "backup": next((r.get("backup") for r in results if r.get("backup")), None),
        }
        try:
            self.append_history(result)
            return {**entry, **result}, None
        except OSError as e:
            return {**entry, "outcome": "unknown"}, f"history result not recorded: {e}"

    def append_history(self, line):
        with open(os.path.join(self.backups, "history.jsonl"), "a") as f:
            f.write(json.dumps(line) + "\n")

    def history(self, offset=0, limit=50, print_=None):
        """Applied history, newest first: attempts merged with their results, paged, optionally one wallpaper."""
        path = os.path.join(self.backups, "history.jsonl")
        merged = {}
        for line in Path(path).read_text().splitlines() if os.path.isfile(path) else []:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("phase") == "attempt":
                merged[rec["id"]] = {**rec, "outcome": "unknown", "results": []}
            elif rec.get("phase") == "result" and rec.get("id") in merged:
                merged[rec["id"]].update({k: v for k, v in rec.items() if k not in ("phase", "at")})
        entries = sorted(merged.values(), key=lambda e: e["at"], reverse=True)
        if print_:
            entries = [e for e in entries if e.get("fingerprint") == print_]
        live, here_dir = self.palette().get("revision"), display(self.live_dir)
        # Current = the newest Apply in this profile whose palette is what the theme files hold now
        # (an older Apply of the same palette is history, not current). Says nothing about other apps.
        current = next((e["id"] for e in sorted(merged.values(), key=lambda e: e["at"], reverse=True)
                        if live and e.get("revision") == live and e.get("liveDir") == here_dir), None)
        page = entries[offset:offset + limit]
        prints = {}
        for p in self.images():
            prints.setdefault(fingerprint(str(p)), str(p))
        for e in page:
            # The image may have moved or been copied: find it again by content fingerprint; else a placeholder.
            e["image"] = e["wallpaper"] if self.allowed_image(e["wallpaper"]) else prints.get(e.get("fingerprint")) if e.get("fingerprint") else None
            # Current = this entry's palette is what this profile's theme files hold now; says nothing about other apps.
            e["current"] = e["id"] == current
        return {"entries": page, "offset": offset, "total": len(entries), "hasMore": offset + limit < len(entries), "liveRevision": live, "liveDir": here_dir}

    def load_history(self, entry_id, image):
        """An applied palette as the draft, shown on `image` (its own wallpaper when found, else the current one)."""
        if not re.fullmatch(r"\d{8}-\d{6}(-\d+)?", str(entry_id)):
            raise ValueError("unknown history entry")
        path = os.path.join(self.backups, "history", entry_id + ".json")
        if not os.path.isfile(path):
            raise ValueError(f"history entry {entry_id} has no palette")
        colors = pywal_theme.parse(path)
        colors["wallpaper"] = image
        return colors

    def backup_list(self):
        """Apply backups, newest first: each is the live theme as it was before that Apply."""
        root = Path(self.backups)
        # Backup folders only (named by time); history/ holds applied palettes, not before-Apply state.
        entries = sorted((d for d in root.iterdir() if d.is_dir() and re.fullmatch(r"\d{8}-\d{6}(-\d+)?", d.name)), reverse=True) if root.is_dir() else []
        out = []
        for d in entries[:20]:
            data = read_json(str(d / "colors.json")) or {}
            out.append({"name": d.name, "background": data.get("special", {}).get("background"), "wallpaper": data.get("wallpaper")})
        return out

    def load_backup(self, name):
        """A backup's colors.json as the draft, so undo goes through the normal Apply and its proofs."""
        if not re.fullmatch(r"\d{8}-\d{6}(-\d+)?", str(name)):
            raise ValueError("unknown backup")
        path = os.path.join(self.backups, name, "colors.json")
        if not os.path.isfile(path):
            raise ValueError(f"backup {name} has no colors.json")
        return pywal_theme.parse(path)

    def permitted(self, requested):
        """The requested targets, refusing any outside this instance's --targets."""
        if not self.targets:
            return requested
        requested = requested or self.targets
        refused = [t for t in requested if t not in self.targets]
        if refused:
            raise ValueError(f"targets not permitted on this instance: {', '.join(refused)}")
        return requested

    def themes(self):
        roots = {"user": CONF_DIR, "builtin": MODULE_DIR}
        names = {s: {b: theme_names(os.path.join(root, "colorschemes", b)) for b in ("dark", "light")} for s, root in roots.items()}
        return {
            **names,
            # Row previews: "source/dark|light/name" -> color0-7.
            "bands": {
                f"{s}/{b}/{n}": band(read_json(os.path.join(roots[s], "colorschemes", b, n + ".json")))
                for s, groups in names.items() for b, ns in groups.items() for n in ns
            },
            "canSave": self.allow_apply,
        }

    def schemes(self):
        """The live cache's generated schemes (one per wallpaper, mode and backend), newest first."""
        out = []
        for f in Path(self.live_dir, "schemes").glob("*.json"):
            data = read_json(str(f)) or {}
            if not isinstance(data.get("colors"), dict) or not data.get("wallpaper"):
                continue
            settings = data.get("settings") or {}
            out.append({
                "id": f.name,
                "wallpaper": data["wallpaper"],
                "available": self.allowed_image(data["wallpaper"]),
                "light": bool(settings.get("light")),
                "background": (data.get("special") or {}).get("background"),
                "band": band(data),
                "mtime": f.stat().st_mtime,
            })
        return sorted(out, key=lambda s: s["mtime"], reverse=True)

    def load_scheme(self, name, image):
        """A cached scheme as the draft for `image`; its generation settings come with it."""
        path = Path(self.live_dir, "schemes", os.path.basename(str(name)))
        if path.suffix != ".json" or not path.is_file():
            raise ValueError("unknown cached scheme")
        colors = pywal_theme.parse(str(path))
        if not isinstance(colors.get("colors"), dict) or not isinstance(colors.get("special"), dict):
            raise ValueError(f"cached scheme {path.name} is not a colour scheme")
        ARGS.light = bool((colors.get("settings") or {}).get("light"))
        colors["wallpaper"] = image
        return colors

    def save_theme(self, body):
        """`wal --save-theme`: store the current draft as a user theme."""
        name = str(body.get("name", "")).strip()
        if not THEME_NAME.fullmatch(name):
            raise ValueError("theme names use letters, digits, - and _")
        draft = self.last
        if not draft:
            raise ValueError("Generate a preview first")
        path = os.path.join(CONF_DIR, "colorschemes", "light" if draft["settings"].get("light") else "dark", name + ".json")
        if os.path.exists(path) and not body.get("overwrite"):
            raise ValueError(f"theme {name} exists")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(draft, f, indent=4)
        return {"saved": display(path)}

    def set_look(self, look):
        """Glass settings change without regenerating; keep the draft colors.json in step."""
        if not look or not self.last:
            return
        with self.lock:
            self.last["studio"] = clean_look(look)
            with open(os.path.join(self.preview_dir, "colors.json"), "w") as f:
                json.dump(self.last, f, indent=4)

    def warm_thumbs(self):
        for p in self.images():
            try:
                self.thumb(str(p), 240)
            except OSError:
                logging.exception("thumbnail failed for %s", p)

    def thumb(self, path, width):
        """Downscaled copy for the browser; originals can be 4K+."""
        if not shutil.which("magick"):
            return path
        out = self.scratch_file("thumbs", path, f"w{width}", ".jpg")
        if not os.path.isfile(out):
            run(["magick", path, "-auto-orient", "-thumbnail", f"{width}x", "-quality", "86", out])
        return out if os.path.isfile(out) else path

    def blurred(self, path, sigma, dim=0.0):
        """The exact blurred (and dimmed) file Apply would hand to kitty, rendered into scratch."""
        if not shutil.which("magick"):
            raise ValueError("ImageMagick (magick) is required to render the blurred wallpaper")
        out = self.scratch_file("blurred", path, f"s{sigma:g}" + (f"-d{dim:g}" if dim else ""), Path(path).suffix or ".png")
        if not os.path.isfile(out):
            # Dim mixes the image toward black, the same as the preview's black overlay at that opacity.
            run(["magick", path, "-blur", f"0x{sigma:g}", *(["-fill", "black", "-colorize", f"{dim * 100:g}%"] if dim else []), out])
        return out

    def scratch_file(self, kind, path, variant, ext):
        stat = os.stat(path)
        key = hashlib.sha1(f"{os.path.realpath(path)}:{stat.st_mtime_ns}:{stat.st_size}:{variant}".encode()).hexdigest()[:16]
        folder = os.path.join(self.scratch, kind)
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, f"{Path(path).stem}-{variant}-{key}{ext}")


class Handler(BaseHTTPRequestHandler):
    studio: Studio

    def log_message(self, fmt, *args):
        logging.debug("http " + fmt, *args)

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        studio = self.studio
        try:
            if url.path in ("/", "/index.html"):
                return self.file(STATIC / "index.html")
            if url.path.startswith("/static/"):
                target = (STATIC / url.path.removeprefix("/static/")).resolve()
                if STATIC.resolve() not in target.parents:
                    return self.error(404, "not found")
                return self.file(target)
            if url.path == "/palette.css":
                return self.palette_css()
            if url.path == "/palette.json":
                return self.json(studio.palette(), cors=True)
            if url.path == "/palette/live.js":
                return self.file(STATIC / "palette-live.js", mime="text/javascript; charset=utf-8", cors=True)
            if url.path == "/palette/events":
                return self.palette_events()
            if url.path == "/api/state":
                return self.json(studio.state())
            if url.path == "/api/image":
                path = query.get("path", "")
                if not studio.allowed_image(path):
                    return self.error(403, "image not allowed")
                width = int(query.get("w", "0") or 0)
                return self.file(Path(studio.thumb(path, min(width, 3840)) if width else path), cache=True)
            if url.path == "/api/blur":
                path = query.get("path", "")
                if not studio.allowed_image(path):
                    return self.error(403, "image not allowed")
                out = studio.blurred(path, float(query.get("sigma", DEFAULT_LOOK["blur"])), max(0.0, min(float(query.get("dim", 0) or 0), 0.8)))
                width = int(query.get("w", "0") or 0)
                return self.file(Path(studio.thumb(out, width) if width else out), cache=True)
            if url.path == "/api/output":
                name = os.path.basename(query.get("name", ""))
                target = os.path.join(studio.preview_dir, name)
                if not name or not os.path.isfile(target):
                    return self.error(404, "no such output")
                return self.file(Path(target), mime="text/plain; charset=utf-8")
            if url.path == "/api/history":
                return self.json(studio.history(int(query.get("offset", 0) or 0), max(1, min(int(query.get("limit", 50) or 50), 200)), query.get("fingerprint") or None))
            if url.path == "/api/backups":
                return self.json(studio.backup_list())
            if url.path == "/api/themes":
                return self.json(studio.themes())
            if url.path == "/api/schemes":
                return self.json(studio.schemes())
            if url.path == "/api/sync":
                return self.json(adapters.probe(studio.live_dir, studio.targets))
            return self.error(404, "not found")
        except ValueError as e:
            return self.error(400, str(e))
        except Exception as e:  # noqa: BLE001 - answer instead of dropping the connection
            logging.exception("request failed")
            return self.error(500, f"{type(e).__name__}: {e}")

    def do_POST(self):
        # Other local pages must not drive Apply: cross-origin JSON needs a preflight this server
        # never answers, and a present Origin must be our own.
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if not self.headers.get("Content-Type", "").startswith("application/json") or (origin and urlparse(origin).netloc != host):
            return self.error(403, "same-origin JSON only")
        url = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        studio = self.studio
        try:
            if url.path == "/api/preview":
                return self.json(studio.preview(body))
            if url.path == "/api/themes/save":
                if not studio.allow_apply:
                    return self.error(403, "Saving themes is disabled; restart with --allow-apply")
                return self.json(studio.save_theme(body))
            if url.path == "/api/plan":
                studio.set_look(body.get("look"))
                return self.json(adapters.plan(studio, studio.permitted(body.get("targets"))))
            if url.path == "/api/apply":
                if not studio.allow_apply:
                    return self.error(403, "Apply is disabled; restart with --allow-apply")
                studio.set_look(body.get("look"))
                targets = studio.permitted(body.get("targets")) or adapters.DEFAULT_TARGETS
                entry, error = studio.begin_apply(targets)
                res = adapters.apply(studio, targets)
                res["history"], late = studio.finish_apply(entry, res["results"])
                res["historyError"] = error or late
                return self.json(res)
            return self.error(404, "not found")
        except (ValueError, AssertionError) as e:
            # The palette engine signals unusable images (e.g. too grey) with assertions.
            return self.error(400, str(e) or type(e).__name__)
        except Exception as e:  # noqa: BLE001 - report engine/template failures instead of dropping the connection
            logging.exception("request failed")
            return self.error(500, f"{type(e).__name__}: {e}")

    def palette_css(self):
        raw = contract.css(self.studio.palette()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/css; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def palette_events(self):
        """Server-sent events: one `revision` message now and on every live palette change."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        sent = None
        try:
            while True:
                revision = self.studio.palette()["revision"]
                if revision != sent:
                    self.wfile.write(f"data: {revision}\n\n".encode())
                    sent = revision
                else:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
                time.sleep(PALETTE_POLL)
        except (BrokenPipeError, ConnectionResetError):
            return

    def json(self, data, status=200, cors=False):
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def error(self, status, message):
        self.json({"error": message}, status)

    def file(self, path, mime=None, cache=False, cors=False):
        if not path.is_file():
            return self.error(404, "not found")
        raw = path.read_bytes()
        self.send_response(200)
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", mime or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Cache-Control", "private, max-age=3600" if cache else "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def theme_names(folder):
    return sorted(p.stem for p in Path(folder).glob("*.json")) if os.path.isdir(folder) else []


FINGERPRINTS = {}


def fingerprint(path):
    """Content identity for a wallpaper (sha256 of the whole file), stable across renames and copies; None if unreadable."""
    try:
        stat = os.stat(path)
        key = (os.path.realpath(path), stat.st_mtime_ns, stat.st_size)
        if key not in FINGERPRINTS:
            digest = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    digest.update(chunk)
            FINGERPRINTS[key] = "sha256:" + digest.hexdigest()
        return FINGERPRINTS[key]
    except OSError:
        return None


def band(data):
    colors = (data or {}).get("colors") or {}
    return [colors.get(f"color{i}") for i in range(8)]


def load_theme(theme, image):
    """A builtin or user theme as a draft for `image` (like `wal --theme NAME -i IMAGE`)."""
    name, bright = str(theme.get("name", "")), "light" if theme.get("light") else "dark"
    if not THEME_NAME.fullmatch(name):
        raise ValueError("unknown theme")
    root = CONF_DIR if theme.get("source") == "user" else MODULE_DIR
    data = read_json(os.path.join(root, "colorschemes", bright, name + ".json"))
    if not data or "colors" not in data or "special" not in data:
        raise ValueError(f"theme {name} not found")
    raw = dict(data["colors"])
    # Builtin themes carry only color0-15; this fork's templates read the named ANSI slots.
    for i, n in enumerate(ANSI_NAMES):
        raw.setdefault(n, raw[f"color{i}"])
        raw.setdefault(f"bright_{n}", raw[f"color{i + 8}"])
    raw["background"], raw["foreground"] = data["special"]["background"], data["special"]["foreground"]
    ARGS.light = bright == "light"
    # The fork's exporter derives surfaces, subsurfaces and delta diff colours the templates need.
    colors = palette.colors_to_dict({k: Color.from_hex(v) for k, v in raw.items() if isinstance(v, str) and v.startswith("#")}, image)
    colors["special"]["cursor"] = data["special"].get("cursor", colors["special"]["cursor"])
    colors["theme"] = {"source": theme.get("source", "builtin"), "name": name}
    return colors


def image_size(path):
    from PIL import Image  # colorthief dependency; reads only the header here

    try:
        with Image.open(path) as img:
            return list(img.size)
    except OSError:
        return None


def generation_defaults():
    defaults = vars(cli_parser.parse_args([]))
    return {k: defaults.get(k) for k in OPTIONS_TO_SAVE}


def apply_settings(settings):
    defaults = generation_defaults()
    for key in OPTIONS_TO_SAVE:
        value = settings.get(key, defaults[key])
        if key == "seed" and value not in (None, ""):
            # Seeds exceed JS number precision, so the browser sends them as strings.
            value = int(str(value))
        setattr(ARGS, key, None if value == "" else value)
    ARGS.no_cache = True


def apply_overrides(colors, overrides):
    """Pin individual slots after generation; `background`/`foreground` follow the CLI's --bg/--fg."""
    for key, value in overrides.items():
        if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
            continue
        if key in colors["special"]:
            colors["special"][key] = value
        if key in colors["colors"]:
            colors["colors"][key] = value
        if key == "background":
            colors["colors"]["color0"] = value
        if key == "foreground":
            colors["colors"]["color15"] = value
            colors["special"]["cursor"] = value
    return colors


def clean_look(look):
    blur = float(look.get("blur", DEFAULT_LOOK["blur"]))
    tint = float(look.get("tint", DEFAULT_LOOK["tint"]))
    dim = float(look.get("dim", DEFAULT_LOOK["dim"]))
    return {"blur": max(0.0, min(blur, 64.0)), "tint": max(0.0, min(tint, 1.0)), "dim": max(0.0, min(dim, 0.8))}


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def display(path):
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home + os.sep) else path


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)
