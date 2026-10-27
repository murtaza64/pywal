"""wal-palette/1: the shared palette contract for agent artifacts and app surfaces.

Built from the fork's colors.json at export time (every `wal` run and Palette Studio Apply),
written next to it as `palette.json` + `palette.css`. Consumers read those cached files; they
never parse colors.json per token. Stdlib only, so the same file runs as a standalone helper on
hosts without pywal installed:

    wal-palette css|json|snapshot          (or: python3 path/to/contract.py ...)
    wal-palette inject FILE.html|FILE.svg  # embed the current palette, idempotent
    wal-palette build [--colors colors.json] [--out DIR]

Semantic roles come from the fork's hue-matched ANSI names (red, green, ...), never from raw
`colorN`, which is generation order. Raw order feeds the non-semantic highlights `hl1..hl8`:
hl1..hl4 take the first four well-separated hues in generation order and sit on a lightness
ladder chosen so they stay tellable apart under every simulated colour-vision deficiency;
hl5..hl8 are the next raw colours, readable but without that guarantee.
The contract carries colours only: no wallpaper path, nothing that reads as an instruction.
"""

import hashlib
import itertools
import json
import math
import os
import re
import sys

SCHEMA = "wal-palette/1"
# Bump when derivation rules change so cached palette.json files are rebuilt.
BUILD = 2
CACHE = os.environ.get("PYWAL_CACHE_DIR") or os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "wal")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Role -> meaning. Text roles hold 4.5:1 against `surface` (fg 7:1); graphic roles 3:1.
ROLES = {
    "bg": "page background",
    "surface": "panels, cards, the default drawing ground",
    "raised": "fields, hover, selected rows",
    "line": "rules, strokes, chart axes (3:1 on surface)",
    "fg": "body text (7:1 on surface)",
    "muted": "secondary text (4.5:1)",
    "faint": "tertiary marks, gridlines (3:1)",
    "accent": "links, focus, primary action (4.5:1)",
    "on_accent": "text drawn on an accent fill",
    "ok": "success / done (4.5:1)",
    "warn": "attention / pending (4.5:1)",
    "risk": "failure / danger (4.5:1, distinguishable from ok under colour-vision deficiency)",
    "info": "neutral notice (4.5:1)",
    **{f"hl{i}_bg": f"text-highlight fill for hl{i} (fg keeps 7:1; falls back to surface)" for i in range(1, 5)},
}
HIGHLIGHTS = 8
# OKLab distance under simulated deuteranopia/protanopia that keeps ok and risk tellable apart.
CVD_MINIMUM = 0.12
# OKLab distance every pair of hl1..hl4 keeps under normal vision and each simulated deficiency.
HL_DISTINCT = 0.10
HL_DISTINCT_COUNT = 4

# Used when no palette has been generated on this host yet (and by tests): manadj-like dark.
DEFAULT_COLORS = {
    "special": {"background": "#121214", "foreground": "#d6dbe6", "cursor": "#d6dbe6"},
    "colors": {
        **{f"surface{i}": c for i, c in enumerate(["#18181b", "#1e1e22", "#26262b", "#34343a", "#45454c", "#5a5a62"])},
        "black": "#121214", "red": "#e5484d", "green": "#30a46c", "yellow": "#f5a524", "blue": "#3e8ef7",
        "magenta": "#a463f2", "cyan": "#12a5b8", "white": "#c9ced8",
        "bright_black": "#5a5a62", "bright_red": "#ff6b70", "bright_green": "#3dd68c", "bright_yellow": "#ffcc4d",
        "bright_blue": "#6aa8ff", "bright_magenta": "#c08cff", "bright_cyan": "#3fd0e0", "bright_white": "#eef1f6",
        **{f"color{i}": c for i, c in enumerate(["#3e8ef7", "#30a46c", "#f5a524", "#a463f2", "#12a5b8", "#e5484d", "#ff8a3d", "#d6dbe6",
                                                   "#6aa8ff", "#3dd68c", "#ffcc4d", "#c08cff", "#3fd0e0", "#ff6b70", "#ffa86b", "#eef1f6"])},
    },
}


def build(colors_json):
    """Contract dict from a colors.json dict (the fork's export format)."""
    special, c = colors_json["special"], colors_json["colors"]
    pick = lambda *keys: next((c[k] for k in keys if HEX.match(str(c.get(k, "")))), None)
    bg = special["background"]
    light = luminance(bg) > 0.4
    surface = pick("surface1", "surface0") or mix(bg, special["foreground"], 0.05)
    raised = pick("surface2") or mix(bg, special["foreground"], 0.12)
    fg = readable(special["foreground"], surface, 7)
    vivid = max((pick(f"bright_{n}", n) for n in ("blue", "cyan", "magenta")), key=chroma)
    roles = {
        "bg": bg,
        "surface": surface,
        "raised": raised,
        "line": readable(pick("surface3") or mix(surface, fg, 0.2), surface, 3),
        "fg": fg,
        "muted": readable(mix(surface, fg, 0.72), surface, 4.5),
        "faint": readable(mix(surface, fg, 0.45), surface, 3),
        "accent": readable(vivid, surface, 4.5),
        "ok": readable(pick("bright_green", "green"), surface, 4.5),
        "warn": readable(pick("bright_yellow", "yellow"), surface, 4.5),
        "risk": readable(pick("bright_red", "red"), surface, 4.5),
        "info": readable(pick("bright_cyan", "cyan"), surface, 4.5),
    }
    roles["on_accent"] = max([bg, "#000000", "#ffffff"], key=lambda ink: contrast(ink, roles["accent"]))
    roles["ok"], roles["risk"] = separate(roles["ok"], roles["risk"], surface)
    raw = [pick(f"color{i}") or vivid for i in range(HIGHLIGHTS)]
    distinct = distinct_highlights(raw, surface)
    rest = [readable(h, surface, 3) for h in raw if h not in distinct["sources"]]
    highlights = (distinct["colors"] + rest + [readable(h, surface, 3) for h in raw])[:HIGHLIGHTS]
    for i, h in enumerate(highlights[:4], 1):
        roles[f"hl{i}_bg"] = tint_keeping_text(h, surface, fg)
    body = {"scheme": "light" if light else "dark", "roles": roles, "highlights": highlights}
    return {
        "schema": SCHEMA,
        "build": BUILD,
        "revision": hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()[:12],
        **body,
        "terminal": {k: c[k] for k in [*ANSI, *(f"bright_{n}" for n in ANSI)] if HEX.match(str(c.get(k, "")))},
        "checks": checks(roles, highlights),
    }


ANSI = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]


def css(contract):
    """`:root` custom properties: namespaced `--wal-*` plus the bare role names briefs already use."""
    r = contract["roles"]
    props = [f"--wal-{k.replace('_', '-')}:{v}" for k, v in r.items()]
    props += [f"--wal-hl{i + 1}:{v}" for i, v in enumerate(contract["highlights"])]
    props += [f"--{k.replace('_', '-')}:var(--wal-{k.replace('_', '-')})" for k in r]
    props += [f"--hl{i + 1}:var(--wal-hl{i + 1})" for i in range(len(contract["highlights"]))]
    # Present only when true, so `var(--wal-ok-risk-cvd-safe, 0)`-style feature tests stay simple.
    props += [f"--wal-{k.replace('_', '-')}:1" for k in ("ok_risk_cvd_safe", "hl_distinct_safe") if contract["checks"].get(k)]
    head = f"/* {contract['schema']} rev {contract['revision']} */"
    return f"{head}\n:root{{color-scheme:{contract['scheme']};--wal-revision:\"{contract['revision']}\";{';'.join(props)}}}\n"


def write(colors_json, out_dir):
    contract = build(colors_json)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "palette.json"), "w") as f:
        json.dump(contract, f, indent=2)
    with open(os.path.join(out_dir, "palette.css"), "w") as f:
        f.write(css(contract))
    return contract


def current(cache=CACHE, persist=True):
    """The cached contract; rebuilt only when colors.json is newer (one stat per call).

    `persist=False` rebuilds in memory without writing into the cache (read-only services)."""
    path, source = os.path.join(cache, "palette.json"), os.path.join(cache, "colors.json")
    stale = os.path.isfile(source) and (not os.path.isfile(path) or os.path.getmtime(path) < os.path.getmtime(source) or cached_build(path) != BUILD)
    if stale:
        with open(source) as f:
            data = json.load(f)
        return write(data, cache) if persist else build(data)
    if os.path.isfile(path):
        # Hosts that only receive palette metadata (no colors.json) still have a contract.
        with open(path) as f:
            return json.load(f)
    return build(DEFAULT_COLORS)


def cached_build(path):
    try:
        with open(path) as f:
            return json.load(f).get("build")
    except (OSError, ValueError):
        return None


def inject(text, contract, svg=False):
    """Embed the palette as one `<style id="wal-palette">` block; replaces an earlier one."""
    block = f'<style id="wal-palette" data-wal-revision="{contract["revision"]}">{css(contract)}</style>'
    if svg:
        block = block.replace(":root{", ":root,svg{", 1)
    existing = re.compile(r'<style id="wal-palette"[^>]*>.*?</style>', re.S)
    if existing.search(text):
        return existing.sub(lambda _: block, text, count=1)
    anchor = re.search(r"<head[^>]*>", text, re.I) or (re.search(r"<svg[^>]*>", text, re.I) if svg else None)
    if anchor:
        return text[: anchor.end()] + block + text[anchor.end():]
    return block + text


def checks(roles, highlights):
    s = roles["surface"]
    text = {k: round(contrast(roles[k], s), 2) for k in ("fg", "muted", "accent", "ok", "warn", "risk", "info")}
    distinct = highlights[:HL_DISTINCT_COUNT]
    graphic = {k: round(contrast(roles[k], s), 2) for k in ("line", "faint")}
    return {
        "text_min": min(text.values()),
        "graphic_min": min([*graphic.values(), *(contrast(h, s) for h in highlights)]),
        "ok_risk_cvd": round(cvd_distance(roles["ok"], roles["risk"]), 3),
        # False only when no readable pair separates; consumers then keep their own ok/risk defaults.
        "ok_risk_cvd_safe": cvd_distance(roles["ok"], roles["risk"]) >= CVD_MINIMUM,
        "hl_distinct": round(min(any_vision_distance(a, b) for i, a in enumerate(distinct) for b in distinct[i + 1:]), 3),
        # False only on mid-grey surfaces with too little lightness room (2 of 271 builtin themes).
        "hl_distinct_safe": min(any_vision_distance(a, b) for i, a in enumerate(distinct) for b in distinct[i + 1:]) >= HL_DISTINCT,
        "hl_bg_fg_min": round(min(contrast(roles["fg"], roles[f"hl{i}_bg"]) for i in range(1, 5)), 2),
    }


def separate(ok, risk, surface, minimum=None):
    """Keep ok and risk apart under red-green deficiency, changing as little as possible.

    Lightness survives colour-vision deficiency, so candidates move ok and/or risk toward white
    or black; the smallest combined move that keeps both readable wins. Without one, fall back
    to a fixed pair that is far apart in lightness and hue.
    """
    minimum = CVD_MINIMUM if minimum is None else minimum
    steps = [i / 20 for i in range(13)]
    candidates = [
        (a + b, mix(ok, t_ok, a), mix(risk, t_risk, b))
        for t_ok in ("#ffffff", "#000000") for t_risk in ("#ffffff", "#000000") for a in steps for b in steps
    ]
    for _, o, r in sorted(candidates, key=lambda c: c[0]):
        if cvd_distance(o, r) >= minimum and contrast(o, surface) >= 4.5 and contrast(r, surface) >= 4.5:
            return o, r
    # Teal against red keeps a blue-yellow difference that red-green deficiencies preserve.
    pairs = [("#7ee8c0", "#ff5a5f"), ("#0f9f6e", "#c0263f"), ("#00808a", "#c0263f"), ("#1b6fd0", "#c0263f"), ("#5ad1ff", "#ff5a5f")]
    fixed = [(readable(o, surface, 4.5), readable(r, surface, 4.5)) for o, r in pairs]
    return max(fixed, key=lambda pair: cvd_distance(*pair))


def distinct_highlights(raw, surface):
    """hl1..hl4: generation-order hues on a CVD-safe lightness ladder.

    Hues: the first raw colours (generation order) at least 50 degrees apart with some chroma,
    topped up from the remaining raw colours, then the manadj deck hues. Lightness: four rungs
    0.11 apart, the outermost at the first L reaching 3.5:1 on surface. Protanopia darkens reds,
    so every hue -> rung assignment (at two chroma levels) is tried and the one whose closest pair is farthest apart
    (normal, protan, deutan, tritan) wins; hl order stays generation order.
    """
    hues, sources = [], []
    for strict in (True, False):
        for h in raw:
            L, C, H = oklch(h)
            if len(hues) < HL_DISTINCT_COUNT and h not in sources and (not strict or C >= 0.04) and all(hue_gap(H, x) >= (50 if strict else 30) for x in hues):
                hues.append(H)
                sources.append(h)
    for H in (205.0, 0.0, 50.0, 295.0):  # cyan, pink, orange, violet
        if len(hues) < HL_DISTINCT_COUNT and all(hue_gap(H, x) >= 30 for x in hues):
            hues.append(H)
    rungs = ladder(surface)
    best, best_score = None, -1.0
    # Mid-grey surfaces leave little lightness room; more chroma lets hue carry the difference there.
    for chroma_, order in itertools.product((0.15, 0.22), itertools.permutations(range(HL_DISTINCT_COUNT))):
        colours = [oklch_to_hex(rungs[order[i]], chroma_, hues[i]) for i in range(HL_DISTINCT_COUNT)]
        score = min(any_vision_distance(a, b) for i, a in enumerate(colours) for b in colours[i + 1:])
        if score > best_score + 1e-9:
            best, best_score = colours, score
    return {"colors": best, "sources": sources}


def ladder(surface):
    """Four lightness rungs from the surface outward; caps keep chroma (near-white/black read grey)."""
    dark = luminance(surface) < 0.4
    edge = next((L for L in ((i / 100) if dark else (1 - i / 100) for i in range(101))
                 if contrast(oklch_to_hex(L, 0, 0), surface) >= 3.5), 1.0 if dark else 0.0)
    step = min(0.11, ((0.92 - edge) if dark else (edge - 0.18)) / 3)
    return [edge + k * step if dark else edge - k * step for k in (3, 2, 1, 0)]


def tint_keeping_text(highlight, surface, fg):
    for k in range(13, -1, -1):  # 0.30 .. 0.04 of the highlight over the surface
        fill = mix(surface, highlight, 0.04 + k * 0.02)
        if contrast(fg, fill) >= 7:
            return fill
    return surface


def hue_gap(a, b):
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


# --- colour math (sRGB, WCAG contrast, OKLab, Machado 2009 deuteranopia/protanopia) ---

def channels(hex_):
    return [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def to_hex(rgb):
    return "#" + "".join(f"{round(max(0, min(1, v)) * 255):02x}" for v in rgb)


def mix(a, b, t):
    return to_hex([x + (y - x) * t for x, y in zip(channels(a), channels(b))])


def linear(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(hex_):
    r, g, b = (linear(v) for v in channels(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    hi, lo = sorted([luminance(a), luminance(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def readable(color, background, target):
    """Move `color` away from the background's lightness until it reaches `target` contrast."""
    toward = "#ffffff" if luminance(background) < 0.4 else "#000000"
    for step in range(21):
        candidate = mix(color, toward, step / 20)
        if contrast(candidate, background) >= target:
            return candidate
    return toward


def oklab(rgb_linear):
    r, g, b = rgb_linear
    l, m, s = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b, 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
               0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    l, m, s = (max(v, 0) ** (1 / 3) for v in (l, m, s))
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def oklch(hex_):
    L, a, b = oklab([linear(v) for v in channels(hex_)])
    return L, (a * a + b * b) ** 0.5, math.degrees(math.atan2(b, a)) % 360


def oklch_to_hex(L, C, H):
    """OKLCH -> sRGB hex; chroma steps down until the colour fits the gamut."""
    h = math.radians(H)
    for _ in range(24):
        a, b = C * math.cos(h), C * math.sin(h)
        l, m, s = ((L + 0.3963377774 * a + 0.2158037573 * b) ** 3, (L - 0.1055613458 * a - 0.0638541728 * b) ** 3,
                   (L - 0.0894841775 * a - 1.2914855480 * b) ** 3)
        rgb = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
               -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
        if all(-0.0005 <= v <= 1.0005 for v in rgb):
            return to_hex([12.92 * v if v <= 0.0031308 else 1.055 * max(v, 0) ** (1 / 2.4) - 0.055 for v in rgb])
        C *= 0.9
    return to_hex([L, L, L])


def chroma(hex_):
    _, a, b = oklab([linear(v) for v in channels(hex_)])
    return (a * a + b * b) ** 0.5


CVD = {
    "deuteranopia": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "protanopia": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
}


TRITANOPIA = ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900))


def any_vision_distance(a, b):
    """Smallest OKLab distance across normal vision and simulated protan/deutan/tritan deficiency."""
    def sim(hex_, m):
        rgb = [linear(v) for v in channels(hex_)]
        return oklab(rgb if m is None else [max(0, min(1, sum(m[i][j] * rgb[j] for j in range(3)))) for i in range(3)])
    return min(sum((x - y) ** 2 for x, y in zip(sim(a, m), sim(b, m))) ** 0.5 for m in (None, *CVD.values(), TRITANOPIA))


def cvd_distance(a, b):
    """Smallest OKLab distance between two colours across simulated red-green deficiencies."""
    def sim(hex_, m):
        rgb = [linear(v) for v in channels(hex_)]
        return oklab([max(0, min(1, sum(m[i][j] * rgb[j] for j in range(3)))) for i in range(3)])
    return min(sum((x - y) ** 2 for x, y in zip(sim(a, m), sim(b, m))) ** 0.5 for m in CVD.values())


def main(argv):
    cmd = argv[0] if argv else "css"
    if cmd == "build":
        colors = argv[argv.index("--colors") + 1] if "--colors" in argv else os.path.join(CACHE, "colors.json")
        out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.dirname(colors)
        with open(colors) as f:
            print(json.dumps(write(json.load(f), out)["checks"]))
        return 0
    contract = current()
    if cmd == "css":
        sys.stdout.write(css(contract))
    elif cmd == "json":
        print(json.dumps(contract, indent=2))
    elif cmd == "snapshot":
        # For fixed exports (PNG/PDF): record exactly which palette was used.
        print(json.dumps({"schema": contract["schema"], "revision": contract["revision"], "scheme": contract["scheme"],
                          "roles": contract["roles"], "highlights": contract["highlights"]}, separators=(",", ":")))
    elif cmd == "inject":
        path = argv[1]
        with open(path) as f:
            text = f.read()
        with open(path, "w") as f:
            f.write(inject(text, contract, svg=path.endswith(".svg")))
        print(f"{path}: {contract['schema']} rev {contract['revision']}")
    else:
        print(__doc__)
        return 2
    return 0


def cli():
    """Console entry point: `wal-palette`."""
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    cli()
