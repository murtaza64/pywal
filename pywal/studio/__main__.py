"""Run Palette Studio: uv run -m pywal.studio [--port N]."""

import argparse
import os
import tempfile


def main():
    parser = argparse.ArgumentParser(prog="pywal.studio", description="Local palette studio")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address. Keep loopback: palettes and wallpapers stay private.")
    parser.add_argument("--port", type=int, default=4790)
    parser.add_argument(
        "--live-dir",
        default=os.environ.get("PYWAL_CACHE_DIR") or os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "wal"),
        help="The live pywal cache that apps read (default ~/.cache/wal). Read for the original; written only by Apply.",
    )
    parser.add_argument("--wallpapers", default=os.path.expanduser("~/wallpapers"))
    parser.add_argument("--scratch", default=os.path.join(tempfile.gettempdir(), f"pywal-studio-{os.getuid()}"))
    parser.add_argument(
        "--backups",
        default=os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "pywal-studio", "backups"),
        help="Where Apply keeps copies of the live files it replaces (survives reboots, unlike scratch).",
    )
    parser.add_argument(
        "--allow-apply",
        action="store_true",
        help="Enable Apply. Without it the studio is preview-only and never touches the live theme.",
    )
    parser.add_argument(
        "--targets",
        help="Comma-separated sync targets this instance may plan or apply (e.g. files,es-desktop). Others are refused by the server. Default: all.",
    )
    args = parser.parse_args()

    # Every pywal module resolves its cache through PYWAL_CACHE_DIR at call time; pointing it at
    # scratch before import keeps generation and template export away from the live cache.
    preview_dir = os.path.join(args.scratch, "preview")
    os.makedirs(preview_dir, exist_ok=True)
    os.environ["PYWAL_CACHE_DIR"] = preview_dir

    from .server import serve

    serve(
        host=args.host,
        port=args.port,
        live_dir=os.path.abspath(os.path.expanduser(args.live_dir)),
        wallpapers=os.path.abspath(os.path.expanduser(args.wallpapers)),
        scratch=os.path.abspath(args.scratch),
        backups=os.path.abspath(os.path.expanduser(args.backups)),
        allow_apply=args.allow_apply,
        targets=[t.strip() for t in args.targets.split(",") if t.strip()] if args.targets else None,
    )


if __name__ == "__main__":
    main()
