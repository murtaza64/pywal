#!/usr/bin/env -S uv run --script

"""Interactive yellow-zone tuner (OKLCH hue x chroma).

Uses curses for stable rendering (no ANSI escapes inside the grid).

Controls:
  q            quit
  left/right   hue center -/+ 2deg
  [ / ]        hue span  -/+ 5deg
  - / =        hue step  -/+ 1deg

  up/down      lightness L -/+ 0.02
  j / k        chroma min -/+ 0.01
  u / i        chroma max -/+ 0.01
  , / .        chroma step -/+ 0.005

  m            mode: base -> huepen -> huepen+yellow-gate
  1 / 2        hue penalty k -/+ 0.05 (radians weight)
  3 / 4        yellow min L -/+ 0.02
  5 / 6        yellow min C -/+ 0.01

Legend in cells: chosen target letter (R/Y/G/C/B/M)
"""

from __future__ import annotations

import curses
import math

from pywal import match
from pywal import oklab
from pywal.color import Color


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _circle_dist_rad(a: float, b: float) -> float:
    d = abs(a - b) % (2.0 * math.pi)
    return min(d, 2.0 * math.pi - d)


def _oklab_dist(a: oklab.OKLab, b: oklab.OKLab) -> float:
    return ((a.L - b.L) ** 2 + (a.a - b.a) ** 2 + (a.b - b.b) ** 2) ** 0.5


def _target_tag(name: str) -> str:
    return {
        "red": "R",
        "yellow": "Y",
        "green": "G",
        "cyan": "C",
        "blue": "B",
        "magenta": "M",
    }[name]


def _hdeg_rad(h_rad: float) -> float:
    return (h_rad * 180.0 / math.pi) % 360.0


def _hdeg(c: Color) -> float:
    return _hdeg_rad(float(c.oklch.h_rad))


def _nearest_target_by_oklch_hue(c: Color) -> str:
    h = float(c.oklch.h_rad)
    return min(match.TARGET_OKLCH_HUE_RAD, key=lambda t: _circle_dist_rad(h, match.TARGET_OKLCH_HUE_RAD[t]))


def _score_hue_penalty(c: Color, target: str, k: float) -> float:
    d_lab = _oklab_dist(c.oklab, match.TARGET_OKLAB[target])
    d_h = _circle_dist_rad(float(c.oklch.h_rad), match.TARGET_OKLCH_HUE_RAD[target])
    return d_lab + k * d_h


def classify(c: Color, *, mode: str, k: float, yellow_min_L: float, yellow_min_C: float) -> str:
    if mode == "base":
        return match.get_closest_target(c)
    if mode == "huepen":
        return min(match.TARGET_OKLAB.keys(), key=lambda t: _score_hue_penalty(c, t, k))
    if mode == "huepen+gate":
        def score(t: str) -> float:
            if t == "yellow":
                if c.oklch.L < yellow_min_L or c.oklch.C < yellow_min_C:
                    return float("inf")
            return _score_hue_penalty(c, t, k)

        return min(match.TARGET_OKLAB.keys(), key=score)
    raise ValueError(f"unknown mode: {mode}")


def _fg_for_bg(c: Color) -> tuple[int, int, int]:
    # Simple readable foreground based on luminance.
    return (0, 0, 0) if c.w3_luminance > 0.45 else (255, 255, 255)


def _rgb_to_xterm256(r: int, g: int, b: int) -> int:
    """Map RGB(0-255) to xterm-256 color index."""
    if r == g == b:
        if r < 8:
            return 16
        if r > 248:
            return 231
        return 232 + int(round((r - 8) / 10.0))

    def to_6(x: int) -> int:
        return int(round(x / 51.0))

    ri = _clamp(to_6(r), 0, 5)
    gi = _clamp(to_6(g), 0, 5)
    bi = _clamp(to_6(b), 0, 5)
    return 16 + 36 * int(ri) + 6 * int(gi) + int(bi)


class PairCache:
    def __init__(self) -> None:
        self._next = 1
        self._pairs: dict[tuple[int, int], int] = {}

    def pair(self, fg: int, bg: int) -> int:
        key = (fg, bg)
        pid = self._pairs.get(key)
        if pid is not None:
            return pid

        pid = self._next
        self._next += 1
        curses.init_pair(pid, fg, bg)
        self._pairs[key] = pid
        return pid


def _render(
    stdscr,
    cache: PairCache,
    *,
    hue_center_deg: float,
    hue_span_deg: float,
    hue_step_deg: float,
    L: float,
    c_min: float,
    c_max: float,
    c_step: float,
    mode: str,
    k: float,
    yellow_min_L: float,
    yellow_min_C: float,
) -> None:
    hue_center_deg = hue_center_deg % 360.0
    hue_span_deg = _clamp(hue_span_deg, 5.0, 180.0)
    hue_step_deg = _clamp(hue_step_deg, 1.0, 30.0)
    c_step = _clamp(c_step, 0.005, 0.08)
    c_min = _clamp(c_min, 0.0, 0.40)
    c_max = _clamp(c_max, 0.0, 0.40)
    if c_max < c_min:
        c_max, c_min = c_min, c_max

    yellow_h = _hdeg_rad(match.TARGET_OKLCH_HUE_RAD["yellow"])
    green_h = _hdeg_rad(match.TARGET_OKLCH_HUE_RAD["green"])
    red_h = _hdeg_rad(match.TARGET_OKLCH_HUE_RAD["red"])

    stdscr.erase()
    height, width = stdscr.getmaxyx()

    if width < 60 or height < 12:
        stdscr.addnstr(0, 0, f"terminal too small ({width}x{height})", width - 1)
        stdscr.addnstr(1, 0, "resize and try again", width - 1)
        stdscr.refresh()
        return

    stdscr.addnstr(0, 0, "Yellow Zone Tuner (OKLCH hue x chroma)", width - 1)

    line1 = (
        f"mode={mode}  L={L:.3f}  hue_center={hue_center_deg:.1f}deg  span={hue_span_deg:.1f}  step={hue_step_deg:.1f}  "
        f"C=[{c_min:.3f}..{c_max:.3f}] step={c_step:.3f}"
    )
    stdscr.addnstr(1, 0, line1, width - 1)

    line2 = (
        f"targets: red={red_h:.1f}deg yellow={yellow_h:.1f}deg green={green_h:.1f}deg  "
        f"k={k:.2f}  yellow_gate: L>={yellow_min_L:.2f} C>={yellow_min_C:.2f}"
    )
    stdscr.addnstr(2, 0, line2, width - 1)
    stdscr.addnstr(3, 0, "keys: arrows/[ ]/- =/j k/u i/, . /m/1..6/q", width - 1)

    # Header row: hue labels.
    h_start = hue_center_deg - hue_span_deg
    h_end = hue_center_deg + hue_span_deg
    hues: list[float] = []
    hd = h_start
    while hd <= h_end + 1e-9:
        hues.append(hd)
        hd += hue_step_deg

    # Chroma rows (high to low).
    chromas: list[float] = []
    c = c_min
    while c <= c_max + 1e-9:
        chromas.append(c)
        c += c_step
    chromas = list(reversed(chromas))

    # Layout.
    top = 5
    left = 8
    cell_w = 2
    max_cols = max(1, (width - left - 1) // cell_w)
    hues = hues[:max_cols]

    # Hue tick labels.
    y = top
    stdscr.addnstr(y, 0, "h(deg)", left - 1)
    for idx, hd in enumerate(hues):
        if idx % 4 == 0:
            label = f"{int(round(hd))%360:>3}"
            x = left + idx * cell_w
            if x + 3 < width:
                stdscr.addnstr(y, x, label, min(3, width - x - 1))
    y += 1

    yellow_count = 0
    total = 0
    for c in chromas:
        if y >= height - 2:
            break
        stdscr.addnstr(y, 0, f"C={c:0.3f}", left - 1)
        for idx, hd in enumerate(hues):
            hr = ((hd % 360.0) * math.pi / 180.0) % (2.0 * math.pi)
            col = Color.from_oklch(oklab.OKLCH(L=L, C=c, h_rad=hr))
            chosen = classify(col, mode=mode, k=k, yellow_min_L=yellow_min_L, yellow_min_C=yellow_min_C)
            tag = _target_tag(chosen)

            r, g, b = col.rgb8
            fr, fg, fb = _fg_for_bg(col)
            bg_idx = _rgb_to_xterm256(r, g, b)
            fg_idx = _rgb_to_xterm256(fr, fg, fb)
            pid = cache.pair(fg_idx, bg_idx)

            x = left + idx * cell_w
            if x + 1 < width:
                stdscr.addnstr(y, x, f"{tag} ", 2, curses.color_pair(pid))

            total += 1
            if chosen == "yellow":
                yellow_count += 1
        y += 1

    stdscr.addnstr(height - 1, 0, f"chosen==yellow: {yellow_count}/{total} cells", width - 1)
    stdscr.refresh()


def _loop(stdscr) -> int:
    hue_center_deg = _hdeg_rad(match.TARGET_OKLCH_HUE_RAD["yellow"])
    hue_span_deg = 70.0
    hue_step_deg = 5.0
    L = 0.78
    c_min = 0.00
    c_max = 0.24
    c_step = 0.02

    mode = "base"  # base | huepen | huepen+gate
    k = 0.35
    yellow_min_L = 0.55
    yellow_min_C = 0.06

    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)
    curses.start_color()
    try:
        curses.use_default_colors()
    except Exception:
        pass

    cache = PairCache()

    while True:
        _render(
            stdscr,
            cache,
            hue_center_deg=hue_center_deg,
            hue_span_deg=hue_span_deg,
            hue_step_deg=hue_step_deg,
            L=L,
            c_min=c_min,
            c_max=c_max,
            c_step=c_step,
            mode=mode,
            k=k,
            yellow_min_L=yellow_min_L,
            yellow_min_C=yellow_min_C,
        )

        ch = stdscr.getch()
        if ch in (ord("q"), ord("Q")):
            break

        if ch == curses.KEY_LEFT:
            hue_center_deg -= 2.0
        elif ch == curses.KEY_RIGHT:
            hue_center_deg += 2.0
        elif ch == ord("["):
            hue_span_deg -= 5.0
        elif ch == ord("]"):
            hue_span_deg += 5.0
        elif ch == ord("-"):
            hue_step_deg += 1.0
        elif ch == ord("="):
            hue_step_deg -= 1.0

        elif ch == curses.KEY_UP:
            L += 0.02
        elif ch == curses.KEY_DOWN:
            L -= 0.02
        elif ch == ord("j"):
            c_min -= 0.01
        elif ch == ord("k"):
            c_min += 0.01
        elif ch == ord("u"):
            c_max -= 0.01
        elif ch == ord("i"):
            c_max += 0.01
        elif ch == ord(","):
            c_step -= 0.005
        elif ch == ord("."):
            c_step += 0.005

        elif ch in (ord("m"), ord("M")):
            mode = {"base": "huepen", "huepen": "huepen+gate", "huepen+gate": "base"}[mode]
        elif ch == ord("1"):
            k = max(0.0, k - 0.05)
        elif ch == ord("2"):
            k = min(3.0, k + 0.05)
        elif ch == ord("3"):
            yellow_min_L = _clamp(yellow_min_L - 0.02, 0.0, 1.0)
        elif ch == ord("4"):
            yellow_min_L = _clamp(yellow_min_L + 0.02, 0.0, 1.0)
        elif ch == ord("5"):
            yellow_min_C = _clamp(yellow_min_C - 0.01, 0.0, 0.40)
        elif ch == ord("6"):
            yellow_min_C = _clamp(yellow_min_C + 0.01, 0.0, 0.40)

        L = _clamp(L, 0.05, 0.98)
        hue_span_deg = _clamp(hue_span_deg, 5.0, 180.0)
        hue_step_deg = _clamp(hue_step_deg, 1.0, 30.0)
        c_step = _clamp(c_step, 0.005, 0.08)
        c_min = _clamp(c_min, 0.0, 0.40)
        c_max = _clamp(c_max, 0.0, 0.40)

    return 0


def main() -> int:
    return curses.wrapper(_loop)


if __name__ == "__main__":
    raise SystemExit(main())
