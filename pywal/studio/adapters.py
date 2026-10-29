"""Sync adapters: read-only probes of what each app shows now, a plan for Apply, and Apply itself.

Every adapter reports proof from the app's own readback where one exists (kitty remote control,
the written colors.json). Apps without a readback are reported as `sent`.
"""

import json
import os
import shutil
import subprocess
import time
from glob import glob
from pathlib import Path

HOME = os.path.expanduser("~")
ES_PORT_FILE = os.path.join(HOME, "Library/Application Support/Editspace/loopback-port")
# es-desktop records the palette it now shows here (es-appearance-receipt/1); keyless, local, read-only.
ES_RECEIPT = os.environ.get("PYWAL_STUDIO_ES_RECEIPT") or os.path.join(HOME, "Library/Application Support/Editspace/appearance-receipt.json")
# es-desktop polls colors.json every 0.5s and debounces 0.3s.
ES_RECEIPT_WAIT = float(os.environ.get("PYWAL_STUDIO_ES_WAIT", "5"))
PYWALFOX_MANIFESTS = [
    os.path.join(HOME, "Library/Application Support/Mozilla/NativeMessagingHosts/pywalfox.json"),
    os.path.join(HOME, ".mozilla/native-messaging-hosts/pywalfox.json"),
]

# Order is the Apply order: files first, because every other app reads them.
TARGETS = {
    "files": "Theme files (colors.json + templates: opencode, nvim, tmux, delta, jjui, hyprland, waybar)",
    "kitty": "kitty: colors, background tint and blurred wallpaper in every window",
    "es-desktop": "Editspace app: follows colors.json on its own",
    "pywalfox": "Firefox via pywalfox",
    "tmux": "tmux: re-source config",
    "system-wallpaper": "System wallpaper",
}
DEFAULT_TARGETS = ["files", "kitty", "es-desktop", "pywalfox", "tmux"]


def probe(live_dir, permitted=None):
    probes = {
        "files": lambda: probe_files(live_dir),
        "kitty": probe_kitty,
        "es-desktop": probe_es,
        "pywalfox": probe_pywalfox,
        "tmux": probe_tmux,
        "system-wallpaper": lambda: {"available": True, "default": False,
                                     "detail": "Off by default: on macOS pywal rewrites the wallpaper store and restarts WallpaperAgent."},
    }
    live = read_json(os.path.join(live_dir, "colors.json")) or {}
    return {
        "live": {
            "background": live.get("special", {}).get("background"),
            "wallpaper": live.get("wallpaper"),
            "mtime": mtime(os.path.join(live_dir, "colors.json")),
        },
        # Targets outside this instance's --targets are not even probed.
        "targets": [{"id": t, "label": TARGETS[t], **fn()} for t, fn in probes.items() if not permitted or t in permitted],
    }


def plan(studio, targets):
    draft = require_draft(studio)
    targets = targets or DEFAULT_TARGETS
    steps = []
    look = draft.get("studio", {})
    for target in targets:
        if target == "files":
            names = sorted(n for n in os.listdir(studio.preview_dir) if os.path.isfile(os.path.join(studio.preview_dir, n)))
            steps.append({"target": target, "writes": [f"{studio.live_dir}/{n}" for n in names] + [f"{studio.live_dir}/wal", f"{studio.live_dir}/wallpaper"],
                          "backup": f"{studio.backups}/<time>/"})
        if target == "kitty":
            steps.append({"target": target, "writes": [f"{studio.live_dir}/blurred/<wallpaper>-s{look.get('blur', 16):g}-<key>", f"{studio.live_dir}/wallpaper.blurred -> that file"],
                          "runs": [f"kitty @ --to {s} set-colors --all --configured colors-kitty.conf background_tint={look.get('tint', 0.95):g}" for s in kitty_sockets()]
                          + [f"kitty @ --to {s} set-background-image --all --configured wallpaper.blurred" for s in kitty_sockets()]})
        if target == "es-desktop":
            steps.append({"target": target, "runs": [], "note": f"No command: the app polls colors.json; proof = {display(ES_RECEIPT)}"})
        if target == "pywalfox":
            steps.append({"target": target, "runs": ["pywalfox update"]})
        if target == "tmux":
            steps.append({"target": target, "runs": [f"tmux source-file {HOME}/.config/tmux/tmux.conf"]})
        if target == "system-wallpaper":
            steps.append({"target": target, "runs": [f"pywal.wallpaper.change({draft['wallpaper']})"]})
    return {"background": draft["special"]["background"], "wallpaper": draft["wallpaper"], "steps": steps}


def apply(studio, targets):
    draft = require_draft(studio)
    targets = targets or DEFAULT_TARGETS
    results = []
    for target in targets:
        handler = APPLY.get(target)
        if not handler:
            results.append({"target": target, "status": "unknown"})
            continue
        try:
            results.append({"target": target, **handler(studio, draft)})
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            results.append({"target": target, "status": "failed", "detail": str(e)})
    return {"results": results, "probe": probe(studio.live_dir)}


def apply_files(studio, draft):
    live = studio.live_dir
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = next(p for p in (os.path.join(studio.backups, stamp + (f"-{i}" if i else "")) for i in range(100)) if not os.path.exists(p))
    os.makedirs(backup)
    names = [n for n in os.listdir(studio.preview_dir) if os.path.isfile(os.path.join(studio.preview_dir, n))]
    for name in names + ["wal"]:
        if os.path.isfile(os.path.join(live, name)):
            shutil.copy2(os.path.join(live, name), os.path.join(backup, name))
    for name in names:
        shutil.copy2(os.path.join(studio.preview_dir, name), os.path.join(live, name))
    Path(live, "wal").write_text(draft["wallpaper"])
    link(draft["wallpaper"], os.path.join(live, "wallpaper"))
    written = read_json(os.path.join(live, "colors.json")) or {}
    ok = written.get("special", {}).get("background") == draft["special"]["background"]
    return {"status": "verified" if ok else "mismatch", "detail": f"{len(names)} files; backup {backup}"}


def apply_kitty(studio, draft):
    sockets = kitty_sockets()
    if not sockets:
        return {"status": "skipped", "detail": "no kitty remote-control sockets"}
    look = draft.get("studio", {})
    # kitty loads wallpaper.blurred again on every launch, so the file must live in the live cache, not scratch.
    rendered = studio.blurred(draft["wallpaper"], float(look.get("blur", 16)))
    blurred = os.path.join(studio.live_dir, "blurred", os.path.basename(rendered))
    os.makedirs(os.path.dirname(blurred), exist_ok=True)
    if not os.path.isfile(blurred):
        shutil.copy2(rendered, blurred)
    link(blurred, os.path.join(studio.live_dir, "wallpaper.blurred"))
    conf = os.path.join(studio.live_dir, "colors-kitty.conf")
    for sock in sockets:
        kitty(sock, "set-colors", "--all", "--configured", conf, f"background_tint={look.get('tint', 0.95):g}")
        kitty(sock, "set-background-image", "--all", "--configured", os.path.join(studio.live_dir, "wallpaper.blurred"))
    seen = probe_kitty()
    ok = all(w.get("background") == draft["special"]["background"] for w in seen.get("windows", []))
    return {"status": "verified" if ok and seen.get("windows") else "mismatch", "detail": seen.get("detail")}


def apply_es(studio, draft):
    seen = probe_es()
    if not seen.get("available"):
        return {"status": "skipped", "detail": seen.get("detail")}
    if not os.path.isfile(ES_RECEIPT):
        return {"status": "sent", "detail": "follows colors.json; this es-desktop build writes no appearance receipt"}
    want = draft["special"]["background"].lower()
    # The wal-palette revision Apply just wrote; app pages report the revision they render.
    revision = (read_json(os.path.join(studio.live_dir, "palette.json")) or {}).get("revision")
    deadline = time.monotonic() + ES_RECEIPT_WAIT
    while True:
        receipt = read_json(ES_RECEIPT) or {}
        shown = str(receipt.get("background", "")).lower()
        tabs = [a for a in receipt.get("applied") or [] if isinstance(a, dict) and revision and a.get("walRevision") == revision]
        if shown == want and tabs:
            return {"status": "verified", "detail": f"{len(tabs)} host tab(s) render wal revision {revision}"}
        if time.monotonic() > deadline:
            if shown == want:
                # `loaded` = the app process holds the palette, but no open page acknowledged rendering it.
                return {"status": "loaded", "detail": f"app loaded background {shown}; no page acknowledged revision {revision}"}
            return {"status": "mismatch", "detail": f"app still shows {shown or '?'} after {ES_RECEIPT_WAIT:g}s"}
        time.sleep(0.2)


def apply_pywalfox(studio, draft):
    if not shutil.which("pywalfox"):
        return {"status": "skipped", "detail": "pywalfox not installed"}
    out = subprocess.run(["pywalfox", "update"], capture_output=True, text=True, timeout=20)
    return {"status": "sent" if out.returncode == 0 else "failed", "detail": (out.stderr or out.stdout).strip()[-300:] or "no readback; check Firefox"}


def apply_tmux(studio, draft):
    if not shutil.which("tmux") or subprocess.run(["tmux", "has-session"], capture_output=True).returncode != 0:
        return {"status": "skipped", "detail": "no tmux server"}
    out = subprocess.run(["tmux", "source-file", os.path.join(HOME, ".config/tmux/tmux.conf")], capture_output=True, text=True, timeout=20)
    return {"status": "sent" if out.returncode == 0 else "failed", "detail": out.stderr.strip()[-300:]}


def apply_system_wallpaper(studio, draft):
    from .. import wallpaper

    wallpaper.change(draft["wallpaper"])
    return {"status": "sent", "detail": draft["wallpaper"]}


APPLY = {
    "files": apply_files,
    "kitty": apply_kitty,
    "es-desktop": apply_es,
    "pywalfox": apply_pywalfox,
    "tmux": apply_tmux,
    "system-wallpaper": apply_system_wallpaper,
}


def probe_files(live_dir):
    opencode = os.path.realpath(os.path.join(HOME, ".config/opencode/themes/pywal.json"))
    return {"available": os.path.isdir(live_dir), "default": True,
            "detail": f"opencode theme -> {display(opencode)}" if os.path.exists(opencode) else "opencode pywal theme link absent"}


def probe_kitty():
    sockets = kitty_sockets()
    if not shutil.which("kitty"):
        return {"available": False, "default": False, "detail": "kitty not installed"}
    windows = []
    for sock in sockets:
        out = kitty(sock, "get-colors")
        colors = dict(line.split(None, 1) for line in out.stdout.splitlines() if len(line.split(None, 1)) == 2)
        windows.append({"socket": sock, "background": colors.get("background"), "foreground": colors.get("foreground")})
    return {"available": bool(sockets), "default": True, "windows": windows,
            "detail": f"{len(sockets)} instance(s): " + ", ".join(w["background"] or "?" for w in windows) if sockets else "no remote-control sockets in /tmp"}


def probe_es():
    running = os.path.isfile(ES_PORT_FILE) and subprocess.run(["pgrep", "-x", "Editspace"], capture_output=True).returncode == 0
    receipt = read_json(ES_RECEIPT) if running or os.environ.get("PYWAL_STUDIO_ES_RECEIPT") else None
    if receipt:
        return {"available": True, "default": True, "detail": f"shows background {receipt.get('background')} (appearance receipt)"}
    return {"available": running, "default": running,
            "detail": "running; reads colors.json itself (no receipt in this build)" if running else "Editspace app not running"}


def probe_pywalfox():
    installed = bool(shutil.which("pywalfox"))
    manifest = any(os.path.isfile(m) for m in PYWALFOX_MANIFESTS)
    return {"available": installed and manifest, "default": installed and manifest,
            "detail": "installed; no readback (extension reads colors.json on update)" if installed and manifest else "pywalfox or its Firefox native host is missing"}


def probe_tmux():
    up = bool(shutil.which("tmux")) and subprocess.run(["tmux", "has-session"], capture_output=True).returncode == 0
    return {"available": up, "default": up, "detail": "server running" if up else "no tmux server"}


def kitty_sockets():
    return sorted(f"unix:{p}" for p in glob("/tmp/kitty-*.sock"))


def kitty(sock, *args):
    return subprocess.run(["kitty", "@", "--to", sock, *args], capture_output=True, text=True, timeout=10)


def link(target, path):
    if os.path.lexists(path):
        os.remove(path)
    os.symlink(target, path)


def require_draft(studio):
    if not studio.last:
        raise ValueError("Generate a preview first")
    return studio.last


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def display(path):
    return "~" + path[len(HOME):] if path.startswith(HOME + os.sep) else path

